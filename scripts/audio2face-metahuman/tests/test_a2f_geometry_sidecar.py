import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "sdk-v3-geometry"
MODULE = ROOT / "a2f_geometry_sidecar.py"
BUILD_ENGINE = SIDECAR / "build_engine.py"
VERIFY_OUTPUTS = SIDECAR / "verify_outputs.py"
DIRECT_VIZ = SIDECAR / "render_direct_geometry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_geometry_sidecar", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_path_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GeometrySidecarContractTests(unittest.TestCase):
    def test_container_is_digest_and_version_pinned_without_secrets(self):
        dockerfile = (SIDECAR / "Dockerfile").read_text()
        self.assertIn(
            "nvidia/cuda:12.8.1-devel-ubuntu22.04@sha256:6617a625", dockerfile
        )
        self.assertIn("tensorrt-cu12-libs==10.13.3.9", dockerfile)
        self.assertIn("94e2b9ef6d2cce74c76cdad499cca36cc4949197", dockerfile)
        self.assertIn("1ca0f02535ed774f5dbcd724a31cd486368dc783", dockerfile)
        for forbidden in ("HF_TOKEN", "NGC_API_KEY", "--privileged", "/usr/local/cuda:"):
            self.assertNotIn(forbidden, dockerfile)

    def test_compose_confines_gpu_and_mounts_source_data_read_only(self):
        compose = (SIDECAR / "compose.yaml").read_text()
        self.assertIn('device_ids: ["1"]', compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("no-new-privileges:true", compose)
        self.assertIn("cap_drop:", compose)
        self.assertIn("/models:ro", compose)
        self.assertIn(":/input/test.wav:ro", compose)
        self.assertIn(":/input/emotions.csv:ro", compose)
        self.assertIn("/output:rw", compose)
        self.assertNotIn("/var/run/docker.sock", compose)

    def test_exporter_uses_official_diffusion_geometry_and_solver_apis(self):
        source = (SIDECAR / "geometry_exporter.cpp").read_text()
        self.assertIn("ReadDiffusionGeometryExecutorBundle", source)
        self.assertIn("ExecutionOption::All", source)
        self.assertIn("ReadDiffusionBlendshapeSolveExecutorBundle", source)
        for field in ("skinGeometry", "tongueGeometry", "jawTransform", "eyesRotation"):
            self.assertIn(field, source)
        self.assertIn("constantNoise", source)
        self.assertIn("identityIndex", source)
        self.assertIn("constexpr bool useGpuSolver = true", source)
        self.assertIn("IBlendshapeExecutor::DeviceResults", source)


class GeometrySidecarEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_path_module("a2f_build_engine", BUILD_ENGINE)

    def test_official_default_build_options_preserve_units_and_fp32(self):
        info = {
            "trt_build_param": {
                "cuda_in_graphics": ["--memPoolSize=tacticSharedMem:0.046875"],
                "batch": [
                    "--minShapes=window:1x16000,identity:1x3",
                    "--optShapes=window:{OPT_BATCH_SIZE}x16000,identity:{OPT_BATCH_SIZE}x3",
                    "--maxShapes=window:{MAX_BATCH_SIZE}x16000,identity:{MAX_BATCH_SIZE}x3",
                ],
            },
            "defaults": {"OPT_BATCH_SIZE": 3, "MAX_BATCH_SIZE": 8},
        }
        options = self.module.resolve_build_options(info, batch_size=1)
        self.assertEqual(options["precision"], "fp32")
        self.assertEqual(options["memory_pools"]["tacticSharedMem"], 49_152)
        self.assertNotIn("workspace", options["memory_pools"])
        self.assertEqual(options["shapes"]["optShapes"]["window"], (1, 16000))
        self.assertEqual(options["shapes"]["maxShapes"]["identity"], (1, 3))

    def test_precision_is_enabled_only_when_official_info_requests_it(self):
        info = {
            "trt_build_param": {
                "fp16": ["--fp16"],
                "batch": [
                    "--minShapes=x:1x2", "--optShapes=x:1x2", "--maxShapes=x:1x2"
                ],
            }
        }
        self.assertEqual(
            self.module.resolve_build_options(info, batch_size=1)["precision"], "fp16"
        )

    def test_nim_fp16_profile_is_explicit_and_does_not_change_official_default(self):
        info = {
            "trt_build_param": {
                "batch": [
                    "--minShapes=x:1x2", "--optShapes=x:1x2", "--maxShapes=x:1x2"
                ]
            }
        }
        official = self.module.resolve_build_options(info, batch_size=1)
        nim = self.module.resolve_build_options(
            info, batch_size=1, precision_profile="nim-fp16"
        )
        self.assertEqual(official["precision"], "fp32")
        self.assertEqual(nim["precision"], "fp16")
        self.assertEqual(nim["precision_source"], "explicit-nim-comparison-profile")

    def test_engine_manifest_rejects_stale_or_modified_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            onnx = root / "network.onnx"
            trt_info = root / "trt_info.json"
            engine = root / "network.trt"
            manifest = root / "engine-manifest.json"
            onnx.write_bytes(b"onnx-v1")
            trt_info.write_text('{"trt_build_param": {"batch": []}}')
            engine.write_bytes(b"engine-v1")
            payload = self.module.engine_manifest_payload(
                onnx=onnx,
                trt_info=trt_info,
                engine=engine,
                build_options={"precision": "fp32"},
                tensorrt_version="10.13.3.9",
                compute_capability="8.6",
            )
            manifest.write_text(json.dumps(payload))
            verified = self.module.verify_engine_manifest(
                onnx=onnx, trt_info=trt_info, engine=engine, manifest=manifest
            )
            self.assertEqual(verified["status"], "pass")
            engine.write_bytes(b"engine-v2")
            with self.assertRaisesRegex(RuntimeError, "engine_sha256"):
                self.module.verify_engine_manifest(
                    onnx=onnx, trt_info=trt_info, engine=engine, manifest=manifest
                )


class GeometrySidecarPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_vram_gate_never_stops_existing_services(self):
        with mock.patch.object(
            self.module, "gpu_inventory", return_value={"index": 1, "free_mib": 2614}
        ), mock.patch.object(self.module.subprocess, "run") as run:
            report = self.module.runtime_preflight(minimum_free_mib=4096)
        self.assertEqual(report["status"], "blocked_vram")
        self.assertFalse(report["phase_b_runtime_allowed"])
        run.assert_not_called()

    def test_sufficient_vram_allows_runtime_without_mutating_host(self):
        with mock.patch.object(
            self.module, "gpu_inventory", return_value={"index": 1, "free_mib": 8192}
        ):
            report = self.module.runtime_preflight(minimum_free_mib=4096)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["phase_b_runtime_allowed"])

    def test_host_snapshot_is_a_successful_non_mutating_boundary(self):
        completed = mock.Mock(returncode=1)
        with mock.patch.object(
            self.module,
            "gpu_inventory",
            side_effect=lambda index=1: {"index": index, "free_mib": 8192},
        ), mock.patch.object(
            self.module,
            "_run",
            side_effect=lambda argv: "" if argv[0] in {"docker", "pgrep"} else "nvcc",
        ), mock.patch.object(self.module.subprocess, "run", return_value=completed):
            report = self.module.host_snapshot()
        self.assertEqual(report["status"], "pass")
        self.assertNotIn("tokens", report)

    def test_gpu_inventory_parses_requested_device_and_rejects_missing_index(self):
        rows = (
            "0, Quadro RTX 5000, 7.5, 16384, 1, 15927, 580.173.02\n"
            "1, NVIDIA RTX A4500, 8.6, 20470, 17429, 2614, 580.173.02"
        )
        with mock.patch.object(self.module, "_run", return_value=rows):
            gpu = self.module.gpu_inventory(1)
            self.assertEqual(gpu["name"], "NVIDIA RTX A4500")
            self.assertEqual(gpu["free_mib"], 2614)
            with self.assertRaises(RuntimeError):
                self.module.gpu_inventory(2)

    def test_preflight_and_snapshot_comparison_validate_error_paths(self):
        with self.assertRaises(ValueError):
            self.module.runtime_preflight(512)
        before = {
            "nvcc": "12.0",
            "cuda_link": {"exists": False},
            "host_tensorrt_python_available": False,
            "selected_environment": {},
            "running_containers": [{"name": "nim"}],
        }
        unchanged = self.module.compare_snapshots(before, dict(before))
        self.assertEqual(unchanged["status"], "pass")
        after = dict(before, nvcc="changed", running_containers=[])
        changed = self.module.compare_snapshots(before, after)
        self.assertEqual(changed["status"], "changed")
        self.assertEqual(changed["preexisting_containers_missing"], ["nim"])

    def test_snapshot_comparison_rejects_lost_unreal_and_restarted_container(self):
        stable = {
            "nvcc": "12.0",
            "cuda_link": {"exists": True, "target": "cuda-12.0"},
            "host_tensorrt_python_available": False,
            "selected_environment": {},
            "gpu0": {"index": 0, "name": "RTX", "driver_version": "580", "total_mib": 1},
            "gpu1": {"index": 1, "name": "A4500", "driver_version": "580", "total_mib": 2},
            "unreal_processes": [{"pid": 123, "command": "/opt/UnrealEditor Project.uproject"}],
            "running_containers": [
                {
                    "name": "audio2face-3d-diffusion",
                    "id": "old-id",
                    "image": "nim:v3",
                    "state": "running",
                    "restart_count": 0,
                }
            ],
        }
        after = json.loads(json.dumps(stable))
        after["unreal_processes"] = []
        after["running_containers"][0].update(
            {"id": "new-id", "image": "other:v3", "state": "restarting", "restart_count": 1}
        )
        report = self.module.compare_snapshots(stable, after)
        self.assertEqual(report["status"], "changed")
        self.assertIn("unreal_processes", report["host_state_mismatches"])
        self.assertIn("audio2face-3d-diffusion", report["container_state_mismatches"])

    def test_phase_a_gate_requires_two_roles_shared_lineage_and_real_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            benchmark = root / "benchmark.json"
            benchmark.write_text("{}")
            avatars = {}
            for role, name in (
                ("elderly_asian_male", "Keiji"),
                ("elderly_asian_female", "Sook-ja"),
            ):
                manifest = root / f"{name}-manifest.json"
                avatar = root / f"{name}.mp4"
                triptych = root / f"{name}-triptych.mp4"
                avatar.write_bytes(name.encode())
                triptych.write_bytes((name + "-triptych").encode())
                manifest.write_text(json.dumps({
                    "motion_artifacts": {"lineage": {
                        "curve_source_sha256": "a" * 64,
                        "model_id": "v3.0-diffusion",
                        "nim_model_id": "multi_v3.2",
                    }}
                }))
                avatars[role] = {
                    "name": name,
                    "character_id": role,
                    "manifest": str(manifest),
                    "avatar_mp4": str(avatar),
                    "triptych_mp4": str(triptych),
                }
            payload = {
                "phase": "A",
                "status": "pass",
                "phase_b_allowed": True,
                "shared_curve_sha256": "a" * 64,
                "avatars": avatars,
                "benchmark": {
                    "path": str(benchmark),
                    "sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest(),
                },
            }
            result = self.module.validate_phase_a_result(payload)
            self.assertEqual(result["status"], "pass")
            payload["avatars"]["elderly_asian_female"]["name"] = "Keiji"
            with self.assertRaisesRegex(ValueError, "distinct"):
                self.module.validate_phase_a_result(payload)

    def test_vram_threshold_is_labeled_unverified_minimum_for_attempt(self):
        with mock.patch.object(
            self.module, "gpu_inventory", return_value={"index": 1, "free_mib": 8192}
        ):
            report = self.module.runtime_preflight(minimum_free_mib=4096)
        self.assertEqual(report["minimum_for_attempt_free_mib"], 4096)
        self.assertIsNone(report["verified_safe_free_vram_mib"])

    def test_output_confinement_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with mock.patch.object(self.module, "OUTPUT_ROOT", root):
                output = root / "evidence.json"
                self.module._write(output, {"status": "pass"})
                self.assertEqual(json.loads(output.read_text())["status"], "pass")
                with self.assertRaises(ValueError):
                    self.module._safe_output(root.parent / "escape.json")

    def test_main_preserves_machine_exit_contracts(self):
        with mock.patch.object(
            self.module, "host_snapshot", return_value={"status": "pass"}
        ), mock.patch.object(self.module, "_write") as write:
            code = self.module.main(["snapshot", "--output", "snapshot.json"])
        self.assertEqual(code, 0)
        write.assert_called_once()
        with mock.patch.object(
            self.module,
            "runtime_preflight",
            return_value={"status": "blocked_vram"},
        ), mock.patch.object(self.module, "_write"):
            code = self.module.main(
                ["preflight", "--output", "preflight.json", "--minimum-free-mib", "4096"]
            )
        self.assertEqual(code, 42)
        with tempfile.TemporaryDirectory() as directory:
            before = Path(directory) / "before.json"
            after = Path(directory) / "after.json"
            before.write_text('{"nvcc":"same"}')
            after.write_text('{"nvcc":"same"}')
            with mock.patch.object(
                self.module, "compare_snapshots", return_value={"status": "pass"}
            ), mock.patch.object(self.module, "_write"):
                code = self.module.main(
                    [
                        "compare",
                        "--before",
                        str(before),
                        "--after",
                        str(after),
                        "--output",
                        "compare.json",
                    ]
                )
        self.assertEqual(code, 0)


class GeometrySidecarVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_path_module("a2f_verify_outputs", VERIFY_OUTPUTS)

    def test_time_alignment_reports_window_and_max_delta(self):
        sdk = [0.0, 1.0 / 60.0, 2.0 / 60.0]
        nim = [0.001, 0.0175, 0.034]
        alignment = self.module.align_timecodes(sdk, nim, tolerance_seconds=0.009)
        self.assertEqual(alignment["status"], "within_tolerance")
        self.assertLessEqual(alignment["maximum_abs_delta_seconds"], 0.009)
        self.assertIn("window_start_delta_seconds", alignment)
        self.assertIn("window_end_delta_seconds", alignment)

    def test_time_alignment_rejects_different_windows(self):
        alignment = self.module.align_timecodes(
            [0.0, 1.0 / 60.0], [0.2, 0.216], tolerance_seconds=0.009
        )
        self.assertEqual(alignment["status"], "outside_tolerance")

    def test_request_curve_adjustments_are_applied_by_name_without_reordering(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.yml"
            request.write_text(
                "blendshape_parameters:\n"
                "  enable_clamping_bs_weight: false\n"
                "  multipliers:\n"
                "    JawOpen: 1.5\n"
                "    MouthClose: 0.5\n"
                "  offsets:\n"
                "    JawOpen: 0.1\n"
                "    MouthClose: 0.0\n"
            )
            config = self.module.parse_request_adjustments(request)
            values = self.module.apply_request_adjustments(
                self.module.np.asarray([[0.2, 0.4]], dtype=self.module.np.float32),
                ["jawOpen", "mouthClose"],
                config,
            )
        self.assertTrue(
            self.module.np.allclose(values, [[0.4, 0.2]], rtol=0, atol=1e-7)
        )

    def test_request_curve_clamping_is_explicit(self):
        values = self.module.np.asarray([[0.8, -0.1]], dtype=self.module.np.float32)
        adjusted = self.module.apply_request_adjustments(
            values,
            ["jawOpen", "mouthClose"],
            {"multipliers": {"jawopen": 2.0}, "offsets": {}, "clamp": True},
        )
        self.assertTrue(self.module.np.allclose(adjusted, [[1.0, 0.0]]))


class DirectGeometryVisualizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_path_module("a2f_direct_geometry_viz", DIRECT_VIZ)

    def test_output_frame_time_maps_to_exact_60fps_sdk_source_frame(self):
        timestamps = self.module.np.arange(218, dtype=self.module.np.float64) / 60.0
        self.assertEqual(
            self.module.nearest_source_frame(timestamps, output_frame=83, output_fps=30),
            166,
        )

    def test_geometry_digest_changes_when_vertices_change(self):
        neutral = self.module.np.zeros((4, 3), dtype=self.module.np.float32)
        moved = neutral.copy(); moved[2, 1] = 1.0
        self.assertNotEqual(
            self.module.geometry_digest(neutral), self.module.geometry_digest(moved)
        )


if __name__ == "__main__":
    unittest.main()
