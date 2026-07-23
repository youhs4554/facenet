import base64
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import pandas as pd

from pyfeat_analyzer import (
    AU_LABELS,
    AU_DESCRIPTIONS,
    EMOTION_LABELS,
    AnalyzerState,
    LiveTracker,
    decode_image_data_url,
    encode_jpeg_data_url,
    mesh_to_roi,
    normalize_result,
    select_device,
)


class PyFeatAnalyzerTests(unittest.TestCase):
    def make_image_data_url(self, image):
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        payload = base64.b64encode(encoded.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{payload}"

    def test_decode_image_data_url_accepts_browser_jpeg_payload_and_preserves_shape(self):
        image = np.zeros((12, 16, 3), dtype=np.uint8)
        image[:, :, 1] = 200

        decoded = decode_image_data_url(self.make_image_data_url(image))

        self.assertEqual(decoded.shape, image.shape)
        self.assertEqual(decoded.dtype, np.uint8)

    def test_encode_jpeg_data_url_returns_jpeg_data_url_prefix(self):
        image = np.zeros((8, 10, 3), dtype=np.uint8)

        encoded = encode_jpeg_data_url(image)

        self.assertTrue(encoded.startswith("data:image/jpeg;base64,"))

    def test_select_device_honors_explicit_cpu_and_mps(self):
        self.assertEqual(select_device("cpu"), "cpu")
        self.assertEqual(select_device("mps"), "mps")

    def test_live_tracker_detects_once_then_tracks_stable_frames(self):
        tracker = LiveTracker()
        frame = np.zeros((64, 96, 3), dtype=np.uint8)
        mesh = np.array([[30, 20], [60, 20], [60, 50], [30, 50]], dtype=float)

        self.assertTrue(tracker.should_detect(frame))
        tracker.note_detect([mesh], 96, 64)

        self.assertFalse(tracker.should_detect(frame.copy()))
        self.assertEqual(tracker.last_mode, "track")

    def test_mesh_to_roi_expands_and_clamps_to_frame(self):
        mesh = np.array([[2, 3], [20, 3], [20, 24], [2, 24]], dtype=float)

        left, top, right, bottom = mesh_to_roi(mesh, 30, 28)

        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(right, 30)
        self.assertLessEqual(bottom, 28)
        self.assertGreater(right - left, 18)
        self.assertGreater(bottom - top, 21)

    def test_analyzer_state_snapshot_reports_idle_not_ready_before_load(self):
        snapshot = AnalyzerState(device_name="cpu").snapshot()

        self.assertEqual(snapshot["state"], "idle")
        self.assertFalse(snapshot["ready"])
        self.assertEqual(snapshot["device"], "cpu")
        self.assertEqual(snapshot["labels"]["emotions"], EMOTION_LABELS)
        self.assertEqual(snapshot["labels"]["aus"], AU_LABELS)
        self.assertEqual(snapshot["labels"]["au_descriptions"], AU_DESCRIPTIONS)

    def test_start_loading_noops_when_already_ready(self):
        state = AnalyzerState(device_name="cpu")
        detector = object()
        state.detector = detector
        state.state = "ready"

        state.start_loading()

        self.assertEqual(state.state, "ready")
        self.assertIs(state.detector, detector)
        self.assertIsNone(state._thread)

    def test_configure_supports_detectorv1_and_resets_ready_detector(self):
        state = AnalyzerState(device_name="cpu")
        state.detector = object()
        state.state = "ready"

        state.configure(
            device="cpu",
            detector_type="Detectorv1",
            face_model="retinaface",
            landmark_model="mobilefacenet",
        )

        snapshot = state.snapshot()
        self.assertEqual(snapshot["state"], "idle")
        self.assertFalse(snapshot["ready"])
        self.assertEqual(snapshot["detector_type"], "Detectorv1")
        self.assertEqual(state.model_config["face_model"], "retinaface")

    def test_configure_preserves_disabled_identity_model(self):
        state = AnalyzerState(device_name="cpu")

        state.configure(device="cpu", detector_type="Detectorv2", identity_model=None)

        self.assertIn("identity_model", state.model_config)
        self.assertIsNone(state.model_config["identity_model"])

    def test_detect_frame_uses_tensor_fast_path_without_temp_image_file(self):
        class FakeDetector:
            def __init__(self):
                self.calls = []

            def detect(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return pd.DataFrame()

        state = AnalyzerState(device_name="cpu")
        detector = FakeDetector()
        state.detector = detector
        state.state = "ready"
        frame = np.zeros((12, 16, 3), dtype=np.uint8)
        sentinel = object()

        with patch("pyfeat_analyzer.frame_to_rgb_tensor", return_value=sentinel):
            state.analyze_fex(frame)

        args, kwargs = detector.calls[0]
        self.assertIs(args[0], sentinel)
        self.assertEqual(kwargs["data_type"], "tensor")
        self.assertFalse(kwargs["progress_bar"])
        self.assertEqual(kwargs["batch_size"], 1)

    def test_import_does_not_require_pandas(self):
        script = textwrap.dedent(
            """
            import importlib.abc
            import sys

            class BlockPandas(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "pandas" or fullname.startswith("pandas."):
                        raise ModuleNotFoundError("blocked pandas import")
                    return None

            sys.meta_path.insert(0, BlockPandas())
            import pyfeat_analyzer
            print("import ok")
            """
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout.strip(), "import ok")

    def test_normalize_result_handles_empty_dataframe_as_no_face(self):
        normalized = normalize_result(pd.DataFrame(), image_shape=(120, 160, 3), latency_ms=37.5)

        self.assertEqual(normalized["face_count"], 0)
        self.assertEqual(normalized["faces"], [])
        self.assertIsNone(normalized["primary_face"])
        self.assertEqual(normalized["latency_ms"], 37.5)

    def test_normalize_result_maps_fex_like_row_to_api_contract(self):
        row = {
            "FaceRectX": 10,
            "FaceRectY": 20,
            "FaceRectWidth": 30,
            "FaceRectHeight": 40,
            "FaceScore": 0.91,
            "anger": 0.03,
            "disgust": 0.01,
            "fear": 0.02,
            "happiness": 0.8,
            "sadness": 0.04,
            "surprise": 0.05,
            "neutral": 0.2,
            "AU12": 0.72,
            "AU01": 0.31,
            "valence": 0.67,
            "arousal": 0.42,
            "Pitch": 1.5,
            "Roll": -2.5,
            "Yaw": 3.5,
            "gaze_0_x": 0.1,
            "gaze_0_y": 0.2,
            "gaze_0_z": 0.3,
            "x_0": 11,
            "y_0": 21,
            "z_0": 31,
            "mesh_x_0": 101,
            "mesh_y_0": 201,
            "mesh_z_0": 0.1,
            "mesh_x_1": 102,
            "mesh_y_1": 202,
            "mesh_z_1": 0.2,
        }

        normalized = normalize_result(pd.DataFrame([row]), image_shape=(120, 160, 3), latency_ms=50)

        self.assertEqual(normalized["face_count"], 1)
        self.assertEqual(normalized["fps"], 20.0)
        self.assertEqual(normalized["latency_ms"], 50)
        self.assertEqual(normalized["primary_face"], 0)

        face = normalized["faces"][0]
        self.assertEqual(
            face["box"],
            {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0, "confidence": 0.91},
        )
        self.assertEqual(face["emotions"][0], {"label": "happiness", "value": 0.8})
        self.assertEqual(face["aus"][0], {"code": "AU12", "value": 0.72})
        self.assertEqual(face["valence"], 0.67)
        self.assertEqual(face["arousal"], 0.42)
        self.assertEqual(face["pose"], {"pitch": 1.5, "roll": -2.5, "yaw": 3.5})
        self.assertEqual(face["gaze"], {"x": 0.1, "y": 0.2, "z": 0.3})
        self.assertEqual(face["landmarks"], [{"x": 11.0, "y": 21.0, "z": 31.0}])
        self.assertEqual(
            face["mesh"],
            [{"x": 101.0, "y": 201.0, "z": 0.1}, {"x": 102.0, "y": 202.0, "z": 0.2}],
        )
        self.assertEqual(face["landmark_count"], 1)
        self.assertEqual(face["mesh_count"], 2)

    def test_normalize_result_maps_detector_v2_capitalized_emotions(self):
        row = {
            "Neutral": 0.11,
            "Happy": 0.72,
            "Sad": 0.04,
            "Surprise": 0.03,
            "Fear": 0.02,
            "Disgust": 0.01,
            "Anger": 0.07,
        }

        normalized = normalize_result(pd.DataFrame([row]), image_shape=(120, 160, 3), latency_ms=50)

        face = normalized["faces"][0]
        self.assertEqual(face["emotions"][0], {"label": "happiness", "value": 0.72})
        self.assertIn({"label": "neutral", "value": 0.11}, face["emotions"])

    def test_label_sets_are_large_enough_for_demo(self):
        self.assertGreaterEqual(len(EMOTION_LABELS), 7)
        self.assertGreaterEqual(len(AU_LABELS), 8)
        self.assertEqual(set(AU_LABELS), set(AU_DESCRIPTIONS))


if __name__ == "__main__":
    unittest.main()
