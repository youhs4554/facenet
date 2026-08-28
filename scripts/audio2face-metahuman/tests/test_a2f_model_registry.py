import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "a2f_model_registry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_model_registry", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class A2FModelRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_default_profile_is_v30_diffusion(self):
        profile = self.module.resolve_model_profile(None)
        self.assertEqual(profile["id"], "v3.0-diffusion")
        self.assertEqual(profile["runtime"], "nim-2.0-remote")
        self.assertEqual(profile["model"], "Audio2Face-3D-v3.0")
        self.assertEqual(profile["default_endpoint"], "127.0.0.1:52100")

    def test_v3_profile_is_pinned_official_diffusion(self):
        profile = self.module.resolve_model_profile("v3.0-diffusion")
        self.assertEqual(profile["architecture"], "transformer-diffusion")
        self.assertEqual(
            profile["sdk_commit"],
            "1ca0f02535ed774f5dbcd724a31cd486368dc783",
        )
        self.assertEqual(
            profile["model_revision"],
            "b74132732fd9a9d29b237bec193ded64c9745e91",
        )
        self.assertEqual(profile["license"], "NVIDIA Open Model License")
        self.assertEqual(profile["runtime"], "nim-2.0-remote")
        self.assertEqual(profile["offline_fallback_runtime"], "a2f-sdk-local-offline")
        self.assertEqual(profile["client_request_config"], "config_claire.yml")
        self.assertEqual(
            profile["client_config_role"], "shared-claire-request-header"
        )

    def test_explicit_v23_profile_remains_supported(self):
        profile = self.module.resolve_model_profile("v2.3-regression")
        self.assertEqual(profile["architecture"], "regression")
        self.assertEqual(profile["default_endpoint"], "127.0.0.1:52000")
        self.assertEqual(profile["client_request_config"], "config_claire.yml")

    def test_v3_preflight_accepts_ampere_but_rejects_old_sdk_stack(self):
        supported = self.module.evaluate_v3_preflight(
            compute_capability=8.6,
            cuda_version="12.9",
            tensorrt_version="10.13",
            model_present=True,
            sdk_runner_present=True,
        )
        self.assertTrue(supported["supported"])
        unsupported = self.module.evaluate_v3_preflight(
            compute_capability=8.6,
            cuda_version="12.0",
            tensorrt_version="10.9",
            model_present=True,
            sdk_runner_present=True,
        )
        self.assertFalse(unsupported["supported"])
        self.assertIn("CUDA", " ".join(unsupported["reasons"]))
        self.assertIn("TensorRT", " ".join(unsupported["reasons"]))

    def test_v3_runner_command_is_fixed_and_records_identity_emotions(self):
        command = self.module.build_v3_runner_command(
            runner=Path("/sdk/bin/a2f-v3-export"),
            audio=Path("/run/test.wav"),
            model=Path("/models/v3/model.json"),
            output_dir=Path("/run/v3"),
            identity=0,
            emotion_csv=Path("/run/emotions.csv"),
            device=0,
        )
        self.assertEqual(command[0], "/sdk/bin/a2f-v3-export")
        self.assertIn("--architecture", command)
        self.assertIn("diffusion", command)
        self.assertIn("--identity", command)
        self.assertIn("0", command)
        self.assertNotIn("sh", command)

    def test_v3_blendshape_csv_requires_finite_monotonic_68(self):
        names = self.module.A2F_68_NAMES
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blendshapes.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["frame_index", "time_seconds"] + list(names))
                writer.writerow([0, 0.0] + [0.0] * 68)
                writer.writerow([1, 1 / 30] + [0.1] * 68)
            result = self.module.validate_v3_blendshape_csv(path)
        self.assertEqual(result["frames"], 2)
        self.assertEqual(result["curves"], 68)
        self.assertTrue(result["finite"])

    def test_unknown_model_name_is_never_guessed(self):
        with self.assertRaises(self.module.ModelProfileError):
            self.module.resolve_model_profile("v3-magic")

    def test_model_output_cadence_rejects_v2_frames_relabelled_as_v3(self):
        v3 = self.module.validate_model_output_cadence(
            "v3.0-diffusion",
            frames=218,
            first_timecode=0.0,
            last_timecode=3.616625,
            output_frames=109,
        )
        self.assertEqual(v3["cadence"], "diffusion-approximately-60fps")
        self.assertGreater(v3["source_fps"], 59.0)
        with self.assertRaises(self.module.ModelProfileError):
            self.module.validate_model_output_cadence(
                "v3.0-diffusion",
                frames=109,
                first_timecode=0.0,
                last_timecode=3.6,
                output_frames=109,
            )
        v2 = self.module.validate_model_output_cadence(
            "v2.3-regression",
            frames=109,
            first_timecode=0.0,
            last_timecode=3.6,
            output_frames=109,
        )
        self.assertEqual(v2["cadence"], "regression-30fps")


if __name__ == "__main__":
    unittest.main()
