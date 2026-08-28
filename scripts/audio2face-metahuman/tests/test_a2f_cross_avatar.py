import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "a2f_cross_avatar.py"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_cross_avatar", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FabCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def candidate(self, **overrides):
        value = {
            "listing_id": "3693be83-9054-4fd3-9b2e-0b6d5b45fe22",
            "listing_url": (
                "https://www.fab.com/listings/"
                "3693be83-9054-4fd3-9b2e-0b6d5b45fe22"
            ),
            "title": "Seo - Editable MetaHuman Character",
            "publisher": "Groomchenko",
            "price": "Free",
            "tags": ["Asian", "MetaHuman", "Editable"],
            "formats": ["MetaHuman"],
            "license": "Standard",
            "no_ai": True,
            "intended_use": "runtime_animation",
        }
        value.update(overrides)
        return value

    def test_free_fab_metahuman_with_explicit_asian_metadata_is_accepted(self):
        candidate = self.module.validate_fab_candidate(self.candidate())
        self.assertEqual(candidate["listing_id"], self.candidate()["listing_id"])
        self.assertEqual(candidate["price"], "Free")
        self.assertEqual(
            candidate["required_tags"], ["Asian", "Editable", "MetaHuman"]
        )
        self.assertEqual(candidate["intended_use"], "runtime_animation")
        self.assertFalse(candidate["epic_authored"])

    def test_paid_missing_metadata_or_training_use_is_rejected(self):
        invalid = [
            self.candidate(price="$4.99"),
            self.candidate(tags=["MetaHuman", "Editable"]),
            self.candidate(formats=["FBX"]),
            self.candidate(license="CC-BY"),
            self.candidate(intended_use="model_training"),
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(
                self.module.FabCandidateError
            ):
                self.module.validate_fab_candidate(candidate)

    def test_manual_boundary_never_allows_phase_b(self):
        boundary = self.module.manual_action_boundary(
            stage="login",
            reason="Epic login requires user interaction",
            evidence="DISPLAY=:1 Window > Fab",
        )
        self.assertEqual(boundary["status"], "manual_action_required")
        self.assertFalse(boundary["phase_b_allowed"])
        self.assertNotIn("credentials", boundary)
        self.assertNotIn("token", boundary)


class CrossAvatarLineageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def lineage(self, **overrides):
        value = {
            "source_run_id": "20260827-165227-v30-dynamic-final-r3",
            "input_sha256": "a" * 64,
            "authoritative_audio_sha256": "b" * 64,
            "model_id": "v3.0-diffusion",
            "architecture": "transformer-diffusion",
            "nim_model_id": "multi_v3.2",
            "nim_endpoint": "127.0.0.1:52100",
            "curve_source_sha256": "c" * 64,
            "curve_source": "effective-final-render",
            "fps": 30,
            "frame_count": 109,
        }
        value.update(overrides)
        return value

    def manifest(self, avatar: str, **lineage_overrides):
        return {
            "status": "success",
            "avatar": {
                "canonical_asset_path": avatar,
                "source_asset_modified": False,
            },
            "compositor_lineage": self.lineage(**lineage_overrides),
        }

    def test_distinct_avatars_with_identical_v3_curve_lineage_pass(self):
        report = self.module.validate_cross_avatar_pair(
            self.manifest("/Game/MetaHumans/Taro/BP_Taro.BP_Taro"),
            self.manifest("/Game/MetaHumans/Seo/BP_Seo.BP_Seo"),
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["shared_curve_sha256"], "c" * 64)
        self.assertEqual(report["changed_dimension"], "avatar_only")

    def test_same_avatar_or_any_lineage_mismatch_is_rejected(self):
        taro = self.manifest("/Game/MetaHumans/Taro/BP_Taro.BP_Taro")
        with self.assertRaises(self.module.CrossAvatarError):
            self.module.validate_cross_avatar_pair(taro, dict(taro))
        for key, value in {
            "input_sha256": "d" * 64,
            "model_id": "v2.3-regression",
            "nim_endpoint": "127.0.0.1:52000",
            "curve_source_sha256": "e" * 64,
            "fps": 60,
        }.items():
            with self.subTest(key=key), self.assertRaises(
                self.module.CrossAvatarError
            ):
                self.module.validate_cross_avatar_pair(
                    taro,
                    self.manifest(
                        "/Game/MetaHumans/Seo/BP_Seo.BP_Seo", **{key: value}
                    ),
                )


class TaroProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_taro_route_is_bridge_preassembled_but_not_policy_reusable(self):
        report = self.module.classify_taro_acquisition_route(
            {
                "catalog_url": (
                    "https://mhc-api.quixel.com/v1/mhc/characters/presets/list"
                ),
                "character_id": "k8bukITg",
                "download_api": (
                    "https://mhc-api.quixel.com/v1/mhc/characters/"
                    "presets/k8bukITg/download"
                ),
                "download_executor": "external_curl",
                "credential_source": "bridge_token_file_contents",
                "bundle_format": "preassembled_ue_zip",
                "export_quality": "Cinematic",
                "export_tool_version": "4.1.2-39981827",
                "import_operation": "unzip_no_overwrite",
                "canonical_asset": "/Game/MetaHumans/Taro/BP_Taro.BP_Taro",
                "editable_mhc_asset_present": False,
                "sample_project_source": False,
            }
        )
        self.assertEqual(report["classification"], "A_bridge_preassembled")
        self.assertFalse(report["official_ui_import"])
        self.assertFalse(report["reusable_under_current_policy"])
        self.assertEqual(
            report["policy_blocker"], "credential_file_contents_were_read"
        )

    def test_public_bridge_catalog_does_not_qualify_demographics_without_fields(self):
        with self.assertRaises(self.module.AvatarMatrixError):
            self.module.qualify_avatar_role(
                "elderly_asian_male",
                {
                    "character_id": "k8ezkISA",
                    "name": "Keiji",
                    "asset_types": ["ue5", "source", "ue5+source"],
                    "mhc_version": "4.0.0",
                },
            )

    def test_taro_route_rejects_nonofficial_or_inconsistent_evidence(self):
        invalid = {
            "catalog_url": "https://example.com/presets/list",
            "character_id": "k8bukITg",
            "download_api": "https://example.com/presets/k8bukITg/download",
            "bundle_format": "mhpkg",
            "import_operation": "bridge_add",
            "editable_mhc_asset_present": True,
            "sample_project_source": True,
        }
        with self.assertRaises(self.module.AvatarMatrixError):
            self.module.classify_taro_acquisition_route(invalid)


class RequiredAvatarMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def candidate(self, role, character_id, gender):
        return {
            "role": role,
            "character_id": character_id,
            "name": f"Candidate-{gender}",
            "source": "official_catalog",
            "source_url": "https://official.example/catalog/item",
            "price": "Free",
            "format": "preassembled_ue_zip",
            "linux_ue56_supported": True,
            "metadata": {
                "ethnicity": "Asian",
                "gender": gender,
                "age": "Elderly",
            },
            "license": "MetaHuman",
        }

    def visual_bridge_candidate(self, role, character_id, name, gender, sha):
        return {
            "role": role,
            "character_id": character_id,
            "name": name,
            "source": "official_bridge_preset_catalog",
            "source_url": (
                "https://mhc-api.quixel.com/v1/mhc/characters/presets/list"
            ),
            "preview_url": (
                "https://quixel-mhc-presets-previews.s3-us-west-2.amazonaws.com/"
                f"{character_id}/previews/{character_id}_720.png"
            ),
            "preview_sha256": sha,
            "price": "Free",
            "format": "preassembled_ue_zip",
            "linux_ue56_supported": True,
            "selection_basis": "user_authorized_visual_assessment",
            "visual_assessment": {
                "user_authorized": True,
                "ethnicity_appearance": "Asian",
                "gender_presentation": gender,
                "age_appearance": "Elderly",
                "limitations_acknowledged": True,
            },
            "license": "Epic Content License Agreement / MetaHuman Addendum",
        }

    def test_both_distinct_slots_with_explicit_metadata_are_required(self):
        result = self.module.validate_required_avatar_matrix(
            [
                self.candidate(
                    "elderly_asian_male", "official-elderly-male", "Male"
                ),
                self.candidate(
                    "elderly_asian_female", "official-elderly-female", "Female"
                ),
            ]
        )
        self.assertEqual(result["status"], "qualified")
        self.assertEqual(
            sorted(result["roles"]),
            ["elderly_asian_female", "elderly_asian_male"],
        )

    def test_user_authorized_visual_bridge_presets_are_qualified_with_disclaimer(self):
        result = self.module.validate_required_avatar_matrix(
            [
                self.visual_bridge_candidate(
                    "elderly_asian_male", "k8ezkISA", "Keiji", "Male", "a" * 64
                ),
                self.visual_bridge_candidate(
                    "elderly_asian_female", "l01pkISw", "Sook-ja", "Female", "b" * 64
                ),
            ]
        )
        self.assertEqual(result["status"], "qualified")
        for candidate in result["roles"].values():
            self.assertEqual(
                candidate["metadata_provenance"],
                "visual_estimate_not_demographic_metadata",
            )
            self.assertTrue(candidate["visual_assessment"]["user_authorized"])
            self.assertIn("not official demographic metadata", candidate["disclaimer"])

    def test_visual_bridge_selection_rejects_missing_authorization_or_provenance(self):
        candidate = self.visual_bridge_candidate(
            "elderly_asian_male", "k8ezkISA", "Keiji", "Male", "a" * 64
        )
        invalid = []
        no_authorization = dict(candidate)
        no_authorization["visual_assessment"] = dict(candidate["visual_assessment"])
        no_authorization["visual_assessment"]["user_authorized"] = False
        invalid.append(no_authorization)
        wrong_catalog = dict(candidate, source_url="https://example.com/presets")
        invalid.append(wrong_catalog)
        bad_hash = dict(candidate, preview_sha256="not-a-sha")
        invalid.append(bad_hash)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(
                self.module.AvatarMatrixError
            ):
                self.module.qualify_avatar_role("elderly_asian_male", value)

    def test_duplicate_avatar_and_missing_demographic_metadata_are_rejected(self):
        male = self.candidate(
            "elderly_asian_male", "same-character", "Male"
        )
        female = self.candidate(
            "elderly_asian_female", "same-character", "Female"
        )
        with self.assertRaises(self.module.AvatarMatrixError):
            self.module.validate_required_avatar_matrix([male, female])
        for missing in ("ethnicity", "gender", "age"):
            invalid = self.candidate(
                "elderly_asian_male", f"missing-{missing}", "Male"
            )
            del invalid["metadata"][missing]
            with self.subTest(missing=missing), self.assertRaises(
                self.module.AvatarMatrixError
            ):
                self.module.qualify_avatar_role(
                    "elderly_asian_male", invalid
                )

    def test_phase_a_is_partial_until_both_e2e_results_pass(self):
        partial = self.module.phase_a_matrix_gate(
            {
                "elderly_asian_male": {
                    "acquired": True,
                    "imported": True,
                    "readiness": True,
                    "same_lineage_e2e": True,
                },
                "elderly_asian_female": {
                    "acquired": True,
                    "imported": True,
                    "readiness": True,
                    "same_lineage_e2e": False,
                },
            }
        )
        self.assertEqual(partial["status"], "partial")
        self.assertFalse(partial["phase_b_allowed"])
        complete = self.module.phase_a_matrix_gate(
            {
                role: {
                    "acquired": True,
                    "imported": True,
                    "readiness": True,
                    "same_lineage_e2e": True,
                }
                for role in (
                    "elderly_asian_male",
                    "elderly_asian_female",
                )
            }
        )
        self.assertEqual(complete["status"], "pass")
        self.assertTrue(complete["phase_b_allowed"])

    def test_matrix_rejects_missing_role_and_wrong_gender(self):
        with self.assertRaises(self.module.AvatarMatrixError):
            self.module.validate_required_avatar_matrix([])
        wrong_gender = self.candidate(
            "elderly_asian_male", "wrong-gender", "Female"
        )
        with self.assertRaises(self.module.AvatarMatrixError):
            self.module.qualify_avatar_role(
                "elderly_asian_male", wrong_gender
            )
        with self.assertRaises(self.module.AvatarMatrixError):
            self.module.phase_a_matrix_gate(
                {"elderly_asian_male": {"acquired": True}}
            )


if __name__ == "__main__":
    unittest.main()
