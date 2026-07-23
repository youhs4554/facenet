import argparse
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple, Union

import numpy as np


ROOT = os.path.dirname(os.path.abspath(__file__))
RETINAFACE_ROOT = os.path.join(ROOT, "Pytorch_Retinaface")
STAR_ROOT = os.path.join(ROOT, "STAR")


EMOTIONS = ["Neutral", "Happy", "Sad", "Surprise", "Fear", "Disgust", "Anger", "Contempt"]
EMOTION_KO = ["중립", "행복", "슬픔", "놀람", "두려움", "혐오", "분노", "경멸"]
AU_INFO = [
    {"code": "AU1", "name_en": "Inner Brow Raiser", "name_ko": "안쪽 눈썹 올림"},
    {"code": "AU2", "name_en": "Outer Brow Raiser", "name_ko": "바깥쪽 눈썹 올림"},
    {"code": "AU4", "name_en": "Brow Lowerer", "name_ko": "눈썹 내림"},
    {"code": "AU6", "name_en": "Cheek Raiser", "name_ko": "볼 올림"},
    {"code": "AU9", "name_en": "Nose Wrinkler", "name_ko": "코 찡그림"},
    {"code": "AU12", "name_en": "Lip Corner Puller", "name_ko": "입꼬리 당김"},
    {"code": "AU25", "name_en": "Lips Part", "name_ko": "입술 벌어짐"},
    {"code": "AU26", "name_en": "Jaw Drop", "name_ko": "턱 내림"},
]
AU_LABELS = [f"{item['code']} - {item['name_en']}" for item in AU_INFO]


def parse_source(value: str) -> Union[int, str]:
    return int(value) if value.isdigit() else value


def is_image_source(value: str) -> bool:
    return not value.isdigit() and os.path.splitext(value.lower())[1] in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def select_device(requested: str, cuda_available: bool, mps_available: bool) -> str:
    if requested:
        return requested
    if cuda_available:
        return "cuda"
    if mps_available:
        return "mps"
    return "cpu"


def scale_and_clip_bbox(
    bbox: Sequence[int],
    scale_factor: float,
    frame_shape: Sequence[int],
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    width = x2 - x1
    height = y2 - y1
    dx = int(width * scale_factor)
    dy = int(height * scale_factor)
    frame_h, frame_w = frame_shape[:2]
    return (
        max(0, x1 - dx),
        max(0, y1 - dy),
        min(frame_w, x2 + dx),
        min(frame_h, y2 + dy),
    )


def eye_points(landmarks: np.ndarray) -> list[Tuple[int, int]]:
    if landmarks.shape[0] >= 98:
        indices = (96, 97)
    elif landmarks.shape[0] >= 68:
        indices = (36, 45)
    else:
        return []
    return [(int(landmarks[i, 0]), int(landmarks[i, 1])) for i in indices]


def ensure_local_imports() -> None:
    for path in (STAR_ROOT, RETINAFACE_ROOT):
        if path not in sys.path:
            sys.path.insert(0, path)


def patch_scipy_for_star() -> None:
    import scipy.integrate

    if not hasattr(scipy.integrate, "simps") and hasattr(scipy.integrate, "simpson"):
        scipy.integrate.simps = scipy.integrate.simpson


class CropMatrix:
    def __init__(self, image_size: int = 256, target_face_scale: float = 1.0):
        self.image_size = image_size
        self.target_face_scale = target_face_scale

    def process(self, scale: float, center_w: float, center_h: float) -> np.ndarray:
        scale_mu = self.image_size / (scale * self.target_face_scale * 200.0)
        to_center = self.image_size / 2.0
        matrix = np.array(
            [
                [scale_mu, 0.0, to_center - scale_mu * center_w],
                [0.0, scale_mu, to_center - scale_mu * center_h],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )
        return matrix


@dataclass
class StarAlignment:
    net: object
    device: object
    input_size: int = 256

    def __post_init__(self) -> None:
        self.crop_matrix = CropMatrix(self.input_size)

    def analyze(self, image: np.ndarray, scale: float, center_w: float, center_h: float) -> np.ndarray:
        import cv2
        import torch

        matrix = self.crop_matrix.process(scale, center_w, center_h)
        cropped = cv2.warpPerspective(
            image,
            matrix,
            dsize=(self.input_size, self.input_size),
            flags=cv2.INTER_LINEAR,
            borderValue=0,
        )
        tensor = torch.from_numpy(cropped[np.newaxis, :]).float().permute(0, 3, 1, 2)
        tensor = (tensor / 255.0 * 2.0 - 1.0).to(self.device)

        with torch.no_grad():
            output = self.net(tensor)

        landmarks = output[-1][0]
        landmarks = (landmarks + 1) / 2
        landmarks = landmarks * torch.tensor([self.input_size, self.input_size]).to(landmarks).view(1, 1, 2)
        landmarks = landmarks.data.cpu().numpy()[0]
        inverse = np.linalg.inv(matrix)

        restored = np.zeros(landmarks.shape, dtype=np.float32)
        for i in range(landmarks.shape[0]):
            restored[i][0] = inverse[0][0] * landmarks[i][0] + inverse[0][1] * landmarks[i][1] + inverse[0][2]
            restored[i][1] = inverse[1][0] * landmarks[i][0] + inverse[1][1] * landmarks[i][1] + inverse[1][2]
        return restored


def load_star_alignment(model_path: str, device: object) -> StarAlignment:
    import argparse as _argparse
    import torch

    ensure_local_imports()
    patch_scipy_for_star()
    from lib import utility

    args = _argparse.Namespace(config_name="alignment", device_id=-1)
    config = utility.get_config(args)
    config.device_id = -1
    utility.set_environment(config)
    net = utility.get_net(config)
    checkpoint = torch.load(model_path, map_location="cpu")
    net.load_state_dict(checkpoint["net"])
    net = net.to(device)
    net.eval()
    return StarAlignment(net=net, device=device)


def load_retinaface(model_path: str, device: object):
    import torch

    ensure_local_imports()
    from data import cfg_mnet
    from models.retinaface import RetinaFace

    old_argv = sys.argv[:]
    try:
        sys.argv = [old_argv[0]]
        from detect import load_model
    finally:
        sys.argv = old_argv

    model = RetinaFace(cfg=cfg_mnet, phase="test")
    model = load_model(model, model_path, load_to_cpu=True)
    model.eval()
    return model.to(device), cfg_mnet


def load_multitask(model_path: str, device: object):
    import torch
    from torchvision import transforms

    from model.MLT import MLT

    model = MLT()
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()
    model = model.to(device)
    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    return model, transform


def detect_faces(frame: np.ndarray, retinaface_model, retina_cfg, device, resize: float = 1.0) -> np.ndarray:
    import torch

    ensure_local_imports()
    from layers.functions.prior_box import PriorBox
    from utils.box_utils import decode, decode_landm
    from utils.nms.py_cpu_nms import py_cpu_nms

    img = np.float32(frame)
    if resize != 1:
        import cv2

        img = cv2.resize(img, None, None, fx=resize, fy=resize, interpolation=cv2.INTER_LINEAR)
    im_height, im_width, _ = img.shape
    scale = torch.Tensor([img.shape[1], img.shape[0], img.shape[1], img.shape[0]]).to(device)
    img -= (104, 117, 123)
    img = img.transpose(2, 0, 1)
    img = torch.from_numpy(img).unsqueeze(0).to(device)

    with torch.no_grad():
        loc, conf, landms = retinaface_model(img)

    priorbox = PriorBox(retina_cfg, image_size=(im_height, im_width))
    priors = priorbox.forward().to(device)
    prior_data = priors.data
    boxes = decode(loc.data.squeeze(0), prior_data, retina_cfg["variance"])
    boxes = (boxes * scale / resize).cpu().numpy()
    scores = conf.squeeze(0).data.cpu().numpy()[:, 1]

    landms = decode_landm(landms.data.squeeze(0), prior_data, retina_cfg["variance"])
    scale1 = torch.Tensor(
        [
            img.shape[3],
            img.shape[2],
            img.shape[3],
            img.shape[2],
            img.shape[3],
            img.shape[2],
            img.shape[3],
            img.shape[2],
            img.shape[3],
            img.shape[2],
        ]
    ).to(device)
    landms = (landms * scale1 / resize).cpu().numpy()

    inds = np.where(scores > 0.02)[0]
    boxes = boxes[inds]
    landms = landms[inds]
    scores = scores[inds]
    if scores.size == 0:
        return np.empty((0, 15), dtype=np.float32)

    order = scores.argsort()[::-1]
    boxes = boxes[order]
    landms = landms[order]
    scores = scores[order]

    dets = np.hstack((boxes, scores[:, np.newaxis])).astype(np.float32, copy=False)
    keep = py_cpu_nms(dets, 0.4)
    return np.concatenate((dets[keep, :], landms[keep]), axis=1)


def draw_landmarks(image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    import cv2

    out = image.copy()
    for x, y in landmarks:
        cv2.circle(out, (int(x * 16), int(y * 16)), 16, (0, 255, 0), -1, cv2.LINE_AA, shift=4)
    return out


def gaze_to_2d(gaze: np.ndarray) -> Tuple[float, float]:
    yaw, pitch = float(gaze[0]), float(gaze[1])
    x = -math.cos(pitch) * math.sin(yaw)
    y = -math.sin(pitch)
    z = -math.cos(pitch) * math.cos(yaw)
    scale = max(35.0, 120.0 * abs(z))
    return x * scale, y * scale


def draw_gaze(image: np.ndarray, gaze: np.ndarray, points: Iterable[Tuple[int, int]]) -> np.ndarray:
    import cv2

    out = image.copy()
    dx, dy = gaze_to_2d(gaze)
    for point in points:
        end = (int(point[0] + dx), int(point[1] + dy))
        cv2.arrowedLine(out, point, end, (0, 255, 255), 2, tipLength=0.25)
    return out


def au_row_positions(height: int, count: int) -> list[int]:
    if count <= 0:
        return []
    top = 58 if height >= 300 else 48
    bottom = max(top, height - 16)
    if count == 1:
        return [top]
    step = (bottom - top) / (count - 1)
    return [int(top + step * index) for index in range(count)]


def draw_au_panel(au_values: np.ndarray, height: int, width: int = 430) -> np.ndarray:
    import cv2

    panel = np.full((height, width, 3), 245, dtype=np.uint8)
    compact = height < 320
    title_scale = 0.62 if compact else 0.7
    font_scale = 0.34 if compact else 0.44
    value_scale = 0.36 if compact else 0.42
    bar_height = 10 if compact else 18
    cv2.putText(panel, "Action Units", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, title_scale, (30, 30, 30), 2)
    max_bar = width - 248
    for label, value, y in zip(AU_LABELS, au_values, au_row_positions(height, len(AU_LABELS))):
        value = float(np.clip(value, 0.0, 1.0))
        text_y = y + bar_height
        cv2.putText(panel, label, (14, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (40, 40, 40), 1)
        bar_x = width - max_bar - 48
        cv2.rectangle(panel, (bar_x, y), (bar_x + max_bar, y + bar_height), (190, 190, 190), 1)
        cv2.rectangle(panel, (bar_x + 1, y + 1), (bar_x + 1 + int(max_bar * value), y + bar_height - 1), (40, 170, 70), -1)
        cv2.putText(panel, f"{value:.2f}", (width - 48, text_y), cv2.FONT_HERSHEY_SIMPLEX, value_scale, (40, 40, 40), 1)
    return panel


def draw_label(frame: np.ndarray, bbox: Tuple[int, int, int, int], label: str, score: float) -> np.ndarray:
    import cv2

    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
    text = f"{label} {score:.2f}"
    y = y1 - 8 if y1 > 22 else y1 + 22
    cv2.putText(frame, text, (x1, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 0), 2)
    return frame


def build_au_metadata(au_values: np.ndarray) -> list[dict]:
    return [
        {
            "code": info["code"],
            "name_en": info["name_en"],
            "name_ko": info["name_ko"],
            "value": float(np.clip(value, 0.0, 1.0)),
        }
        for info, value in zip(AU_INFO, au_values)
    ]


def analyze_frame(
    frame,
    retinaface_model,
    retina_cfg,
    alignment,
    multitask_model,
    transform,
    device,
    min_conf: float,
    include_au_panel: bool = True,
    include_gaze: bool = True,
):
    import cv2
    import torch
    from PIL import Image

    detections = detect_faces(frame, retinaface_model, retina_cfg, device)
    au_display = np.zeros(len(AU_LABELS), dtype=np.float32)
    analysis = {
        "face_count": int(len(detections)),
        "emotion": {"label": "No face", "label_ko": "얼굴 없음", "confidence": 0.0},
        "emotions": [
            {"label": label, "label_ko": label_ko, "value": 0.0}
            for label, label_ko in zip(EMOTIONS, EMOTION_KO)
        ],
        "gaze": {"yaw": 0.0, "pitch": 0.0},
        "aus": build_au_metadata(au_display),
    }

    for det in detections[:1]:
        if det[4] < min_conf:
            continue
        bbox = scale_and_clip_bbox(det[:4], 0.15, frame.shape)
        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            continue

        face = frame[y1:y2, x1:x2]
        center_w = face.shape[1] / 2.0
        center_h = face.shape[0] / 2.0
        scale = min(face.shape[1], face.shape[0]) / 200.0 * 1.05
        landmarks = alignment.analyze(face, float(scale), float(center_w), float(center_h))

        face_rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        image = transform(Image.fromarray(face_rgb)).unsqueeze(0).to(device)
        with torch.no_grad():
            emotion_output, gaze_output, au_output = multitask_model(image)

        emotion_probs = torch.softmax(emotion_output[0], dim=0).cpu().numpy()
        emotion_index = int(np.argmax(emotion_probs))
        au_display = torch.sigmoid(au_output[0]).cpu().numpy()
        gaze_values = gaze_output[0].detach().cpu().numpy()
        analysis = {
            "face_count": int(len(detections)),
            "emotion": {
                "label": EMOTIONS[emotion_index],
                "label_ko": EMOTION_KO[emotion_index],
                "confidence": float(emotion_probs[emotion_index]),
            },
            "emotions": [
                {"label": label, "label_ko": label_ko, "value": float(value)}
                for label, label_ko, value in zip(EMOTIONS, EMOTION_KO, emotion_probs)
            ],
            "gaze": {"yaw": float(gaze_values[0]), "pitch": float(gaze_values[1])},
            "aus": build_au_metadata(au_display),
        }
        face_drawn = draw_landmarks(face, landmarks)
        if include_gaze:
            face_drawn = draw_gaze(face_drawn, gaze_values, eye_points(landmarks))
        frame[y1:y2, x1:x2] = face_drawn
        draw_label(frame, bbox, EMOTIONS[emotion_index], float(emotion_probs[emotion_index]))

    if include_au_panel:
        frame = np.hstack((frame, draw_au_panel(au_display, frame.shape[0])))
    return frame, analysis


def process_frame(frame, retinaface_model, retina_cfg, alignment, multitask_model, transform, device, min_conf: float):
    annotated, _ = analyze_frame(frame, retinaface_model, retina_cfg, alignment, multitask_model, transform, device, min_conf)
    return annotated


def run_demo(args) -> int:
    import cv2
    import torch

    mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    device = torch.device(select_device(args.device, torch.cuda.is_available(), mps_available))
    print(f"Loading models on {device}...")
    multitask_model, transform = load_multitask(args.multitask_weights, device)
    retinaface_model, retina_cfg = load_retinaface(args.retina_weights, device)
    alignment = load_star_alignment(args.landmark_weights, device)

    if is_image_source(args.source):
        frame = cv2.imread(args.source, cv2.IMREAD_COLOR)
        if frame is None:
            print(f"Could not read image source: {args.source}")
            return 2
        if args.width and frame.shape[1] > args.width:
            scale = args.width / frame.shape[1]
            frame = cv2.resize(frame, (args.width, int(frame.shape[0] * scale)))
        shown = process_frame(
            frame,
            retinaface_model,
            retina_cfg,
            alignment,
            multitask_model,
            transform,
            device,
            args.min_confidence,
        )
        if args.output:
            cv2.imwrite(args.output, shown)
        if not args.no_window:
            cv2.imshow("OpenFace 3.0 Live Demo", shown)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return 0

    cap = cv2.VideoCapture(parse_source(args.source))
    if not cap.isOpened():
        print(f"Could not open video source: {args.source}")
        return 2

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    last = time.time()
    fps = 0.0
    frames = 0
    print("Press q or Esc in the OpenCV window to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.width and frame.shape[1] > args.width:
            scale = args.width / frame.shape[1]
            frame = cv2.resize(frame, (args.width, int(frame.shape[0] * scale)))

        shown = process_frame(
            frame,
            retinaface_model,
            retina_cfg,
            alignment,
            multitask_model,
            transform,
            device,
            args.min_confidence,
        )
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-6))
        last = now
        cv2.putText(shown, f"FPS {fps:.1f}", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        if args.output:
            cv2.imwrite(args.output, shown)
        if not args.no_window:
            cv2.imshow("OpenFace 3.0 Live Demo", shown)
        frames += 1
        if args.max_frames and frames >= args.max_frames:
            break
        if not args.no_window:
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break

    cap.release()
    cv2.destroyAllWindows()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenFace 3.0 OpenCV live demo")
    parser.add_argument("--source", default="0", help="Camera index or video path")
    parser.add_argument("--device", default="", help="cpu, cuda, mps, or empty for auto")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--multitask-weights", default=os.path.join("weights", "stage2_epoch_7_loss_1.1606_acc_0.5589.pth"))
    parser.add_argument("--retina-weights", default=os.path.join("weights", "mobilenet0.25_Final.pth"))
    parser.add_argument("--landmark-weights", default=os.path.join("weights", "Landmark_98.pkl"))
    return parser


if __name__ == "__main__":
    raise SystemExit(run_demo(build_parser().parse_args()))
