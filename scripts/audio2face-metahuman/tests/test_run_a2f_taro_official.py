import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run-a2f-metahuman.py"
CAPTURE_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".tools/audio2face-metahuman/KairosSample/Content/Python/a2f_metahuman_capture.py"
)
EDITOR_LIBRARY_CPP = (
    Path(__file__).resolve().parents[3]
    / ".tools/audio2face-metahuman/KairosSample/Source/KairosSample/Private/KairosDemoEditorLibrary.cpp"
)


def load_module():
    spec = importlib.util.spec_from_file_location("run_a2f_taro_official", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfficialA2FPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_nvidia_command_calls_the_pinned_official_sample(self):
        command = self.module.build_inference_command(
            python=Path("/sample/.venv/bin/python"),
            client=Path("/sample/a2f_3d.py"),
            audio=Path("/run/input.nim.wav"),
            config=Path("/sample/config/config_claire.yml"),
            url="127.0.0.1:52000",
        )
        self.assertEqual(command[2], "run_inference")
        self.assertEqual(command[-2:], ["-u", "127.0.0.1:52000"])
        self.assertNotIn("--skip-print-to-files", command)

    def test_motion_curve_source_distinguishes_verified_ace_node_overrides(self):
        config = self.module.load_motion_config(
            Path(__file__).resolve().parents[1]
            / "configs/motion-v3-ace-node-quality-v4.json",
            3.63,
            model_id="v3.0-diffusion",
        )
        self.assertEqual(
            self.module.curve_source_identity_for_motion_config(config),
            "ace-node-overrides",
        )
        self.assertTrue(self.module.requires_content_sync(config))

    def test_plain_artifact_only_config_remains_untrusted_reinference(self):
        config = self.module.load_motion_config(
            None, 3.63, model_id="v2.3-regression"
        )
        self.assertEqual(
            self.module.curve_source_identity_for_motion_config(config),
            "raw-ace-reinference",
        )
        self.assertFalse(self.module.requires_content_sync(config))

    def test_capture_must_prove_exact_ace_node_override_configuration(self):
        config = self.module.load_motion_config(
            Path(__file__).resolve().parents[1]
            / "configs/motion-v3-ace-node-quality-v4.json",
            3.63,
            model_id="v3.0-diffusion",
        )
        expected = config["nvidia_runtime_curve_parameters"]
        result = self.module.validate_ace_node_override_capture(
            config,
            {
                "ace_blendshape_override_nodes": 1,
                "ace_runtime_curve_parameters": expected,
            },
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["configured_node_count"], 1)
        for bad_status in (
            {
                "ace_blendshape_override_nodes": 0,
                "ace_runtime_curve_parameters": expected,
            },
            {
                "ace_blendshape_override_nodes": 1,
                "ace_runtime_curve_parameters": {
                    **expected,
                    "multipliers": {"EyeBlinkLeft": 2.0},
                },
            },
        ):
            with self.subTest(status=bad_status), self.assertRaises(
                self.module.PipelineError
            ):
                self.module.validate_ace_node_override_capture(config, bad_status)

    def test_mrq_command_uses_epic_documented_arguments_only(self):
        command = self.module.build_mrq_command(
            editor_cmd=Path("/ue/UnrealEditor-Cmd"),
            project=Path("/work/KairosSample.uproject"),
            map_path="/Game/Maps/TaroA2F/TaroFaceBodyDemo",
            sequence="/Game/Cinematics/A2FCLI/Take.Take",
            log=Path("/run/mrq.log"),
            graphics_adapter=0,
        )
        joined = " ".join(map(str, command))
        self.assertIn("-game", command)
        self.assertIn("-LevelSequence=/Game/Cinematics/A2FCLI/Take.Take", command)
        self.assertIn(
            "-MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelinePythonHostExecutor",
            command,
        )
        self.assertIn(
            "-ExecutorPythonClass=/Engine/PythonTypes.A2FMetaHumanMoviePipelineExecutor",
            command,
        )
        self.assertNotIn("ExecutePythonScript", joined)
        self.assertNotIn("ExecCmds=py", joined)

    def test_capture_command_uses_init_hook_not_python_command_injection(self):
        command = self.module.build_capture_command(
            editor=Path("/ue/UnrealEditor"),
            project=Path("/work/KairosSample.uproject"),
            map_path="/Game/Maps/TaroA2F/TaroFaceBodyDemo",
            log=Path("/run/capture.log"),
            graphics_adapter=0,
        )
        joined = " ".join(map(str, command))
        self.assertIn("-Multiprocess", command)
        self.assertIn("-RenderOffscreen", command)
        self.assertIn("-TAKERECORDERISHEADLESS", command)
        self.assertNotIn("ExecutePythonScript", joined)
        self.assertNotIn("ExecCmds=py", joined)

    def test_animation_csv_validation_requires_motion_and_monotonic_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "animation_frames.csv"
            csv_path.write_text(
                "timeCode,blendShapes.JawOpen,blendShapes.MouthSmileLeft\n"
                "0.0,0.0,0.0\n"
                "0.033333,0.4,0.1\n"
                "0.066667,0.2,0.0\n",
                encoding="utf-8",
            )
            result = self.module.validate_animation_csv(csv_path)
            self.assertEqual(result["frames"], 3)
            self.assertEqual(result["blendshape_columns"], 2)
            self.assertGreater(result["max_weight_delta"], 0.3)

    def test_manual_boundary_has_stable_nonzero_exit_code(self):
        self.assertEqual(
            int(self.module.ExitCode.MANUAL_EDITOR_CAPTURE_REQUIRED), 42
        )

    def test_volume_parser_rejects_silence_and_accepts_real_audio(self):
        result = self.module.parse_volume_output(
            "mean_volume: -32.2 dB\nmax_volume: -9.4 dB\n"
        )
        self.assertEqual(result, {"mean_dbfs": -32.2, "max_dbfs": -9.4})
        with self.assertRaises(self.module.PipelineError):
            self.module.parse_volume_output(
                "mean_volume: -inf dB\nmax_volume: -inf dB\n"
            )

    def test_manifest_primary_sources_are_only_nvidia_epic(self):
        for url in self.module.PRIMARY_SOURCE_URLS.values():
            self.assertTrue(
                url.startswith("https://docs.nvidia.com/")
                or url.startswith("https://github.com/NVIDIA/")
                or url.startswith("https://huggingface.co/nvidia/")
                or url.startswith("https://dev.epicgames.com/")
            )

    def test_parser_defaults_to_v3_and_keeps_taro_single_shot_defaults(self):
        defaults = self.module.parse_args(["input.wav"])
        self.assertEqual(defaults.avatar, "Taro")
        self.assertEqual(defaults.map, self.module.DEFAULT_MAP)
        self.assertEqual(defaults.a2f_model, "v3.0-diffusion")
        self.assertFalse(defaults.a2f_model_explicit)
        self.assertIsNone(defaults.motion_config)
        self.assertEqual(defaults.avatar_visual_profile, "source")
        self.assertEqual(defaults.progress, "auto")
        self.assertEqual(defaults.shot, [])
        self.assertIsNone(defaults.shot_config)
        extended = self.module.parse_args(
            [
                "input.wav",
                "--avatar",
                "/Game/MetaHumans/Jesse/BP_Jesse.BP_Jesse",
                "--shot",
                "close-up-front",
                "--shot",
                "profile-left",
            ]
        )
        self.assertEqual(extended.avatar, "/Game/MetaHumans/Jesse/BP_Jesse.BP_Jesse")
        self.assertEqual(extended.shot, ["close-up-front", "profile-left"])
        safe_avatar = self.module.parse_args(
            [
                "input.wav",
                "--avatar",
                "Sook-ja",
                "--avatar-visual-profile",
                "face-focused-vulkan-safe",
            ]
        )
        self.assertEqual(
            safe_avatar.avatar_visual_profile, "face-focused-vulkan-safe"
        )
        legacy = self.module.parse_args(
            ["input.wav", "--a2f-model", "v2.3-regression"]
        )
        self.assertEqual(legacy.a2f_model, "v2.3-regression")
        self.assertTrue(legacy.a2f_model_explicit)

    def test_model_selection_preserves_legacy_endpoint_and_routes_v3_side_by_side(self):
        self.assertEqual(
            self.module.resolve_nim_endpoint("v2.3-regression", None),
            "127.0.0.1:52000",
        )
        self.assertEqual(
            self.module.resolve_nim_endpoint("v3.0-diffusion", None),
            "127.0.0.1:52100",
        )
        self.assertEqual(
            self.module.resolve_nim_endpoint("v3.0-diffusion", "127.0.0.1:52999"),
            "127.0.0.1:52999",
        )

    def test_resume_inherits_source_model_only_when_model_was_omitted(self):
        v2 = {
            "a2f_model": {"id": "v2.3-regression"},
            "nim_endpoint": {"url": "127.0.0.1:52000"},
        }
        v3 = {
            "a2f_model": {"id": "v3.0-diffusion"},
            "nim_endpoint": {"url": "127.0.0.1:52100"},
        }
        self.assertEqual(
            self.module.resolve_resume_model_selection(
                v2,
                requested_model="v3.0-diffusion",
                requested_endpoint=None,
                model_was_explicit=False,
            ),
            {
                "model_id": "v2.3-regression",
                "endpoint": "127.0.0.1:52000",
                "selection_source": "resume-manifest",
            },
        )
        self.assertEqual(
            self.module.resolve_resume_model_selection(
                v3,
                requested_model="v3.0-diffusion",
                requested_endpoint=None,
                model_was_explicit=False,
            )["endpoint"],
            "127.0.0.1:52100",
        )
        with self.assertRaises(self.module.ResumeError):
            self.module.resolve_resume_model_selection(
                v2,
                requested_model="v3.0-diffusion",
                requested_endpoint=None,
                model_was_explicit=True,
            )

    def test_v3_failure_hint_never_offers_v2_fallback(self):
        hint = self.module.model_service_failure_hint("v3.0-diffusion")
        self.assertIn("start-a2f-v3-diffusion.sh", hint)
        self.assertIn("no automatic v2 fallback", hint.casefold())
        self.assertNotIn("--a2f-model v2.3-regression", hint)

    def test_native_v3_default_uses_identity_final_bake_but_v2_keeps_artifact_only(self):
        v3 = self.module.load_motion_config(
            None, audio_duration=3.6, model_id="v3.0-diffusion"
        )
        v2 = self.module.load_motion_config(
            None, audio_duration=3.6, model_id="v2.3-regression"
        )
        self.assertEqual(v3["mode"], "baseline")
        self.assertEqual(v3["curve_application"], "final_render")
        self.assertEqual(v3["artifact_postprocess"]["global_intensity"], 1.0)
        self.assertEqual(v2["mode"], "baseline")
        self.assertEqual(v2["curve_application"], "artifact_only")

    def test_known_loopback_model_endpoint_crosswire_is_rejected(self):
        with self.assertRaises(ValueError):
            self.module.validate_model_endpoint_binding(
                "v3.0-diffusion", "127.0.0.1:52000"
            )
        with self.assertRaises(ValueError):
            self.module.validate_model_endpoint_binding(
                "v2.3-regression", "localhost:52100"
            )

    def test_runtime_attestation_distinguishes_bound_and_custom_endpoints(self):
        bound = self.module.classify_endpoint_attestation(
            "v3.0-diffusion", "127.0.0.1:52100"
        )
        custom = self.module.classify_endpoint_attestation(
            "v3.0-diffusion", "127.0.0.1:52999"
        )
        remote = self.module.classify_endpoint_attestation(
            "v3.0-diffusion", "nim.example.com:52100"
        )
        self.assertEqual(bound["status"], "bound-local-runtime")
        self.assertEqual(bound["container"], "audio2face-3d-diffusion")
        self.assertEqual(custom["status"], "unattested-custom-endpoint")
        self.assertIsNone(custom["container"])
        self.assertEqual(remote["status"], "unattested-remote-endpoint")
        self.assertIsNone(remote["container"])

    def test_capture_receives_model_endpoint_and_validated_motion_parameters(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("set_a2x_connection_info", source)
        self.assertIn('self.config["nim_endpoint"]', source)
        self.assertIn("create_audio2_face_parameters", source)
        self.assertIn('self.config.get("ace_runtime_parameters"', source)

    def test_capture_configures_official_apply_ace_node_maps_on_run_instance(self):
        capture_source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        editor_source = EDITOR_LIBRARY_CPP.read_text(encoding="utf-8")
        self.assertIn("configure_ace_blendshape_overrides", capture_source)
        self.assertIn("ace_blendshape_override_nodes", capture_source)
        self.assertIn("FAnimNode_ApplyACEAnimation", editor_source)
        self.assertIn("Node->BlendshapeMultipliers = Multipliers", editor_source)
        self.assertIn("Node->BlendshapeOffsets = Offsets", editor_source)

    def test_final_render_duplicates_and_bakes_run_owned_animation(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('curve_application != "final_render"', source)
        self.assertIn("EditorAssetLibrary.duplicate_asset", source)
        self.assertIn("apply_float_curves_bulk", source)
        self.assertIn("pre_transform_face_animation", source)
        self.assertIn("post_transform_curve_motion", source)
        editor_source = EDITOR_LIBRARY_CPP.read_text(encoding="utf-8")
        self.assertIn("IAnimationDataController::FScopedBracket", editor_source)
        self.assertIn("Controller.SetCurveKeys", editor_source)

    def test_non_default_avatar_saves_then_loads_run_owned_world(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('self.phase = "prepare_avatar_world"', source)
        save_call = "EditorLoadingAndSavingUtils.save_map(world, run_map)"
        load_call = "self.level_editor.load_level(run_map)"
        self.assertIn(save_call, source)
        self.assertIn(load_call, source)
        self.assertLess(source.index(save_call), source.index(load_call))
        self.assertNotIn("EditorAssetLibrary.duplicate_asset(source_map, run_map)", source)

    def test_explicit_avatar_path_uses_exact_asset_registry_lookup(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("registry.get_asset_by_object_path(canonical)", source)

    def test_final_sequence_build_claims_phase_before_slate_can_reenter(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        phase = 'self.phase = "build_final_sequence"'
        build = "self.create_final_sequence()"
        wait_branch = source.index('self.phase == "wait_pie_end"')
        self.assertLess(source.index(phase, wait_branch), source.index(build, wait_branch))

    def test_custom_camera_rotator_names_pitch_yaw_and_roll(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("pitch=rotation_values[0]", source)
        self.assertIn("yaw=rotation_values[1]", source)
        self.assertIn("roll=rotation_values[2]", source)

    def test_ace_instance_setup_checks_face_anim_skeleton_compatibility(self):
        source = EDITOR_LIBRARY_CPP.read_text(encoding="utf-8")
        self.assertIn("IAnimClassInterface::GetFromClass", source)
        self.assertIn("IsCompatibleForEditor(TargetSkeleton)", source)

    def test_unreal_environment_does_not_forward_secret_variables(self):
        with mock.patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "HF_TOKEN": "must-not-leak",
                "NGC_API_KEY": "must-not-leak",
                "SSH_AUTH_SOCK": "/tmp/agent.sock",
                "DISPLAY": ":9",
            },
            clear=True,
        ), mock.patch.object(
            self.module.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=1, stdout=""),
        ):
            environment = self.module.vnc_session_environment()
        self.assertEqual(environment["PATH"], "/usr/bin")
        self.assertEqual(environment["DISPLAY"], ":9")
        self.assertNotIn("HF_TOKEN", environment)
        self.assertNotIn("NGC_API_KEY", environment)
        self.assertNotIn("SSH_AUTH_SOCK", environment)

    def test_render_limits_reject_pathological_values(self):
        valid = self.module.parse_args(["input.wav"])
        self.module.validate_cli_limits(valid)
        for argv in (
            ["input.wav", "--fps", "0"],
            ["input.wav", "--width", "1000000"],
            ["input.wav", "--capture-timeout", "-1"],
            ["input.wav", "--expected-frames", "1000000000"],
        ):
            with self.assertRaises(ValueError):
                self.module.validate_cli_limits(self.module.parse_args(argv))

    def test_remote_nim_requires_explicit_opt_in(self):
        self.assertTrue(self.module.is_loopback_nim_endpoint("127.0.0.1:52000"))
        self.assertTrue(self.module.is_loopback_nim_endpoint("localhost:52000"))
        self.assertFalse(self.module.is_loopback_nim_endpoint("nim.example.com:52000"))

    def test_mrq_output_directory_must_be_empty_and_not_a_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            empty = root / "empty"
            empty.mkdir()
            self.module.validate_mrq_output_directory(empty)
            nonempty = root / "nonempty"
            nonempty.mkdir()
            (nonempty / "existing.png").write_bytes(b"x")
            with self.assertRaises(ValueError):
                self.module.validate_mrq_output_directory(nonempty)
            linked = root / "linked"
            linked.symlink_to(empty, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.module.validate_mrq_output_directory(linked)

    def test_resume_command_preserves_avatar_and_shot_request(self):
        command = self.module.build_resume_command(
            script=Path("/repo/run.py"),
            input_path=Path("/input/speech file.wav"),
            avatar="Ada",
            resume=Path("/runs/missing"),
            config=Path("/config/claire.yml"),
            map_path="/Game/Maps/Demo",
            shots=["close-up-front", "profile-left"],
            shot_config=None,
        )
        self.assertIn("'/input/speech file.wav'", command)
        self.assertIn("--avatar Ada", command)
        self.assertIn("--shot close-up-front", command)
        self.assertIn("--shot profile-left", command)
        self.assertIn("--resume /runs/missing", command)

    def test_resume_command_preserves_custom_shot_file(self):
        command = self.module.build_resume_command(
            script=Path("/repo/run.py"),
            input_path=Path("/input/a.wav"),
            avatar="Ada",
            resume=Path("/runs/missing"),
            config=Path("/config/claire.yml"),
            map_path="/Game/Maps/Demo",
            shots=[],
            shot_config=Path("/shots/custom.json"),
        )
        self.assertIn("--shot-config /shots/custom.json", command)

    def test_resume_command_preserves_model_endpoint_and_motion_config(self):
        command = self.module.build_resume_command(
            script=Path("/repo/run.py"),
            input_path=Path("/input/a.wav"),
            avatar="Taro",
            resume=Path("/runs/missing"),
            config=Path("/config/claire.yml"),
            map_path="/Game/Maps/Demo",
            shots=["close-up-front"],
            shot_config=None,
            a2f_model="v3.0-diffusion",
            nim_url="127.0.0.1:52100",
            motion_config=Path("/configs/expressive.json"),
        )
        self.assertIn("--a2f-model v3.0-diffusion", command)
        self.assertIn("--nim-url 127.0.0.1:52100", command)
        self.assertIn("--motion-config /configs/expressive.json", command)

    def test_resumed_inference_rechecks_files_and_hashes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            names = [
                "animation_frames.csv",
                "a2f_3d_input_emotions.csv",
                "a2f_3d_smoothed_emotion_output.csv",
                "out.wav",
            ]
            files = {}
            for name in names:
                path = output / name
                path.write_bytes(("content-" + name).encode())
                files[name] = {
                    "sha256": self.module.sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            inference = {"output_dir": str(output), "files": files}
            verified = self.module.verify_resumed_inference(inference)
            self.assertEqual(verified["output_dir"], str(output))
            (output / "out.wav").write_bytes(b"tampered")
            with self.assertRaises(self.module.ResumeError):
                self.module.verify_resumed_inference(inference)

    def test_process_group_stop_escalates_after_grace_timeout(self):
        class FakeProcess:
            pid = 1234
            returncode = None

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                if self.returncode is None:
                    if timeout is not None:
                        raise self_module.subprocess.TimeoutExpired("ue", timeout)
                    self.returncode = -9
                return self.returncode

        self_module = self.module
        process = FakeProcess()
        with mock.patch.object(
            self.module, "process_group_exists", return_value=True
        ), mock.patch.object(self.module.os, "killpg") as killpg:
            self.module.stop_process_group(process, grace_seconds=0.01)
        self.assertEqual(
            [call.args[1] for call in killpg.call_args_list],
            [self.module.signal.SIGTERM, self.module.signal.SIGKILL],
        )

    def test_process_group_stop_cleans_child_after_leader_exits(self):
        leader = self.module.subprocess.Popen(
            [
                self.module.sys.executable,
                "-c",
                "import subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                "print(child.pid,flush=True)",
            ],
            stdout=self.module.subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            self.assertTrue(leader.stdout.readline().strip())
            leader.wait(timeout=5)
            self.assertTrue(self.module.process_group_exists(leader.pid))
            self.module.stop_process_group(leader, grace_seconds=1.0)
            self.assertFalse(self.module.process_group_exists(leader.pid))
        finally:
            if self.module.process_group_exists(leader.pid):
                self.module.os.killpg(leader.pid, self.module.signal.SIGKILL)
            if leader.stdout is not None:
                leader.stdout.close()


if __name__ == "__main__":
    unittest.main()
