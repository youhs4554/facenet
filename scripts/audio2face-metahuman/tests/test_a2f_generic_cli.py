import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "run-a2f-metahuman.py"
LEGACY = ROOT / "run-a2f-taro-official.py"
UE_PYTHON = (
    ROOT.parents[1]
    / ".tools/audio2face-metahuman/KairosSample/Content/Python"
)


def load_canonical():
    spec = importlib.util.spec_from_file_location("run_a2f_metahuman", CANONICAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenericCLIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_canonical()

    def test_canonical_command_owns_parser_and_generic_defaults(self):
        args = self.module.parse_args(["input.wav"])
        self.assertEqual(args.avatar, "Taro")
        self.assertEqual(args.progress, "auto")
        self.assertEqual(self.module.CANONICAL_COMMAND, "run-a2f-metahuman.py")

    def test_legacy_wrapper_preserves_help_stdout_and_exit_code(self):
        canonical = subprocess.run(
            [sys.executable, str(CANONICAL), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        legacy = subprocess.run(
            [sys.executable, str(LEGACY), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(canonical.returncode, 0)
        self.assertEqual(legacy.returncode, canonical.returncode)
        self.assertEqual(legacy.stdout, canonical.stdout)
        self.assertIn("deprecated", legacy.stderr.casefold())
        self.assertNotIn("deprecated", canonical.stderr.casefold())

    def test_generic_helpers_exist_and_old_names_are_import_shims(self):
        capture = UE_PYTHON / "a2f_metahuman_capture.py"
        capture_shim = UE_PYTHON / "a2f_taro_capture.py"
        mrq = UE_PYTHON / "a2f_metahuman_movie_pipeline_executor.py"
        mrq_shim = UE_PYTHON / "a2f_taro_movie_pipeline_executor.py"
        self.assertTrue(capture.is_file())
        self.assertTrue(mrq.is_file())
        self.assertIn("a2f_metahuman_capture", capture_shim.read_text())
        self.assertIn("a2f_metahuman_movie_pipeline_executor", mrq_shim.read_text())

    def test_capture_helper_accepts_safe_hyphenated_official_asset_segments(self):
        capture_source = (UE_PYTHON / "a2f_metahuman_capture.py").read_text()
        self.assertIn(
            'UNREAL_NAME = r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*"',
            capture_source,
        )

    def test_face_focused_profile_is_run_owned_and_uses_proven_safe_material(self):
        capture_source = (UE_PYTHON / "a2f_metahuman_capture.py").read_text()
        cli_source = CANONICAL.read_text()
        self.assertIn('"avatar_visual_profile": args.avatar_visual_profile', cli_source)
        self.assertIn('"face-focused-vulkan-safe"', capture_source)
        self.assertIn("M_TaroTop_VulkanSafe", capture_source)
        self.assertIn('("Legs", "Feet")', capture_source)
        self.assertIn("set_material", capture_source)

    def test_init_hook_and_cli_use_generic_environment_contract(self):
        init_source = (UE_PYTHON / "init_unreal.py").read_text()
        cli_source = CANONICAL.read_text()
        self.assertIn("A2F_METAHUMAN_CAPTURE_CONFIG", init_source)
        self.assertIn("A2F_METAHUMAN_MRQ_CONFIG", cli_source)
        self.assertNotIn("A2F_TARO_CAPTURE_CONFIG", cli_source)


if __name__ == "__main__":
    unittest.main()
