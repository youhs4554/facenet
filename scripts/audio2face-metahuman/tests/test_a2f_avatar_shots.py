import importlib.util
import math
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "a2f_avatar_shots.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_avatar_shots", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AvatarResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.catalog = [
            {
                "asset_name": "BP_Taro",
                "object_path": "/Game/MetaHumans/Taro/BP_Taro.BP_Taro",
                "generated_class_path": "/Game/MetaHumans/Taro/BP_Taro.BP_Taro_C",
                "metahuman_version": "4.1.2",
            },
            {
                "asset_name": "BP_Jesse",
                "object_path": "/Game/MetaHumans/Jesse/BP_Jesse.BP_Jesse",
                "generated_class_path": "/Game/MetaHumans/Jesse/BP_Jesse.BP_Jesse_C",
                "metahuman_version": "4.1.2",
            },
            {
                "asset_name": "BP_Sook-ja",
                "object_path": "/Game/MetaHumans/Sook-ja/BP_Sook-ja.BP_Sook-ja",
                "generated_class_path": (
                    "/Game/MetaHumans/Sook-ja/BP_Sook-ja.BP_Sook-ja_C"
                ),
                "metahuman_version": "4.0.0",
            },
        ]

    def test_name_and_path_forms_resolve_to_same_taro_blueprint(self):
        expected = "/Game/MetaHumans/Taro/BP_Taro.BP_Taro"
        for selector in (
            "Taro",
            "BP_Taro",
            "/Game/MetaHumans/Taro/BP_Taro",
            expected,
        ):
            resolved = self.module.resolve_avatar(selector, self.catalog)
            self.assertEqual(resolved["object_path"], expected)

    def test_explicit_asset_path_is_canonicalized_and_restricted_to_game(self):
        self.assertEqual(
            self.module.canonicalize_avatar_path(
                "/Game/Characters/Hero/BP_Hero"
            ),
            "/Game/Characters/Hero/BP_Hero.BP_Hero",
        )
        for invalid in ("/tmp/BP_Hero", "../BP_Hero", "/Engine/BP_Hero"):
            with self.assertRaises(self.module.AvatarResolutionError):
                self.module.canonicalize_avatar_path(invalid)

    def test_official_hyphenated_metahuman_name_and_path_are_supported(self):
        expected = "/Game/MetaHumans/Sook-ja/BP_Sook-ja.BP_Sook-ja"
        for selector in (
            "Sook-ja",
            "BP_Sook-ja",
            "/Game/MetaHumans/Sook-ja/BP_Sook-ja",
            expected,
        ):
            with self.subTest(selector=selector):
                resolved = self.module.resolve_avatar(selector, self.catalog)
                self.assertEqual(resolved["object_path"], expected)
        for invalid in (
            "Sook--ja",
            "-Sook-ja",
            "/Game/MetaHumans/Sook--ja/BP_Sook-ja",
            "/Game/MetaHumans/-Sook-ja/BP_Sook-ja",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                self.module.AvatarResolutionError
            ):
                if invalid.startswith("/"):
                    self.module.canonicalize_avatar_path(invalid)
                else:
                    self.module.resolve_avatar(invalid, self.catalog)

    def test_unreal_asset_reference_rejects_option_injection(self):
        valid = [
            "/Game/Maps/Demo",
            "/Game/Cinematics/Run/Sequence.Sequence",
        ]
        for value in valid:
            self.assertEqual(self.module.validate_unreal_asset_reference(value), value)
        for value in (
            "-ExecCmds=quit",
            "/Engine/Maps/Entry",
            "/Game/Maps/Demo.Other",
            "/Game/Maps/../Secret",
            "/Game/Maps/Demo -ExecCmds=quit",
        ):
            with self.assertRaises(self.module.AvatarResolutionError):
                self.module.validate_unreal_asset_reference(value)

    def test_missing_and_ambiguous_avatar_are_never_guessed(self):
        with self.assertRaises(self.module.AvatarImportRequired):
            self.module.resolve_avatar("Ada", self.catalog)
        ambiguous = self.catalog + [
            {
                "asset_name": "BP_Taro",
                "object_path": "/Game/Other/Taro/BP_Taro.BP_Taro",
                "generated_class_path": "/Game/Other/Taro/BP_Taro.BP_Taro_C",
                "metahuman_version": "4.1.2",
            }
        ]
        with self.assertRaises(self.module.AvatarResolutionError) as caught:
            self.module.resolve_avatar("Taro", ambiguous)
        self.assertEqual(len(caught.exception.candidates), 2)


class ShotConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_default_and_profile_alias_preserve_named_catalog(self):
        default = self.module.resolve_named_shots([])
        self.assertEqual([shot["id"] for shot in default], ["close-up-front"])
        profile = self.module.resolve_named_shots(["profile"])
        self.assertEqual(profile[0]["preset"], "profile-left")

    def test_all_required_named_shots_have_distinct_camera_orbits(self):
        names = [
            "close-up-front",
            "medium-three-quarter-left",
            "medium-three-quarter-right",
            "profile-left",
        ]
        shots = self.module.resolve_named_shots(names)
        signatures = {
            (
                shot["camera"]["distance_cm"],
                shot["camera"]["azimuth_deg"],
                shot["camera"]["focal_length_mm"],
            )
            for shot in shots
        }
        self.assertEqual(len(signatures), 4)

    def test_strict_custom_shot_document_accepts_preset_and_camera(self):
        document = {
            "schema_version": 1,
            "shots": [
                {"id": "front", "preset": "close-up-front"},
                {
                    "id": "hero",
                    "camera": {
                        "coordinate_space": "avatar_head",
                        "location_cm": [115.0, -70.0, 8.0],
                        "rotation_deg": [0.0, 145.0, 0.0],
                        "focal_length_mm": 50.0,
                        "aperture": 8.0,
                        "focus_distance_cm": 135.0,
                    },
                },
            ],
        }
        shots = self.module.validate_shot_document(document)
        self.assertEqual([shot["id"] for shot in shots], ["front", "hero"])

    def test_checked_in_custom_shot_fixture_is_valid(self):
        import json

        document = json.loads(
            (FIXTURES / "shots-preset-and-custom.json").read_text(encoding="utf-8")
        )
        shots = self.module.validate_shot_document(document)
        self.assertEqual(
            [shot["id"] for shot in shots],
            ["custom-front-50mm", "preset-profile"],
        )
        self.assertEqual(shots[0]["camera"]["mode"], "transform")

    def test_strict_custom_shot_document_rejects_unsafe_shapes(self):
        invalid_documents = [
            {"schema_version": 1, "unknown": True, "shots": []},
            {
                "schema_version": 1,
                "shots": [
                    {"id": "same", "preset": "close-up-front"},
                    {"id": "same", "preset": "profile-left"},
                ],
            },
            {
                "schema_version": 1,
                "shots": [
                    {
                        "id": "both",
                        "preset": "close-up-front",
                        "camera": {},
                    }
                ],
            },
            {
                "schema_version": 1,
                "shots": [
                    {"id": "bad-preset-type", "preset": []},
                ],
            },
            {
                "schema_version": 1,
                "shots": [
                    {
                        "id": "bad-space-type",
                        "camera": {
                            "coordinate_space": [],
                            "location_cm": [0.0, 0.0, 0.0],
                            "rotation_deg": [0.0, 0.0, 0.0],
                            "focal_length_mm": 50.0,
                            "aperture": 8.0,
                            "focus_distance_cm": 100.0,
                        },
                    }
                ],
            },
            {
                "schema_version": 1,
                "shots": [
                    {
                        "id": "nan",
                        "camera": {
                            "coordinate_space": "world",
                            "location_cm": [math.nan, 0.0, 0.0],
                            "rotation_deg": [0.0, 0.0, 0.0],
                            "focal_length_mm": 50.0,
                            "aperture": 8.0,
                            "focus_distance_cm": 100.0,
                        },
                    }
                ],
            },
        ]
        for document in invalid_documents:
            with self.assertRaises(self.module.ShotConfigError):
                self.module.validate_shot_document(document)


class ResumeAndManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_resume_requires_matching_input_and_config_hashes(self):
        manifest = {
            "status": "success",
            "exit_code": 0,
            "input_sha256": "input-hash",
            "versions": {"official_claire_config_sha256": "config-hash"},
            "official_nvidia_inference": {"output_dir": "/run/output_000001"},
        }
        reused = self.module.validate_resume(
            manifest, input_sha256="input-hash", config_sha256="config-hash"
        )
        self.assertEqual(reused["output_dir"], "/run/output_000001")
        with self.assertRaises(self.module.ResumeError):
            self.module.validate_resume(
                manifest, input_sha256="different", config_sha256="config-hash"
            )
        failed = dict(manifest, status="failure", exit_code=42)
        with self.assertRaises(self.module.ResumeError):
            self.module.validate_resume(
                failed, input_sha256="input-hash", config_sha256="config-hash"
            )
        manual = dict(manifest, status="manual_action_required", exit_code=45)
        reused = self.module.validate_resume(
            manual, input_sha256="input-hash", config_sha256="config-hash"
        )
        self.assertEqual(reused["output_dir"], "/run/output_000001")

    def test_manifest_v2_keeps_legacy_single_shot_fields(self):
        verification = {"final_mp4": "/run/final.mp4", "video_frames": 120}
        manifest = self.module.apply_manifest_v2(
            {"schema_version": 1},
            avatar={"canonical_asset_path": "/Game/MetaHumans/Taro/BP_Taro.BP_Taro"},
            shots=[{"id": "close-up-front", "verification": verification}],
        )
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["verification"], verification)
        self.assertEqual(manifest["final_mp4"], "/run/final.mp4")


if __name__ == "__main__":
    unittest.main()
