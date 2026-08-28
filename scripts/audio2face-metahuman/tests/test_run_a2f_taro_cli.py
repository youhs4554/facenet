import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run-a2f-taro-cli.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_a2f_taro_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class A2FTaroCliUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_safe_name_rejects_empty_or_path_like_input(self):
        self.assertEqual(self.module.safe_name("My demo 01"), "my-demo-01")
        self.assertEqual(self.module.safe_name("../../unsafe"), "unsafe")
        with self.assertRaises(ValueError):
            self.module.safe_name("---")

    def test_build_ue_command_is_dedicated_and_offscreen(self):
        command = self.module.build_ue_command(
            editor=Path("/opt/UnrealEditor"),
            project=Path("/work/KairosSample.uproject"),
            map_path="/Game/Maps/TaroA2F/TaroFaceBodyDemo",
            bootstrap=Path("/work/ue_a2f_cli_pipeline.py"),
            ue_log=Path("/runs/ue.log"),
            graphics_adapter=0,
            inference_mode="low-latency",
        )
        joined = " ".join(map(str, command))
        self.assertIn("-RenderOffscreen", command)
        self.assertIn("-Multiprocess", command)
        self.assertIn("-Unattended", command)
        self.assertIn("-A2FCLIAutomation", command)
        self.assertFalse(
            any(argument.startswith("-ExecutePythonScript=") for argument in command)
        )
        self.assertFalse(any(argument.startswith("-ExecCmds=py") for argument in command))
        self.assertIn("-abslog=/runs/ue.log", command)
        self.assertIn("-A2FDemoMode=low-latency", command)
        self.assertNotIn("-A2FLatencyExit", joined)

    def test_validate_final_probe_accepts_expected_av_contract(self):
        probe = {
            "format": {"duration": "3.633333", "start_time": "0.000000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                    "start_time": "0.000000",
                    "duration": "3.633333",
                    "nb_frames": "109",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 1,
                    "start_time": "0.000000",
                    "duration": "3.626000",
                },
            ],
        }
        result = self.module.validate_final_probe(
            probe,
            expected_frames=109,
            fps=30,
            width=1920,
            height=1080,
        )
        self.assertEqual(result["video_codec"], "h264")
        self.assertEqual(result["audio_codec"], "aac")
        self.assertEqual(result["av_start_delta_ms"], 0.0)
        self.assertLess(result["duration_delta_ms"], 34.0)

    def test_validate_final_probe_rejects_missing_audio(self):
        probe = {
            "format": {"duration": "1.0"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                    "start_time": "0.0",
                    "duration": "1.0",
                    "nb_frames": "30",
                }
            ],
        }
        with self.assertRaises(self.module.PipelineError) as caught:
            self.module.validate_final_probe(
                probe,
                expected_frames=30,
                fps=30,
                width=1920,
                height=1080,
            )
        self.assertEqual(caught.exception.exit_code, self.module.ExitCode.VALIDATION)

    def test_inventory_frames_requires_contiguous_numbers_and_motion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frames = Path(temp_dir)
            for number, payload in enumerate((b"a", b"b", b"c")):
                (frames / f"frame.{number:04d}.png").write_bytes(payload)
            inventory = self.module.inventory_frames(
                frames, "frame.%04d.png", expected_frames=3
            )
            self.assertEqual(inventory["count"], 3)
            self.assertEqual(inventory["first_number"], 0)
            self.assertEqual(inventory["last_number"], 2)
            self.assertEqual(inventory["unique_sample_hashes"], 3)

    def test_atomic_manifest_update_preserves_valid_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            self.module.atomic_write_json(path, {"status": "running", "stage": "ue"})
            self.module.atomic_write_json(path, {"status": "success", "stage": "done"})
            self.assertEqual(
                json.loads(path.read_text()),
                {"stage": "done", "status": "success"},
            )
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
