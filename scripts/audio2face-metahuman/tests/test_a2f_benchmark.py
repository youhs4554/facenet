import importlib.util
import json
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


class A2FBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motion = load("a2f_motion")
        cls.benchmark = load("a2f_benchmark")

    def test_region_metrics_are_time_normalized_across_30_and_60_fps(self):
        base = self.motion.synthetic_motion_series(frame_count=4, fps=30.0)
        candidate = self.motion.synthetic_motion_series(frame_count=7, fps=60.0)
        jaw = self.motion.BLENDSHAPE_NAMES.index("JawOpen")
        for frame in base["frames"]:
            frame["values"][jaw] = frame["time_seconds"] * 2.0
        for frame in candidate["frames"]:
            frame["values"][jaw] = frame["time_seconds"] * 2.0
        left = self.benchmark.summarize_motion(base)
        right = self.benchmark.summarize_motion(candidate)
        self.assertAlmostEqual(
            left["curves"]["JawOpen"]["velocity_abs_mean_per_second"],
            right["curves"]["JawOpen"]["velocity_abs_mean_per_second"],
        )
        self.assertAlmostEqual(left["inferred_fps"], 30.0)
        self.assertAlmostEqual(right["inferred_fps"], 60.0)

    def test_comparison_reports_regions_emotions_and_no_fake_naturalness_score(self):
        base = self.motion.synthetic_motion_series(frame_count=4, fps=30.0)
        candidate = self.motion.synthetic_motion_series(frame_count=4, fps=30.0)
        jaw = self.motion.BLENDSHAPE_NAMES.index("JawOpen")
        candidate["frames"][1]["values"][jaw] = 0.5
        base_emotion = self.motion.synthetic_emotion_series(frame_count=4, fps=30.0)
        candidate_emotion = self.motion.synthetic_emotion_series(frame_count=4, fps=30.0)
        joy = self.motion.EMOTION_NAMES.index("joy")
        candidate_emotion["frames"][2]["values"][joy] = 0.8
        report = self.benchmark.compare_model_outputs(
            base,
            candidate,
            baseline_emotions=base_emotion,
            candidate_emotions=candidate_emotion,
            baseline_id="v2.3-regression",
            candidate_id="v3.0-diffusion",
        )
        self.assertGreater(report["candidate"]["regions"]["jaw"]["range_mean"], 0.0)
        self.assertGreater(report["candidate"]["emotions"]["joy"]["range"], 0.0)
        self.assertIn("temporal_second_derivative_abs_mean", report["candidate"]["curves"]["JawOpen"])
        self.assertNotIn("naturalness_score", json.dumps(report))

    def test_report_writer_is_canonical_and_hashed(self):
        report = {"schema_version": 1, "baseline_id": "a", "candidate_id": "b"}
        with tempfile.TemporaryDirectory() as temp_dir:
            record = self.benchmark.write_benchmark_report(
                report, Path(temp_dir) / "report.json"
            )
            self.assertEqual(record["sha256"], self.motion.sha256_file(Path(record["path"])))


if __name__ == "__main__":
    unittest.main()
