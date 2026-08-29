import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "a2f_lineage.py"


def load_module():
    spec = importlib.util.spec_from_file_location("a2f_lineage", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class A2FLineageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def lineage(self, **overrides):
        values = {
            "source_run_id": "20260827-v30-dynamic",
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
        values.update(overrides)
        return self.module.make_lineage(**values)

    def head_motion_lineage(self, **overrides):
        values = {
            "enabled": True,
            "profile": "subtle-conversational",
            "config_sha256": "d" * 64,
            "samples_sha256": "e" * 64,
            "fps": 30,
            "frame_count": 109,
        }
        values.update(overrides)
        return self.module.make_head_motion_lineage(**values)

    def lineage_with_head_motion(self, **overrides):
        expected = self.lineage()
        values = {key: expected[key] for key in self.module.LINEAGE_FIELDS}
        values["head_motion_lineage"] = self.head_motion_lineage(**overrides)
        return self.module.make_lineage(**values)

    def test_head_motion_lineage_is_separate_versioned_record(self):
        expected = self.lineage_with_head_motion()
        head = expected["head_motion_lineage"]
        self.assertEqual(head["schema_version"], 1)
        self.assertTrue(head["enabled"])
        self.assertEqual(head["profile"], "subtle-conversational")
        self.assertEqual(head["config_sha256"], "d" * 64)
        self.assertEqual(head["samples_sha256"], "e" * 64)
        self.assertEqual(head["fps"], 30)
        self.assertEqual(head["frame_count"], 109)
        self.assertEqual(expected["curve_source_sha256"], "c" * 64)

    def test_head_motion_lineage_mismatch_is_rejected_for_every_bound_field(self):
        expected = self.lineage_with_head_motion()
        for key, value in {
            "profile": "other-profile",
            "config_sha256": "f" * 64,
            "samples_sha256": "0" * 64,
            "fps": 60,
            "frame_count": 218,
        }.items():
            with self.subTest(key=key), self.assertRaises(self.module.LineageError):
                candidate = dict(expected)
                candidate["head_motion_lineage"] = dict(
                    expected["head_motion_lineage"], **{key: value}
                )
                self.module.validate_compositor_lineage(
                    expected,
                    {
                        "avatar": candidate,
                        "mannequin": dict(expected),
                        "curve_panel": dict(expected),
                        "audio": dict(expected),
                    },
                )

    def test_matching_avatar_mannequin_panel_and_audio_pass(self):
        expected = self.lineage()
        result = self.module.validate_compositor_lineage(
            expected,
            {
                "avatar": dict(expected),
                "mannequin": dict(expected),
                "curve_panel": dict(expected),
                "audio": dict(expected),
            },
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["component_count"], 4)

    def test_v2_avatar_cannot_be_composed_with_v3_motion(self):
        expected = self.lineage()
        v2_avatar = self.lineage(
            source_run_id="v23-run",
            model_id="v2.3-regression",
            architecture="regression",
            nim_model_id="claire_v2.3.1",
            nim_endpoint="127.0.0.1:52000",
        )
        with self.assertRaises(self.module.LineageError):
            self.module.validate_compositor_lineage(
                expected,
                {
                    "avatar": v2_avatar,
                    "mannequin": dict(expected),
                    "curve_panel": dict(expected),
                    "audio": dict(expected),
                },
            )

    def test_artifact_only_reinference_cannot_claim_exact_curve_lineage(self):
        request_level = self.lineage(curve_source="raw-ace-reinference")
        with self.assertRaises(self.module.LineageError):
            self.module.validate_compositor_lineage(
                request_level,
                {
                    "avatar": dict(request_level),
                    "mannequin": dict(request_level),
                    "curve_panel": dict(request_level),
                    "audio": dict(request_level),
                },
            )

    def test_verified_ace_node_overrides_can_use_strict_compositor_lineage(self):
        node_override = self.lineage(curve_source="ace-node-overrides")
        result = self.module.validate_compositor_lineage(
            node_override,
            {
                "avatar": dict(node_override),
                "mannequin": dict(node_override),
                "curve_panel": dict(node_override),
                "audio": dict(node_override),
            },
        )
        self.assertTrue(result["valid"])

    def test_ace_node_override_showcase_label_is_not_raw_reinference(self):
        identity = self.module.showcase_identity(
            model_id="v3.0-diffusion",
            architecture="transformer-diffusion",
            nim_model_id="multi_v3.2",
            curve_source="ace-node-overrides",
            layout_id="layout-v3",
        )
        self.assertEqual(identity["panel_source"], "ACE NODE OVERRIDES / CAPTURED")

    def test_any_run_input_curve_or_timeline_mismatch_is_rejected(self):
        expected = self.lineage()
        cases = {
            "source_run_id": "another-run",
            "input_sha256": "d" * 64,
            "authoritative_audio_sha256": "e" * 64,
            "curve_source_sha256": "f" * 64,
            "fps": 60,
            "frame_count": 218,
        }
        for key, value in cases.items():
            with self.subTest(key=key), self.assertRaises(
                self.module.LineageError
            ):
                component = dict(expected)
                component[key] = value
                self.module.validate_compositor_lineage(
                    expected,
                    {
                        "avatar": component,
                        "mannequin": dict(expected),
                        "curve_panel": dict(expected),
                        "audio": dict(expected),
                    },
                )

    def test_model_and_layout_tokens_are_unambiguous(self):
        identity = self.module.showcase_identity(
            model_id="v3.0-diffusion",
            architecture="transformer-diffusion",
            nim_model_id="multi_v3.2",
            curve_source="effective-final-render",
            layout_id="layout-v3",
        )
        self.assertEqual(identity["model_token"], "v30-diffusion")
        self.assertEqual(identity["layout_id"], "layout-v3")
        self.assertEqual(identity["panel_title"], "A2F v3.0 DIFFUSION")
        self.assertEqual(identity["panel_model"], "multi_v3.2")
        self.assertEqual(
            identity["panel_source"], "EFFECTIVE / FINAL-RENDER"
        )
        self.assertEqual(
            identity["filename_suffix"], "v30-diffusion-layout-v3"
        )


if __name__ == "__main__":
    unittest.main()
