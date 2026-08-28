import csv
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "a2f_motion.py"
QUALITY_CONFIG = ROOT / "configs/motion-v3-eyes-tongue-safe-final-v2.json"
ACE_SOURCE_QUALITY_CONFIG = ROOT / "configs/motion-v3-ace-source-quality-v3.json"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_motion", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MotionSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def write_animation(self, path, rows=3):
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [""]
                + ["timeCode"]
                + [f"blendShapes.{name}" for name in self.module.BLENDSHAPE_NAMES]
            )
            for frame in range(rows):
                values = [0.0] * len(self.module.BLENDSHAPE_NAMES)
                values[self.module.BLENDSHAPE_NAMES.index("JawOpen")] = frame * 0.2
                values[self.module.BLENDSHAPE_NAMES.index("BrowInnerUp")] = frame * 0.05
                writer.writerow([frame, frame / 30.0] + values)

    def write_emotions(self, path, sparse=False):
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["", "time_code"]
                + [f"emotion_values.{name}" for name in self.module.EMOTION_NAMES]
            )
            rows = 1 if sparse else 3
            for frame in range(rows):
                values = [0.0] * len(self.module.EMOTION_NAMES)
                values[self.module.EMOTION_NAMES.index("joy")] = 0.2 + frame * 0.1
                writer.writerow([frame, frame / 30.0] + values)

    def test_official_csv_normalizes_exact_68_curves_and_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "animation.csv"
            self.write_animation(source)
            series = self.module.parse_animation_csv(source)
        self.assertEqual(series["schema_version"], 1)
        self.assertEqual(series["curve_names"], list(self.module.BLENDSHAPE_NAMES))
        self.assertEqual(len(series["frames"]), 3)
        self.assertEqual(series["frames"][2]["frame_index"], 2)
        self.assertAlmostEqual(series["frames"][2]["time_seconds"], 2 / 30)
        self.assertEqual(len(series["frames"][0]["values"]), 68)

    def test_emotion_csv_normalizes_exact_10_and_preserves_sparse_stream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "emotions.csv"
            self.write_emotions(source, sparse=True)
            series = self.module.parse_emotion_csv(source, source_name="input")
        self.assertEqual(series["emotion_names"], list(self.module.EMOTION_NAMES))
        self.assertEqual(len(series["frames"]), 1)
        self.assertEqual(series["source"], "input")

    def test_smoothed_emotion_sample_timecodes_are_normalized_to_seconds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "emotions.csv"
            self.write_emotions(source, sparse=False)
            rows = list(csv.reader(source.open(encoding="utf-8")))
            rows[1][1], rows[2][1], rows[3][1] = "0", "533", "1066"
            with source.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerows(rows)
            series = self.module.parse_emotion_csv(
                source, source_name="smoothed", timebase_hz=16000.0
            )
        self.assertAlmostEqual(series["frames"][1]["time_seconds"], 533 / 16000)
        self.assertEqual(series["source_timebase_hz"], 16000.0)

    def test_csv_rejects_nonfinite_nonmonotonic_and_wrong_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nonfinite = root / "nonfinite.csv"
            self.write_animation(nonfinite)
            rows = list(csv.reader(nonfinite.open(encoding="utf-8")))
            rows[2][2] = "nan"
            with nonfinite.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerows(rows)
            with self.assertRaises(self.module.MotionDataError):
                self.module.parse_animation_csv(nonfinite)

            nonmonotonic = root / "nonmonotonic.csv"
            self.write_animation(nonmonotonic)
            rows = list(csv.reader(nonmonotonic.open(encoding="utf-8")))
            rows[3][1] = "0.0"
            with nonmonotonic.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerows(rows)
            with self.assertRaises(self.module.MotionDataError):
                self.module.parse_animation_csv(nonmonotonic)

            wrong = root / "wrong.csv"
            wrong.write_text(",timeCode,blendShapes.JawOpen\n0,0,0\n", encoding="utf-8")
            with self.assertRaises(self.module.MotionDataError):
                self.module.parse_animation_csv(wrong)

    def test_irregular_v3_timecodes_resample_impulse_to_exact_audio_frame_30(self):
        series = self.module.synthetic_motion_series(frame_count=5, fps=2.0)
        times = [0.0, 0.47, 1.0, 1.53, 2.0]
        jaw = self.module.BLENDSHAPE_NAMES.index("JawOpen")
        for index, (frame, timestamp) in enumerate(zip(series["frames"], times)):
            frame["frame_index"] = index
            frame["time_seconds"] = timestamp
            frame["values"][jaw] = 1.0 if timestamp == 1.0 else 0.0
        output = self.module.resample_series(series, fps=30.0, frame_count=61)
        self.assertEqual(output["frames"][30]["time_seconds"], 1.0)
        self.assertEqual(output["frames"][30]["values"][jaw], 1.0)
        self.assertEqual(
            output["frames"][30]["source_mapping"],
            {
                "target_time_seconds": 1.0,
                "left_frame_index": 2,
                "right_frame_index": 2,
                "left_time_seconds": 1.0,
                "right_time_seconds": 1.0,
                "interpolation_alpha": 0.0,
            },
        )


class MotionConfigAndEnhancementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_baseline_config_is_identity_and_deterministic(self):
        raw = self.module.synthetic_motion_series(frame_count=4)
        config = self.module.resolve_motion_config()
        enhanced = self.module.apply_motion_enhancement(raw, config)
        self.assertEqual(config["mode"], "baseline")
        self.assertEqual(config["curve_application"], "artifact_only")
        self.assertEqual(raw["frames"], enhanced["frames"])
        self.assertEqual(
            self.module.canonical_json_sha256(enhanced),
            self.module.canonical_json_sha256(
                self.module.apply_motion_enhancement(raw, config)
            ),
        )

    def test_enhancement_applies_global_region_curve_bias_and_clamp(self):
        raw = self.module.synthetic_motion_series(frame_count=3)
        raw["frames"][1]["values"][self.module.BLENDSHAPE_NAMES.index("JawOpen")] = 0.8
        config = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "artifact_only",
                "artifact_postprocess": {
                    "global_intensity": 1.1,
                    "attack": 1.0,
                    "release": 1.0,
                    "region_gains": {"jaw": 1.2},
                    "curve_operations": {
                        "JawOpen": {"gain": 1.5, "bias": 0.1, "clamp": [0.0, 1.0]}
                    },
                },
            },
            audio_duration=1.0,
        )
        enhanced = self.module.apply_motion_enhancement(raw, config)
        jaw = enhanced["frames"][1]["values"][self.module.BLENDSHAPE_NAMES.index("JawOpen")]
        self.assertEqual(jaw, 1.0)
        metrics = self.module.compare_motion_series(raw, enhanced)
        self.assertGreater(metrics["curves"]["JawOpen"]["rmse"], 0.0)
        self.assertGreater(metrics["saturation_fraction"], 0.0)

    def test_attack_release_is_bounded_and_does_not_shift_timestamps(self):
        raw = self.module.synthetic_motion_series(frame_count=5)
        jaw_index = self.module.BLENDSHAPE_NAMES.index("JawOpen")
        for frame, value in enumerate((0.0, 1.0, 1.0, 0.0, 0.0)):
            raw["frames"][frame]["values"][jaw_index] = value
        config = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "artifact_only",
                "artifact_postprocess": {
                    "global_intensity": 1.0,
                    "attack": 0.5,
                    "release": 0.25,
                    "region_gains": {},
                    "curve_operations": {},
                },
            },
            audio_duration=1.0,
        )
        enhanced = self.module.apply_motion_enhancement(raw, config)
        self.assertEqual(
            [frame["time_seconds"] for frame in raw["frames"]],
            [frame["time_seconds"] for frame in enhanced["frames"]],
        )
        values = [frame["values"][jaw_index] for frame in enhanced["frames"]]
        self.assertTrue(all(0.0 <= value <= 1.0 for value in values))
        self.assertLess(values[1], 1.0)
        self.assertGreater(values[3], 0.0)
        self.assertEqual(
            [frame["frame_index"] for frame in raw["frames"]],
            [frame["frame_index"] for frame in enhanced["frames"]],
        )

    def test_strict_config_rejects_unknown_nonfinite_and_invalid_names(self):
        invalid = [
            {"schema_version": 1, "mode": "baseline", "unknown": True},
            {
                "schema_version": 1,
                "mode": "enhanced",
                "emotion": {"constant": {"happy": 0.2}},
            },
            {
                "schema_version": 1,
                "mode": "enhanced",
                "artifact_postprocess": {
                    "global_intensity": math.nan,
                    "attack": 1.0,
                    "release": 1.0,
                    "region_gains": {},
                    "curve_operations": {},
                },
            },
            {
                "schema_version": 1,
                "mode": "enhanced",
                "artifact_postprocess": {
                    "global_intensity": 1.0,
                    "attack": 1.0,
                    "release": 1.0,
                    "region_gains": {},
                    "curve_operations": {"NotACurve": {"gain": 1.0}},
                },
            },
            {
                "schema_version": 1,
                "mode": "enhanced",
                "emotion": {
                    "timecoded": [
                        {"time_seconds": 0.5, "values": {"joy": 0.2}},
                        {"time_seconds": 0.4, "values": {"joy": 0.3}},
                    ]
                },
            },
        ]
        for document in invalid:
            with self.assertRaises(self.module.MotionConfigError):
                self.module.validate_motion_config(document, audio_duration=1.0)

    def test_face_parameter_names_and_ranges_match_installed_ace_25(self):
        expected = {
            "skinStrength", "upperFaceStrength", "lowerFaceStrength",
            "eyelidOpenOffset", "blinkStrength", "lipOpenOffset",
            "upperFaceSmoothing", "lowerFaceSmoothing", "faceMaskLevel",
            "faceMaskSoftness", "tongueStrength", "tongueHeightOffset",
            "tongueDepthOffset", "inputStrength", "blinkOffset",
        }
        self.assertEqual(set(self.module.FACE_PARAMETER_SPECS), expected)
        valid = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "face_parameters": {
                    "inputStrength": 3.0,
                    "lowerFaceSmoothing": 0.1,
                    "lipOpenOffset": -0.2,
                },
            },
            audio_duration=1.0,
        )
        self.assertEqual(valid["face_parameters"]["inputStrength"], 3.0)
        for name, value in (
            ("input_strength", 1.0),
            ("eyelidOffset", 0.0),
            ("lowerFaceStrength", 2.1),
            ("faceMaskSoftness", 0.0),
        ):
            with self.assertRaises(self.module.MotionConfigError):
                self.module.validate_motion_config(
                    {
                        "schema_version": 1,
                        "mode": "enhanced",
                        "face_parameters": {name: value},
                    },
                    audio_duration=1.0,
                )

    def test_non_runtime_controls_require_explicit_application_boundary(self):
        transform = {
            "global_intensity": 1.1,
            "attack": 0.7,
            "release": 0.4,
            "region_gains": {},
            "curve_operations": {},
        }
        with self.assertRaises(self.module.MotionConfigError):
            self.module.validate_motion_config(
                {
                    "schema_version": 1,
                    "mode": "enhanced",
                    "artifact_postprocess": transform,
                },
                audio_duration=1.0,
            )
        artifact = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "artifact_only",
                "artifact_postprocess": transform,
            },
            audio_duration=1.0,
        )
        final = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "final_render",
                "artifact_postprocess": transform,
            },
            audio_duration=1.0,
        )
        self.assertEqual(artifact["curve_application"], "artifact_only")
        self.assertEqual(final["curve_application"], "final_render")

    def test_baseline_mode_rejects_nonidentity_postprocess_instead_of_ignoring_it(self):
        with self.assertRaises(self.module.MotionConfigError):
            self.module.validate_motion_config(
                {
                    "schema_version": 1,
                    "mode": "baseline",
                    "curve_application": "final_render",
                    "artifact_postprocess": {
                        "global_intensity": 2.0,
                        "attack": 1.0,
                        "release": 1.0,
                        "region_gains": {},
                        "curve_operations": {},
                    },
                },
                audio_duration=1.0,
            )

    def test_timecoded_emotion_requires_explicit_artifact_or_final_render(self):
        base = {
            "schema_version": 1,
            "mode": "enhanced",
            "emotion": {
                "timecoded": [
                    {"time_seconds": 0.0, "values": {"joy": 0.2}},
                    {"time_seconds": 0.5, "values": {"joy": 0.8}},
                ]
            },
        }
        with self.assertRaises(self.module.MotionConfigError):
            self.module.validate_motion_config(base, audio_duration=1.0)
        base["curve_application"] = "final_render"
        result = self.module.validate_motion_config(base, audio_duration=1.0)
        self.assertEqual(result["curve_application"], "final_render")

    def test_ace25_source_contract_accepts_tongue_out_but_rejects_extended_tongue(self):
        accepted = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "final_render",
                "artifact_postprocess": {
                    "global_intensity": 1.0, "attack": 1.0, "release": 1.0,
                    "region_gains": {},
                    "curve_operations": {"TongueOut": {"gain": 1.2}},
                },
            },
            audio_duration=1.0,
        )
        self.assertEqual(accepted["final_render_profile"], "ace-source")
        self.assertEqual(len(self.module.ACE25_SOURCE_CURVE_NAMES), 52)
        self.assertEqual(self.module.ACE25_SOURCE_CURVE_NAMES[-1], "TongueOut")
        for post in (
            {
                "global_intensity": 1.0, "attack": 1.0, "release": 1.0,
                "region_gains": {"tongue": 1.2}, "curve_operations": {},
            },
            {
                "global_intensity": 1.0, "attack": 1.0, "release": 1.0,
                "region_gains": {},
                "curve_operations": {"TongueTipUp": {"gain": 1.2}},
            },
        ):
            with self.assertRaises(self.module.MotionConfigError):
                self.module.validate_motion_config(
                    {
                        "schema_version": 1,
                        "mode": "enhanced",
                        "curve_application": "final_render",
                        "artifact_postprocess": post,
                    },
                    audio_duration=1.0,
                )

    def test_pose_asset_extended_profile_opt_in_allows_all_68_curves(self):
        config = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "final_render",
                "final_render_profile": "pose-asset-extended",
                "artifact_postprocess": {
                    "global_intensity": 1.0,
                    "attack": 0.8,
                    "release": 0.6,
                    "region_gains": {"tongue": 1.1},
                    "curve_operations": {
                        "TongueTipUp": {"gain": 1.2, "clamp": [0.0, 0.8]},
                        "EyeBlinkLeft": {"gain": 4.0, "clamp": [0.0, 0.8]},
                    },
                },
            },
            audio_duration=1.0,
        )
        self.assertEqual(config["final_render_profile"], "pose-asset-extended")
        self.assertEqual(
            self.module.final_render_curve_names(config),
            self.module.BLENDSHAPE_NAMES,
        )
        self.assertEqual(len(self.module.A2F_POSE_ASSET_EXTENDED_CURVE_NAMES), 68)

    def test_extended_profile_requires_final_render_boundary(self):
        for curve_application in ("artifact_only", None):
            document = {
                "schema_version": 1,
                "mode": "enhanced",
                "final_render_profile": "pose-asset-extended",
            }
            if curve_application is not None:
                document["curve_application"] = curve_application
            with self.assertRaises(self.module.MotionConfigError):
                self.module.validate_motion_config(document, audio_duration=1.0)

    def test_checked_quality_profile_enhances_a2f_blink_and_tongue_without_clipping(self):
        document = json.loads(QUALITY_CONFIG.read_text())
        config = self.module.validate_motion_config(document, audio_duration=4.0)
        raw = self.module.synthetic_motion_series(frame_count=3)
        blink = self.module.BLENDSHAPE_NAMES.index("EyeBlinkLeft")
        tongue = self.module.BLENDSHAPE_NAMES.index("TongueIn")
        raw["frames"][1]["values"][blink] = 0.1
        raw["frames"][1]["values"][tongue] = 0.4
        enhanced = self.module.apply_motion_enhancement(raw, config)
        values = enhanced["frames"][1]["values"]
        self.assertEqual(config["final_render_profile"], "pose-asset-extended")
        self.assertGreater(values[blink], raw["frames"][1]["values"][blink])
        self.assertGreater(values[tongue], raw["frames"][1]["values"][tongue])
        self.assertGreaterEqual(values[blink], 0.7)
        self.assertLessEqual(values[blink], 0.85)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in values))

    def test_runtime_curve_parameters_apply_before_ace_capture_not_artifact_only(self):
        base = {
            "face_parameters": {},
            "blendshape_parameters": {
                "enable_clamping_bs_weight": False,
                "multipliers": {name: 1.0 for name in self.module.BLENDSHAPE_NAMES},
                "offsets": {name: 0.0 for name in self.module.BLENDSHAPE_NAMES},
            },
            "post_processing_parameters": {},
            "emotion_with_timecode_list": {},
        }
        base["blendshape_parameters"]["multipliers"]["EyeBlinkLeft"] = 2.0
        config = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "artifact_only",
                "nvidia_runtime_curve_parameters": {
                    "enable_clamping": True,
                    "multipliers": {
                        "EyeBlinkLeft": 8.0,
                        "EyeBlinkRight": 8.0,
                    },
                    "offsets": {},
                },
            },
            audio_duration=1.0,
        )
        effective = self.module.build_effective_nim_config(
            base, config, include_artifact_postprocess=False
        )
        self.assertEqual(
            effective["blendshape_parameters"]["multipliers"]["EyeBlinkLeft"],
            8.0,
        )
        self.assertTrue(
            effective["blendshape_parameters"]["enable_clamping_bs_weight"]
        )

    def test_runtime_curve_parameters_reject_extended_tongue_not_consumed_by_ace(self):
        with self.assertRaises(self.module.MotionConfigError):
            self.module.validate_motion_config(
                {
                    "schema_version": 1,
                    "mode": "enhanced",
                    "curve_application": "artifact_only",
                    "nvidia_runtime_curve_parameters": {
                        "enable_clamping": True,
                        "multipliers": {"TongueIn": 2.0},
                        "offsets": {},
                    },
                },
                audio_duration=1.0,
            )

    def test_checked_ace_source_quality_profile_uses_runtime_blink_without_post_bake_claim(self):
        document = json.loads(ACE_SOURCE_QUALITY_CONFIG.read_text())
        config = self.module.validate_motion_config(document, audio_duration=4.0)
        self.assertEqual(config["curve_application"], "artifact_only")
        self.assertEqual(config["final_render_profile"], "ace-source")
        runtime = config["nvidia_runtime_curve_parameters"]
        self.assertEqual(runtime["multipliers"]["EyeBlinkLeft"], 8.0)
        self.assertEqual(runtime["multipliers"]["EyeBlinkRight"], 8.0)

    def test_constant_emotion_becomes_full_clip_preferred_override(self):
        base = {
            "face_parameters": {},
            "blendshape_parameters": {
                "multipliers": {name: 1.0 for name in self.module.BLENDSHAPE_NAMES},
                "offsets": {name: 0.0 for name in self.module.BLENDSHAPE_NAMES},
            },
            "post_processing_parameters": {},
            "emotion_with_timecode_list": {},
        }
        config = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "emotion": {"constant": {"joy": 0.75}},
            },
            audio_duration=1.0,
        )
        effective = self.module.build_effective_nim_config(base, config)
        first = effective["emotion_with_timecode_list"]["emotion_with_timecode1"]
        self.assertEqual(first["time_code"], 0.0)
        self.assertEqual(first["emotions"]["joy"], 0.75)
        self.assertEqual(set(first["emotions"]), set(self.module.EMOTION_NAMES))
        self.assertTrue(
            all(
                value == 0.0
                for name, value in first["emotions"].items()
                if name != "joy"
            )
        )
        self.assertTrue(effective["post_processing_parameters"]["enable_preferred_emotion"])
        self.assertEqual(effective["post_processing_parameters"]["preferred_emotion_strength"], 1.0)

    def test_timecoded_emotion_expands_every_keyframe_to_canonical_ten_columns(self):
        base = {
            "face_parameters": {},
            "blendshape_parameters": {"multipliers": {}, "offsets": {}},
            "post_processing_parameters": {},
            "emotion_with_timecode_list": {},
        }
        config = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "artifact_only",
                "emotion": {
                    "constant": {},
                    "timecoded": [
                        {"time_seconds": 0.0, "values": {"joy": 0.7}},
                        {"time_seconds": 1.0, "values": {"sadness": 0.7}},
                    ],
                },
            },
            audio_duration=2.0,
        )
        effective = self.module.build_effective_nim_config(base, config)
        entries = effective["emotion_with_timecode_list"]
        self.assertEqual(len(entries), 2)
        for entry in entries.values():
            self.assertEqual(set(entry["emotions"]), set(self.module.EMOTION_NAMES))

    def test_effective_nim_config_preserves_base_and_applies_supported_fields(self):
        base = {
            "face_parameters": {"lowerFaceStrength": 1.0},
            "blendshape_parameters": {
                "enable_clamping_bs_weight": False,
                "multipliers": {name: 1.0 for name in self.module.BLENDSHAPE_NAMES},
                "offsets": {name: 0.0 for name in self.module.BLENDSHAPE_NAMES},
            },
            "post_processing_parameters": {"emotion_strength": 0.6},
            "emotion_with_timecode_list": {},
        }
        original = json.loads(json.dumps(base))
        config = self.module.validate_motion_config(
            {
                "schema_version": 1,
                "mode": "enhanced",
                "curve_application": "artifact_only",
                "face_parameters": {"lowerFaceStrength": 1.1},
                "emotion": {
                    "overall_strength": 0.7,
                    "timecoded": [
                        {"time_seconds": 0.25, "values": {"joy": 0.4}}
                    ],
                },
                "artifact_postprocess": {
                    "global_intensity": 1.0,
                    "attack": 1.0,
                    "release": 1.0,
                    "region_gains": {},
                    "curve_operations": {"JawOpen": {"gain": 1.2, "bias": 0.1}},
                },
            },
            audio_duration=1.0,
        )
        effective = self.module.build_effective_nim_config(base, config)
        self.assertEqual(base, original)
        self.assertEqual(effective["face_parameters"]["lowerFaceStrength"], 1.1)
        self.assertEqual(effective["blendshape_parameters"]["multipliers"]["JawOpen"], 1.2)
        self.assertEqual(effective["blendshape_parameters"]["offsets"]["JawOpen"], 0.1)
        self.assertEqual(effective["post_processing_parameters"]["emotion_strength"], 0.7)
        self.assertEqual(len(effective["emotion_with_timecode_list"]), 1)

    def test_canonical_json_and_csv_round_trip(self):
        series = self.module.synthetic_motion_series(frame_count=3)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_path = root / "motion.json"
            csv_path = root / "motion.csv"
            record = self.module.write_motion_series(series, json_path, csv_path)
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            rows = list(csv.reader(csv_path.open(encoding="utf-8")))
            expected_hash = self.module.sha256_file(json_path)
        self.assertEqual(loaded, series)
        self.assertEqual(len(rows[0]), 70)
        self.assertEqual(record["json"]["sha256"], expected_hash)

    def test_timecode_resampling_makes_diffusion_60fps_match_30fps_video(self):
        series = self.module.synthetic_motion_series(frame_count=7, fps=60.0)
        jaw = self.module.BLENDSHAPE_NAMES.index("JawOpen")
        for index, frame in enumerate(series["frames"]):
            frame["values"][jaw] = index / 6.0
        sampled = self.module.resample_series(series, fps=30.0, frame_count=4)
        self.assertEqual(len(sampled["frames"]), 4)
        self.assertEqual(
            [frame["time_seconds"] for frame in sampled["frames"]],
            [0.0, 1 / 30, 2 / 30, 3 / 30],
        )
        self.assertAlmostEqual(sampled["frames"][1]["values"][jaw], 1 / 3)
        self.assertEqual(sampled["resampling"]["method"], "linear-timecode")


if __name__ == "__main__":
    unittest.main()
