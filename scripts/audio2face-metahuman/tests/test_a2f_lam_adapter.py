import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "a2f_lam_adapter.py"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_lam_adapter", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LamAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_revisions_and_model_identity_are_pinned(self):
        self.assertEqual(
            self.module.LAM_A2E_GIT_SHA,
            "02a703c3ea7d8e360eb43098eca85ee98a083529",
        )
        self.assertEqual(
            self.module.LAM_A2E_HF_REVISION,
            "0fe5f4dbb283ec7d9c01688681e6e4b6ac314858",
        )
        self.assertEqual(self.module.ADAPTER_SCOPE, "reference_artifacts_only")

    def test_52_arkit_values_map_only_to_common_a2f_curves(self):
        values = [[index / 100.0 for index in range(52)]]
        result = self.module.map_lam52_to_a2f(values, fps=30.0)
        self.assertEqual(len(result["curve_names"]), 68)
        self.assertEqual(result["frames"][0]["time_seconds"], 0.0)
        self.assertEqual(sum(result["availability"]), 52)
        for name in self.module.TONGUE_CURVES:
            index = result["curve_names"].index(name)
            self.assertFalse(result["availability"][index])
            self.assertIsNone(result["frames"][0]["values"][index])

    def test_adapter_command_is_fixed_argv_and_has_no_shell(self):
        command = self.module.build_lam_inference_command(
            python=Path("/lam/.venv/bin/python"),
            repo=Path("/lam/repo"),
            audio=Path("/input/test.wav"),
            output_json=Path("/run/lam.json"),
            checkpoint=Path("/lam/weights.tar"),
        )
        self.assertEqual(command[1], "/lam/repo/inference.py")
        self.assertIn("--config-file", command)
        self.assertIn("--options", command)
        self.assertIn("audio_input=/input/test.wav", command)
        self.assertIn("save_json_path=/run/lam.json", command)
        self.assertNotIn("sh", command)


if __name__ == "__main__":
    unittest.main()
