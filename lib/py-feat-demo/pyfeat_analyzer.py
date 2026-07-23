import base64
import importlib.util
import math
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np


EMOTION_LABELS = ["anger", "disgust", "fear", "happiness", "sadness", "surprise", "neutral"]
EMOTION_COLUMN_ALIASES = {
    "anger": ("anger", "Anger"),
    "disgust": ("disgust", "Disgust"),
    "fear": ("fear", "Fear"),
    "happiness": ("happiness", "Happy"),
    "sadness": ("sadness", "Sad"),
    "surprise": ("surprise", "Surprise"),
    "neutral": ("neutral", "Neutral", "_neutral"),
}
AU_LABELS = [
    "AU01",
    "AU02",
    "AU04",
    "AU05",
    "AU06",
    "AU07",
    "AU09",
    "AU10",
    "AU11",
    "AU12",
    "AU14",
    "AU15",
    "AU17",
    "AU20",
    "AU23",
    "AU24",
    "AU25",
    "AU26",
    "AU28",
    "AU43",
]
AU_DESCRIPTIONS = {
    "AU01": "Inner Brow Raiser / 안쪽 눈썹 올림",
    "AU02": "Outer Brow Raiser / 바깥쪽 눈썹 올림",
    "AU04": "Brow Lowerer / 눈썹 내림",
    "AU05": "Upper Lid Raiser / 윗눈꺼풀 올림",
    "AU06": "Cheek Raiser / 볼 올림",
    "AU07": "Lid Tightener / 눈꺼풀 조임",
    "AU09": "Nose Wrinkler / 코 주름",
    "AU10": "Upper Lip Raiser / 윗입술 올림",
    "AU11": "Nasolabial Deepener / 코입술 고랑 깊어짐",
    "AU12": "Lip Corner Puller / 입꼬리 당김",
    "AU14": "Dimpler / 보조개",
    "AU15": "Lip Corner Depressor / 입꼬리 내림",
    "AU17": "Chin Raiser / 턱끝 올림",
    "AU20": "Lip Stretcher / 입술 당김",
    "AU23": "Lip Tightener / 입술 조임",
    "AU24": "Lip Pressor / 입술 누름",
    "AU25": "Lips Part / 입 벌림",
    "AU26": "Jaw Drop / 턱 내림",
    "AU28": "Lip Suck / 입술 빨아들임",
    "AU43": "Eyes Closed / 눈 감음",
}


LIVE_MAX_TRACK_INTERVAL = int(os.environ.get("PYFEAT_LIVE_MAX_TRACK_INTERVAL", "180"))
LIVE_SCENE_MOTION_THRESHOLD = float(os.environ.get("PYFEAT_LIVE_SCENE_MOTION_THRESHOLD", "6.0"))
LIVE_REFINE_DETECT_ROI = os.environ.get("PYFEAT_LIVE_REFINE_DETECT_ROI", "0").lower() in {"1", "true", "yes"}
LIVE_ROI_FROM_MESH_EXPAND = 1.35
_FACEBOX_W_PAD = 0.97
_FACEBOX_H_PAD = 1.11
_GPU_LOCK = threading.Lock()


def decode_image_data_url(data_url: str) -> np.ndarray:
    try:
        raw, _mime = decode_data_url_bytes(data_url)
        encoded = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    except Exception as exc:
        raise ValueError("Invalid image payload") from exc
    if image is None:
        raise ValueError("Invalid image payload")
    return image


def decode_data_url_bytes(data_url: str) -> tuple[bytes, str]:
    header = ""
    payload = data_url
    if "," in data_url:
        header, payload = data_url.split(",", 1)
    mime = "application/octet-stream"
    if header.startswith("data:"):
        mime = header[5:].split(";", 1)[0] or mime
    return base64.b64decode(payload, validate=True), mime


def encode_jpeg_data_url(image: np.ndarray, quality=86) -> str:
    params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    ok, encoded = cv2.imencode(".jpg", image, params)
    if not ok:
        raise ValueError("Could not encode image")
    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def frame_to_rgb_tensor(frame: np.ndarray):
    import torch

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.ascontiguousarray(rgb))
    return tensor.permute(2, 0, 1).unsqueeze(0).contiguous()


def frame_to_v2_batch(frame: np.ndarray):
    import torch
    from PIL import Image
    from feat.utils.image_operations import convert_image_to_tensor

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    tensor = convert_image_to_tensor(image, img_type="float32")
    batch_size = int(tensor.shape[0])
    return tensor, {
        "Image": tensor,
        "Scale": torch.ones(batch_size),
        "Padding": {
            "Left": torch.zeros(batch_size),
            "Top": torch.zeros(batch_size),
            "Right": torch.zeros(batch_size),
            "Bottom": torch.zeros(batch_size),
        },
        "FileName": ["tensor"] * batch_size,
    }


def downscale_gray(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)


def scene_motion(previous: np.ndarray | None, current: np.ndarray) -> float:
    if previous is None:
        return float("nan")
    return float(np.abs(current.astype(np.float32) - previous.astype(np.float32)).mean())


def mesh_to_roi(mesh: np.ndarray, frame_width: float, frame_height: float) -> tuple[float, float, float, float]:
    x1 = float(np.nanmin(mesh[:, 0]))
    y1 = float(np.nanmin(mesh[:, 1]))
    x2 = float(np.nanmax(mesh[:, 0]))
    y2 = float(np.nanmax(mesh[:, 1]))
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    width = max(1.0, (x2 - x1) * LIVE_ROI_FROM_MESH_EXPAND)
    height = max(1.0, (y2 - y1) * LIVE_ROI_FROM_MESH_EXPAND)
    left = max(0.0, cx - width / 2.0)
    top = max(0.0, cy - height / 2.0)
    right = min(float(frame_width), cx + width / 2.0)
    bottom = min(float(frame_height), cy + height / 2.0)
    return left, top, max(left, right), max(top, bottom)


class LiveTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.rois: list[tuple[float, float, float, float]] = []
        self.previous_gray = None
        self.frames_since_detect = 0
        self.force_detect = True
        self.last_mode = "detect"
        self.last_motion = float("nan")

    def should_detect(self, frame: np.ndarray) -> bool:
        current_gray = downscale_gray(frame)
        self.current_gray = current_gray
        self.last_motion = scene_motion(self.previous_gray, current_gray)
        if self.force_detect or not self.rois:
            self.last_mode = "detect"
            return True
        if self.frames_since_detect >= LIVE_MAX_TRACK_INTERVAL - 1:
            self.last_mode = "detect"
            return True
        if self.previous_gray is not None and self.last_motion > LIVE_SCENE_MOTION_THRESHOLD:
            self.last_mode = "detect"
            return True
        self.last_mode = "track"
        return False

    def note_detect(self, meshes: list[np.ndarray], frame_width: float, frame_height: float):
        self.rois = [mesh_to_roi(mesh, frame_width, frame_height) for mesh in meshes if mesh.size]
        self.frames_since_detect = 0
        self.force_detect = not self.rois
        self.previous_gray = self.current_gray
        self.last_mode = "detect"

    def note_track(self, meshes: list[np.ndarray], frame_width: float, frame_height: float):
        if not meshes or len(meshes) != len(self.rois):
            self.force_detect = True
            self.previous_gray = self.current_gray
            self.last_mode = "detect"
            return
        self.rois = [mesh_to_roi(mesh, frame_width, frame_height) for mesh in meshes if mesh.size]
        self.frames_since_detect += 1
        self.force_detect = not self.rois
        self.previous_gray = self.current_gray
        self.last_mode = "track"


def select_device(requested="auto") -> str:
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        return "cpu"
    return "cpu"


def env_bool(name: str):
    value = os.environ.get(name)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def normalize_result(result, image_shape, latency_ms) -> dict:
    rows = _rows_from_result(result)
    fps = 1000.0 / latency_ms if _is_finite(latency_ms) and latency_ms > 0 else 0.0
    faces = [_normalize_face(row) for row in rows]
    return {
        "face_count": len(faces),
        "faces": faces,
        "primary_face": 0 if faces else None,
        "fps": fps,
        "latency_ms": latency_ms,
    }


@lru_cache(maxsize=1)
def _pandas():
    try:
        import pandas as pd
    except ImportError:
        return None
    return pd


def _rows_from_result(result):
    if result is None:
        return []
    if hasattr(result, "to_pandas"):
        result = result.to_pandas()
    if isinstance(result, dict):
        if not result:
            return []
        if any(_is_sequence(value) for value in result.values()):
            pd = _pandas()
            if pd is None:
                return [result]
            frame = pd.DataFrame(result)
            return [] if frame.empty else [row for _, row in frame.iterrows()]
        return [result]
    if isinstance(result, list):
        return result
    pd = _pandas()
    if pd is not None and isinstance(result, pd.DataFrame):
        if result.empty:
            return []
        return [row for _, row in result.iterrows()]
    return []


def _normalize_face(row):
    landmarks = _landmark_points(row)
    mesh = _dense_mesh_points(row) or landmarks
    return {
        "box": {
            "x": _number(row, "FaceRectX"),
            "y": _number(row, "FaceRectY"),
            "width": _number(row, "FaceRectWidth"),
            "height": _number(row, "FaceRectHeight"),
            "confidence": _number(row, "FaceScore"),
        },
        "emotions": _sorted_emotions(row),
        "aus": _sorted_aus(row),
        "valence": _number(row, "valence"),
        "arousal": _number(row, "arousal"),
        "pose": {
            "pitch": _number(row, "Pitch"),
            "roll": _number(row, "Roll"),
            "yaw": _number(row, "Yaw"),
        },
        "gaze": {
            "x": _number(row, "gaze_0_x"),
            "y": _number(row, "gaze_0_y"),
            "z": _number(row, "gaze_0_z"),
        },
        "landmarks": landmarks,
        "landmark_count": len(landmarks),
        "mesh": mesh,
        "mesh_count": len(mesh),
    }


def _sorted_emotions(row):
    scores = [{"label": label, "value": _number_from_aliases(row, EMOTION_COLUMN_ALIASES[label])} for label in EMOTION_LABELS]
    return sorted(scores, key=lambda item: item["value"], reverse=True)


def _sorted_aus(row):
    scores = [{"code": code, "value": _number(row, code)} for code in AU_LABELS]
    return sorted(scores, key=lambda item: item["value"], reverse=True)


def _landmark_points(row):
    indices = set()
    for key in _row_keys(row):
        if not isinstance(key, str) or len(key) < 3:
            continue
        axis, _, index = key.partition("_")
        if axis in {"x", "y", "z"} and index.isdigit():
            indices.add(int(index))
    return [
        {
            "x": _number(row, f"x_{index}"),
            "y": _number(row, f"y_{index}"),
            "z": _number(row, f"z_{index}"),
        }
        for index in sorted(indices)
    ]


def _dense_mesh_points(row):
    indices = set()
    for key in _row_keys(row):
        if not isinstance(key, str) or not key.startswith("mesh_"):
            continue
        _, axis, index = key.split("_", 2) if key.count("_") >= 2 else ("", "", "")
        if axis in {"x", "y", "z"} and index.isdigit():
            indices.add(int(index))
    return [
        {
            "x": _number(row, f"mesh_x_{index}"),
            "y": _number(row, f"mesh_y_{index}"),
            "z": _number(row, f"mesh_z_{index}"),
        }
        for index in sorted(indices)
    ]


def _valid_face_rows(result):
    pd = _pandas()
    if pd is None or not isinstance(result, pd.DataFrame) or result.empty:
        return result
    if "FaceScore" not in result.columns:
        return result
    scores = pd.to_numeric(result["FaceScore"], errors="coerce")
    return result[scores > 0].reset_index(drop=True)


def _meshes_from_rows(result) -> list[np.ndarray]:
    pd = _pandas()
    if pd is None or not isinstance(result, pd.DataFrame) or result.empty:
        return []
    meshes = []
    x_cols = [f"mesh_x_{index}" for index in range(478)]
    y_cols = [f"mesh_y_{index}" for index in range(478)]
    if not all(column in result.columns for column in x_cols + y_cols):
        return []
    xs = result[x_cols].to_numpy(dtype=float)
    ys = result[y_cols].to_numpy(dtype=float)
    for mesh_x, mesh_y in zip(xs, ys):
        if np.isnan(mesh_x).any() or np.isnan(mesh_y).any():
            continue
        meshes.append(np.column_stack([mesh_x, mesh_y]))
    return meshes


def _stabilize_facebox_from_meshes(result, meshes: list[np.ndarray], frame_width: float, frame_height: float):
    pd = _pandas()
    if pd is None or not isinstance(result, pd.DataFrame) or result.empty or len(result) != len(meshes):
        return result
    stabilized = result.copy()
    xs, ys, widths, heights = [], [], [], []
    for mesh in meshes:
        if mesh.size == 0:
            xs.append(np.nan)
            ys.append(np.nan)
            widths.append(np.nan)
            heights.append(np.nan)
            continue
        x1 = float(np.nanmin(mesh[:, 0]))
        y1 = float(np.nanmin(mesh[:, 1]))
        x2 = float(np.nanmax(mesh[:, 0]))
        y2 = float(np.nanmax(mesh[:, 1]))
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        width = (x2 - x1) * _FACEBOX_W_PAD
        height = (y2 - y1) * _FACEBOX_H_PAD
        left = max(0.0, cx - width / 2.0)
        top = max(0.0, cy - height / 2.0)
        right = min(float(frame_width), cx + width / 2.0)
        bottom = min(float(frame_height), cy + height / 2.0)
        xs.append(left)
        ys.append(top)
        widths.append(max(0.0, right - left))
        heights.append(max(0.0, bottom - top))
    stabilized.loc[:, "FaceRectX"] = xs
    stabilized.loc[:, "FaceRectY"] = ys
    stabilized.loc[:, "FaceRectWidth"] = widths
    stabilized.loc[:, "FaceRectHeight"] = heights
    return stabilized


def _number_from_aliases(row, keys, default=0.0) -> float:
    for key in keys:
        value = _number(row, key, None)
        if value is not None:
            return value
    return default


def _number(row, key, default=0.0) -> float:
    try:
        value = row[key]
    except (KeyError, TypeError):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if _is_finite(number) else default


def _is_finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _is_sequence(value) -> bool:
    if isinstance(value, (list, tuple, np.ndarray)):
        return True
    pd = _pandas()
    return pd is not None and isinstance(value, pd.Series)


def _row_keys(row):
    if hasattr(row, "index"):
        return row.index
    if hasattr(row, "keys"):
        return row.keys()
    return []


@dataclass
class AnalyzerState:
    device_name: str = "auto"
    detector_type: str = "Detectorv2"
    model_config: dict = field(default_factory=dict)
    state: str = "idle"
    error: str = ""
    detector: object = field(default=None, init=False, repr=False)
    live_tracker: LiveTracker = field(default_factory=LiveTracker, init=False, repr=False)
    _thread: threading.Thread = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def snapshot(self):
        with self._lock:
            if self.state == "loading" and self.detector is None and self._thread and not self._thread.is_alive():
                self.state = "error"
                self.error = self.error or "Analyzer loading stopped before ready"
            return {
                "state": self.state,
                "ready": self.detector is not None and self.state == "ready",
                "error": self.error,
                "device": self.device_name,
                "detector_type": self.detector_type,
                "live_mode": self.live_tracker.last_mode,
                "labels": {
                    "emotions": EMOTION_LABELS,
                    "aus": AU_LABELS,
                    "au_descriptions": AU_DESCRIPTIONS,
                },
            }

    def start_loading(self):
        with self._lock:
            if self.detector is not None or self.state in {"ready", "loading"}:
                return
            if self._thread and self._thread.is_alive():
                return
            self.state = "loading"
            self.error = ""
            self._thread = threading.Thread(target=self._load, daemon=True)
            self._thread.start()

    def _load(self):
        try:
            if importlib.util.find_spec("feat") is None:
                raise ModuleNotFoundError("No module named 'feat'")
            device = select_device(self.device_name)
            if self.detector_type == "Detectorv1":
                from feat import Detectorv1

                allowed = {
                    "face_model",
                    "landmark_model",
                    "au_model",
                    "emotion_model",
                    "identity_model",
                    "gaze_model",
                }
                kwargs = {key: value for key, value in self.model_config.items() if key in allowed and value}
                detector = Detectorv1(device=device, **kwargs)
            else:
                from feat import Detectorv2

                allowed = {"identity_model", "amp", "compile", "multitask_weights"}
                kwargs = {"identity_model": None}
                env_amp = env_bool("PYFEAT_LIVE_AMP")
                env_compile = env_bool("PYFEAT_LIVE_COMPILE")
                if env_amp is not None:
                    kwargs["amp"] = env_amp
                if env_compile is not None:
                    kwargs["compile"] = env_compile
                kwargs.update({key: value for key, value in self.model_config.items() if key in allowed})
                detector = Detectorv2(device=device, **kwargs)
            with self._lock:
                self.detector = detector
                self.live_tracker.reset()
                self.device_name = device
                self.state = "ready"
        except Exception as exc:
            with self._lock:
                self.detector = None
                self.error = str(exc)
                self.state = "error"

    def configure(self, device=None, detector_type=None, **kwargs):
        next_detector_type = detector_type or self.detector_type
        if next_detector_type not in {"Detectorv1", "Detectorv2"}:
            raise ValueError(f"Unknown detector type: {next_detector_type}")
        next_device = device or self.device_name
        next_model_config = {
            key: value
            for key, value in kwargs.items()
            if value is not None or key == "identity_model"
        }
        if (
            next_device == self.device_name
            and next_detector_type == self.detector_type
            and next_model_config == self.model_config
        ):
            return
        with self._lock:
            self.device_name = next_device
            self.detector_type = next_detector_type
            self.model_config = next_model_config
            self.detector = None
            self.live_tracker.reset()
            self.error = ""
            self.state = "idle"
            self._thread = None

    def analyze_fex(self, frame):
        if self.detector is None:
            raise RuntimeError("Analyzer is not ready")
        return self._detect_frame(frame)

    def analyze_video_fex(self, video_data_url):
        if self.detector is None:
            raise RuntimeError("Analyzer is not ready")
        raw, mime = decode_data_url_bytes(video_data_url)
        suffix = ".mp4" if mime == "video/mp4" else ".video"
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(raw)
            return self.detector.detect(temp_path, data_type="video")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def analyze(self, frame):
        if self.detector is None:
            raise RuntimeError("Analyzer is not ready")

        start = time.perf_counter()
        result = self.analyze_fex(frame)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return normalize_result(result, frame.shape, latency_ms)

    def _detect_frame(self, frame):
        if self.detector_type == "Detectorv2" and hasattr(self.detector, "crop_faces_from_boxes"):
            return self._detect_frame_v2_live(frame)
        tensor = frame_to_rgb_tensor(frame)
        return self.detector.detect(
            tensor,
            data_type="tensor",
            batch_size=1,
            num_workers=0,
            pin_memory=False,
            progress_bar=False,
        )

    def _detect_frame_v2_live(self, frame):
        import torch

        tensor, batch_data = frame_to_v2_batch(frame)
        frame_height, frame_width = frame.shape[:2]
        do_detect = self.live_tracker.should_detect(frame)
        with _GPU_LOCK:
            try:
                if do_detect:
                    faces_data = self.detector.detect_faces(tensor, face_detection_threshold=0.5)
                    result = self.detector.forward(faces_data, batch_data)
                    initial_meshes = _meshes_from_rows(result) if LIVE_REFINE_DETECT_ROI else []
                    if LIVE_REFINE_DETECT_ROI and initial_meshes and all(mesh.size for mesh in initial_meshes):
                        rois = [mesh_to_roi(mesh, frame_width, frame_height) for mesh in initial_meshes]
                        try:
                            boxes = torch.tensor(rois, dtype=torch.float32)
                            faces_data = self.detector.crop_faces_from_boxes(tensor, boxes)
                            result = self.detector.forward(faces_data, batch_data)
                        except Exception:
                            pass
                else:
                    boxes = torch.tensor(self.live_tracker.rois, dtype=torch.float32)
                    faces_data = self.detector.crop_faces_from_boxes(tensor, boxes)
                    result = self.detector.forward(faces_data, batch_data)
            except Exception:
                if do_detect:
                    raise
                faces_data = self.detector.detect_faces(tensor, face_detection_threshold=0.5)
                result = self.detector.forward(faces_data, batch_data)
                do_detect = True
        result = _valid_face_rows(result)
        meshes = _meshes_from_rows(result)
        if do_detect:
            self.live_tracker.note_detect(meshes, frame_width, frame_height)
        else:
            self.live_tracker.note_track(meshes, frame_width, frame_height)
        return _stabilize_facebox_from_meshes(result, meshes, frame_width, frame_height)

    @staticmethod
    def _batch_data_for_tensor(tensor):
        import torch

        batch_size = int(tensor.shape[0])
        return {
            "Image": tensor,
            "Scale": torch.ones(batch_size),
            "Padding": {
                "Left": torch.zeros(batch_size),
                "Top": torch.zeros(batch_size),
                "Right": torch.zeros(batch_size),
                "Bottom": torch.zeros(batch_size),
            },
            "FileName": ["tensor"] * batch_size,
        }
