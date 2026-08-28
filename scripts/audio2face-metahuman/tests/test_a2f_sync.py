import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "a2f_sync.py"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_sync", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class A2FSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_final_render_timeline_preserves_recorded_capture_basis(self):
        policy = self.module.capture_timeline_policy("final_render")
        self.assertEqual(policy["curve_key_time_origin"], "recorded_capture")
        self.assertEqual(policy["sequence_start_offset"], "capture_offset")
        self.assertEqual(policy["content_sync_correction"], "verified_post_render")

    def test_artifact_only_timeline_keeps_recorded_capture_offset(self):
        policy = self.module.capture_timeline_policy("artifact_only")
        self.assertEqual(policy["curve_key_time_origin"], "recorded_capture")
        self.assertEqual(policy["sequence_start_offset"], "capture_offset")

    def test_visual_lag_estimator_detects_four_frame_delay(self):
        rng = np.random.default_rng(7)
        curve = rng.normal(size=120)
        delayed = np.concatenate([np.zeros(4), curve[:-4]])
        frames = np.stack(
            [delayed, delayed * 0.4 + rng.normal(scale=0.01, size=120)], axis=1
        )
        result = self.module.estimate_visual_curve_lag(
            frames, curve, max_lag_frames=8, component_count=2
        )
        self.assertEqual(result["lag_frames"], 4)
        self.assertGreater(result["correlation"], 0.99)

    def test_visual_lag_estimator_reports_zero_for_aligned_motion(self):
        curve = np.sin(np.linspace(0.0, 13.0, 120))
        frames = np.stack([curve, curve * -0.2], axis=1)
        result = self.module.estimate_visual_curve_lag(
            frames, curve, max_lag_frames=8, component_count=2
        )
        self.assertEqual(result["lag_frames"], 0)
        self.assertGreater(result["correlation"], 0.99)

    def test_positive_lag_correction_trims_then_pads_video(self):
        command = self.module.build_avatar_sync_correction_command(
            ffmpeg=Path("/tools/ffmpeg"),
            source=Path("/run/input.mp4"),
            output=Path("/run/corrected.mp4"),
            lag_frames=4,
            fps=30,
            frame_count=109,
        )
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("trim=start_frame=4", graph)
        self.assertIn("tpad=stop_mode=clone:stop_duration=0.133333333", graph)
        self.assertEqual(command[-1], "/run/corrected.mp4")

    def test_negative_lag_correction_pads_then_trims_video(self):
        command = self.module.build_avatar_sync_correction_command(
            ffmpeg=Path("/tools/ffmpeg"),
            source=Path("/run/input.mp4"),
            output=Path("/run/corrected.mp4"),
            lag_frames=-3,
            fps=30,
            frame_count=109,
        )
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("tpad=start_mode=clone:start_duration=0.100000000", graph)
        self.assertIn("trim=end_frame=109", graph)

    def test_master_frame_map_uses_audio_time_once_for_all_panels(self):
        curve_names = [f"Curve{index}" for index in range(68)]
        curve_names[17] = "JawOpen"
        raw = []
        effective = []
        for index in range(61):
            source_mapping = {
                "target_time_seconds": index / 30.0,
                "left_frame_index": index * 2,
                "right_frame_index": index * 2,
                "left_time_seconds": index / 30.0,
                "right_time_seconds": index / 30.0,
                "interpolation_alpha": 0.0,
            }
            raw_frame = {
                "frame_index": index,
                "time_seconds": index / 30.0,
                "values": [0.0] * 68,
                "source_mapping": source_mapping,
            }
            raw.append(raw_frame)
            effective.append(
                {
                    **raw_frame,
                    "values": [0.0] * 68,
                    "source_mapping": dict(source_mapping),
                }
            )
        effective[30]["values"][17] = 1.0
        records = self.module.build_master_frame_map(
            raw_frames=raw,
            effective_frames=effective,
            curve_names=curve_names,
            fps=30,
            frame_count=61,
            avatar_lag_frames=5,
            top_k=1,
        )
        pulse = records[30]
        self.assertEqual(pulse["pts_seconds"], 1.0)
        self.assertEqual(pulse["audio_time_seconds"], 1.0)
        self.assertEqual(pulse["panel_source_frame"], 30)
        self.assertEqual(pulse["mannequin_source_frame"], 30)
        self.assertEqual(pulse["avatar_source_frame"], 35)
        self.assertEqual(
            pulse["top_curves"][0],
            {"name": "JawOpen", "raw": 0.0, "effective": 1.0},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            record = self.module.write_frame_map_jsonl(
                records, Path(temp_dir) / "frame-map.jsonl"
            )
            self.assertEqual(record["frame_count"], 61)
            self.assertEqual(record["first_pts_seconds"], 0.0)
            self.assertEqual(record["last_pts_seconds"], 2.0)

    def test_recorded_curve_key_sampling_is_linear_at_audio_aligned_time(self):
        self.assertAlmostEqual(
            self.module.interpolate_curve_keys(
                [0.0, 0.5, 1.0], [0.0, 0.8, 0.0], 0.75
            ),
            0.4,
        )
        self.assertEqual(
            self.module.interpolate_curve_keys(
                [0.0, 0.5, 1.0], [0.0, 0.8, 0.0], -1.0
            ),
            0.0,
        )
        expected = [
            {
                "frame_index": 30,
                "time_seconds": 1.0,
                "values": [0.2, 0.7],
            }
        ]
        result = self.module.verify_recorded_curve_samples(
            recorded=[
                {
                    "output_frame": 30,
                    "audio_time_seconds": 1.0,
                    "curves": {"JawOpen": 0.2, "MouthClose": 0.7},
                }
            ],
            effective_frames=expected,
            curve_names=["JawOpen", "MouthClose"],
            tolerance=1e-6,
        )
        self.assertTrue(result["valid"])
        with self.assertRaises(self.module.A2FSyncError):
            self.module.verify_recorded_curve_samples(
                recorded=[
                    {
                        "output_frame": 30,
                        "audio_time_seconds": 1.0,
                        "curves": {"JawOpen": 0.3, "MouthClose": 0.7},
                    }
                ],
                effective_frames=expected,
                curve_names=["JawOpen", "MouthClose"],
                tolerance=1e-6,
            )


if __name__ == "__main__":
    unittest.main()
