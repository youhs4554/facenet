import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MotionVisualizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motion = load("a2f_motion")
        cls.viz = load("a2f_motion_viz")

    def test_top_k_is_deterministic_and_uses_canonical_tie_break(self):
        raw = self.motion.synthetic_motion_series(frame_count=3)
        effective = self.motion.synthetic_motion_series(frame_count=3)
        for name in ("JawOpen", "BrowInnerUp"):
            index = self.motion.BLENDSHAPE_NAMES.index(name)
            effective["frames"][1]["values"][index] = 0.5
        first = self.viz.select_top_k(raw, effective, 2)
        second = self.viz.select_top_k(raw, effective, 2)
        self.assertEqual(first, second)
        self.assertEqual(first, ["JawOpen", "BrowInnerUp"])

    def test_panel_renders_all_68_top_k_emotions_and_frame_time(self):
        raw = self.motion.synthetic_motion_series(frame_count=2)
        emotions = self.motion.synthetic_emotion_series(frame_count=2)
        image, metadata = self.viz.render_motion_panel(
            raw,
            raw,
            emotions,
            frame_index=1,
            width=960,
            height=1080,
            top_k=8,
        )
        self.assertEqual(image.size, (960, 1080))
        self.assertEqual(metadata["curve_count"], 68)
        self.assertEqual(metadata["emotion_count"], 10)
        self.assertEqual(metadata["frame_index"], 1)
        self.assertAlmostEqual(metadata["time_seconds"], 1 / 30)
        self.assertEqual(len(metadata["top_k"]), 8)

    def test_compact_triptych_panel_has_readable_type_and_reduced_hierarchy(self):
        raw = self.motion.synthetic_motion_series(frame_count=2)
        effective = self.motion.synthetic_motion_series(frame_count=2)
        emotions = self.motion.synthetic_emotion_series(frame_count=2)
        jaw_index = self.motion.BLENDSHAPE_NAMES.index("JawOpen")
        joy_index = self.motion.EMOTION_NAMES.index("joy")
        effective["frames"][1]["values"][jaw_index] = 0.72
        emotions["frames"][1]["values"][joy_index] = 0.61
        image, metadata = self.viz.render_compact_motion_panel(
            raw,
            effective,
            emotions,
            frame_index=1,
            width=640,
            height=540,
            top_k=8,
            panel_identity={
                "panel_title": "A2F v3.0 DIFFUSION",
                "panel_model": "multi_v3.2",
                "panel_source": "EFFECTIVE / FINAL-RENDER",
            },
        )
        self.assertEqual(image.size, (640, 540))
        self.assertEqual(metadata["layout"], "triptych-compact-v3")
        self.assertGreaterEqual(metadata["minimum_font_px"], 16)
        self.assertEqual(metadata["displayed_curve_count"], 8)
        self.assertEqual(metadata["displayed_emotion_count"], 0)
        self.assertEqual(metadata["curve_count"], 68)
        self.assertEqual(metadata["top_k"][0], "JawOpen")
        self.assertEqual(metadata["sort"], "current_effective_value_descending")
        self.assertEqual(metadata["panel_title"], "A2F v3.0 DIFFUSION")
        self.assertEqual(metadata["panel_model"], "multi_v3.2")
        self.assertEqual(metadata["panel_source"], "EFFECTIVE / FINAL-RENDER")

    def test_compact_curve_rows_are_sorted_by_current_effective_value(self):
        raw = self.motion.synthetic_motion_series(frame_count=1)
        effective = self.motion.synthetic_motion_series(frame_count=1)
        emotions = self.motion.synthetic_emotion_series(frame_count=1)
        assigned = {
            "MouthClose": 0.2,
            "JawOpen": 0.8,
            "BrowInnerUp": 0.5,
            "CheekPuff": 0.35,
        }
        for name, value in assigned.items():
            effective["frames"][0]["values"][
                self.motion.BLENDSHAPE_NAMES.index(name)
            ] = value
        _, metadata = self.viz.render_compact_motion_panel(
            raw, effective, emotions, frame_index=0, top_k=4
        )
        self.assertEqual(
            metadata["top_k"],
            ["JawOpen", "BrowInnerUp", "CheekPuff", "MouthClose"],
        )
        self.assertEqual(metadata["displayed_values"], [0.8, 0.5, 0.35, 0.2])
        self.assertEqual(
            metadata["displayed_bar_pixels"],
            [
                int(metadata["bar_width_pixels"] * value)
                for value in [0.8, 0.5, 0.35, 0.2]
            ],
        )

    def test_final_render_top_curves_exclude_unconsumed_extended_tongue(self):
        raw = self.motion.synthetic_motion_series(frame_count=1)
        effective = self.motion.synthetic_motion_series(frame_count=1)
        emotions = self.motion.synthetic_emotion_series(frame_count=1)
        effective["frames"][0]["values"][
            self.motion.BLENDSHAPE_NAMES.index("TongueIn")
        ] = 1.0
        effective["frames"][0]["values"][
            self.motion.BLENDSHAPE_NAMES.index("JawOpen")
        ] = 0.8
        _, metadata = self.viz.render_compact_motion_panel(
            raw,
            effective,
            emotions,
            frame_index=0,
            top_k=1,
            active_curve_names=list(self.motion.ACE25_RENDER_CURVE_NAMES),
        )
        self.assertEqual(metadata["top_k"], ["JawOpen"])
        self.assertEqual(metadata["top_curve_scope"], "ACE2.5-consumed-52")
        self.assertEqual(metadata["reference_only_extended_tongue_count"], 16)

    def test_extended_pose_asset_profile_includes_tongue_in_as_active_curve(self):
        raw = self.motion.synthetic_motion_series(frame_count=1)
        effective = self.motion.synthetic_motion_series(frame_count=1)
        emotions = self.motion.synthetic_emotion_series(frame_count=1)
        effective["frames"][0]["values"][
            self.motion.BLENDSHAPE_NAMES.index("TongueIn")
        ] = 0.9
        _, metadata = self.viz.render_compact_motion_panel(
            raw,
            effective,
            emotions,
            frame_index=0,
            top_k=1,
            active_curve_names=list(
                self.motion.A2F_POSE_ASSET_EXTENDED_CURVE_NAMES
            ),
        )
        self.assertEqual(metadata["top_k"], ["TongueIn"])
        self.assertEqual(metadata["top_curve_scope"], "A2F-pose-asset-baked-68")
        self.assertEqual(metadata["reference_only_extended_tongue_count"], 0)

    def test_compact_panel_changes_when_geometry_driving_curve_changes(self):
        raw = self.motion.synthetic_motion_series(frame_count=2)
        effective = self.motion.synthetic_motion_series(frame_count=2)
        emotions = self.motion.synthetic_emotion_series(frame_count=2)
        first, _ = self.viz.render_compact_motion_panel(
            raw, effective, emotions, frame_index=0
        )
        jaw_index = self.motion.BLENDSHAPE_NAMES.index("JawOpen")
        effective["frames"][1]["values"][jaw_index] = 0.9
        second, _ = self.viz.render_compact_motion_panel(
            raw, effective, emotions, frame_index=1
        )
        self.assertNotEqual(first.tobytes(), second.tobytes())

    def test_render_frames_are_contiguous_and_repeatable(self):
        raw = self.motion.synthetic_motion_series(frame_count=3)
        emotions = self.motion.synthetic_emotion_series(frame_count=3)
        with tempfile.TemporaryDirectory() as temp_dir:
            first = self.viz.render_motion_frames(
                raw, raw, emotions, Path(temp_dir), width=320, height=240, top_k=4
            )
            hashes = [self.motion.sha256_file(path) for path in first]
            second = self.viz.render_motion_frames(
                raw, raw, emotions, Path(temp_dir), width=320, height=240, top_k=4
            )
            second_hashes = [self.motion.sha256_file(path) for path in second]
        self.assertEqual([path.name for path in first], ["frame.0000.png", "frame.0001.png", "frame.0002.png"])
        self.assertEqual(hashes, second_hashes)

    def test_hstack_command_preserves_avatar_audio_and_sync_contract(self):
        command = self.viz.build_hstack_command(
            ffmpeg=Path("/tools/ffmpeg"),
            avatar=Path("/run/avatar.mp4"),
            visualization=Path("/run/viz.mp4"),
            output=Path("/run/comparison.mp4"),
            fps=30,
            frame_count=109,
        )
        joined = " ".join(map(str, command))
        self.assertIn("hstack=inputs=2", joined)
        self.assertIn("-map 0:a:0", joined)
        self.assertIn("-c:a copy", joined)
        self.assertIn("-frames:v 109", joined)
        self.assertNotIn("-shortest", command)
        self.assertNotIn("shell=True", joined)

    def test_baseline_enhanced_hstack_uses_matching_audio_once(self):
        command = self.viz.build_avatar_comparison_command(
            ffmpeg=Path("/tools/ffmpeg"),
            baseline=Path("/run/base.mp4"),
            enhanced=Path("/run/enhanced.mp4"),
            output=Path("/run/base-vs-enhanced.mp4"),
            fps=30,
            frame_count=109,
        )
        joined = " ".join(map(str, command))
        self.assertIn("hstack=inputs=2", joined)
        self.assertIn("-map 1:a:0", joined)
        self.assertIn("-c:a copy", joined)


if __name__ == "__main__":
    unittest.main()
