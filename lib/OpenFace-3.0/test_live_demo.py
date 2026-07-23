import unittest
from unittest import mock

import numpy as np
import torch


class LiveDemoHelperTests(unittest.TestCase):
    def test_parse_source_uses_int_for_camera_index(self):
        from live_demo import parse_source

        self.assertEqual(parse_source("0"), 0)
        self.assertEqual(parse_source("2"), 2)
        self.assertEqual(parse_source("images/test.avi"), "images/test.avi")

    def test_select_device_prefers_mps_when_cuda_is_unavailable(self):
        from live_demo import select_device

        self.assertEqual(select_device("", cuda_available=False, mps_available=True), "mps")
        self.assertEqual(select_device("", cuda_available=False, mps_available=False), "cpu")
        self.assertEqual(select_device("cpu", cuda_available=True, mps_available=True), "cpu")

    @unittest.skipUnless(torch.backends.mps.is_available(), "MPS is not available")
    def test_au_graph_normalization_preserves_mps_device(self):
        from model.AU_model import normalize_digraph

        adjacency = torch.eye(4, device="mps").view(1, 4, 4)
        normalized = normalize_digraph(adjacency)
        self.assertEqual(normalized.device.type, "mps")

    def test_scaled_bbox_is_clamped_to_frame(self):
        from live_demo import scale_and_clip_bbox

        bbox = scale_and_clip_bbox((10, 20, 30, 60), scale_factor=0.5, frame_shape=(70, 35, 3))
        self.assertEqual(bbox, (0, 0, 35, 70))

    def test_eye_points_prefer_wflw_pupils(self):
        from live_demo import eye_points

        landmarks = np.zeros((98, 2), dtype=np.float32)
        landmarks[96] = [11, 22]
        landmarks[97] = [33, 44]
        self.assertEqual(eye_points(landmarks), [(11, 22), (33, 44)])

    def test_is_image_source_recognizes_common_images(self):
        from live_demo import is_image_source

        self.assertTrue(is_image_source("images/89.jpg"))
        self.assertTrue(is_image_source("frame.PNG"))
        self.assertFalse(is_image_source("0"))
        self.assertFalse(is_image_source("images/test.avi"))

    def test_au_labels_include_english_meanings(self):
        from live_demo import AU_LABELS

        self.assertIn("AU12 - Lip Corner Puller", AU_LABELS)
        self.assertIn("AU26 - Jaw Drop", AU_LABELS)

    def test_au_row_positions_fit_small_frames(self):
        from live_demo import AU_LABELS, au_row_positions

        rows = au_row_positions(224, len(AU_LABELS))
        self.assertEqual(len(rows), 8)
        self.assertGreaterEqual(rows[0], 48)
        self.assertLessEqual(rows[-1], 208)

    def test_analyze_frame_can_skip_gaze_overlay(self):
        from live_demo import analyze_frame

        class FakeAlignment:
            def analyze(self, image, scale, center_w, center_h):
                return np.zeros((98, 2), dtype=np.float32)

        class FakeModel:
            def __call__(self, image):
                return (
                    torch.zeros((1, 8), dtype=torch.float32),
                    torch.zeros((1, 2), dtype=torch.float32),
                    torch.zeros((1, 8), dtype=torch.float32),
                )

        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        detections = np.array([[10, 10, 50, 50, 0.95, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]], dtype=np.float32)
        transform = lambda image: torch.zeros((3, 224, 224), dtype=torch.float32)

        with (
            mock.patch("live_demo.detect_faces", return_value=detections),
            mock.patch("live_demo.draw_gaze", side_effect=lambda image, gaze, points: image) as draw_gaze,
        ):
            analyze_frame(
                frame,
                retinaface_model=object(),
                retina_cfg={},
                alignment=FakeAlignment(),
                multitask_model=FakeModel(),
                transform=transform,
                device=torch.device("cpu"),
                min_conf=0.7,
                include_au_panel=False,
                include_gaze=False,
            )

        draw_gaze.assert_not_called()


if __name__ == "__main__":
    unittest.main()
