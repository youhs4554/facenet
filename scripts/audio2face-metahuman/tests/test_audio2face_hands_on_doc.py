import hashlib
import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "scripts/audio2face-metahuman/run-a2f-metahuman.py"
DOC = ROOT / "docs/audio2face-metahuman-cli-hands-on.ko.md"
ASSETS = ROOT / "docs/assets/audio2face-hands-on"
SCREENSHOT_MANIFEST = ASSETS / "screenshots/screenshot-manifest.json"
WRITING_CONTRACT = ASSETS / "hands-on-writing-contract.md"
HANDS_ON_VERIFICATION = ASSETS / "hands-on-verification.json"
SHOT_MODULE = ROOT / "scripts/audio2face-metahuman/a2f_avatar_shots.py"


class Audio2FaceHandsOnDocumentTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(DOC.is_file(), "hands-on document has not been created")
        self.text = DOC.read_text(encoding="utf-8")

    def test_every_canonical_cli_option_is_documented(self):
        completed = subprocess.run(
            [str(CLI), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        options = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", completed.stdout))
        self.assertEqual(len(options), 32)  # 31 user controls plus --help.
        missing = sorted(option for option in options if f"`{option}`" not in self.text)
        self.assertEqual(missing, [], f"undocumented CLI options: {missing}")

    def test_core_control_categories_and_truth_boundaries_exist(self):
        required = (
            "## 1. 결과와 5분 Quick Start",
            "## 2. 용어와 시스템 개요",
            "## 3. 사전 요구사항과 최초 1회 설정",
            "## 4. Stage 1: 입력과 runtime 확인",
            "## 5. Stage 2: baseline 얼굴 애니메이션 만들기",
            "## 6. Stage 3: 자연스러운 머리 움직임 켜기",
            "## 7. Stage 4: MetaHuman과 안전한 visual profile 선택",
            "## 8. Stage 5: named/custom camera 선택",
            "## 9. Stage 6: emotion, 얼굴 parameter와 motion intensity",
            "## 10. Stage 7: UE capture와 MRQ render",
            "## 11. Stage 8: 결과와 codec·동기 검증",
            "## 12. Resume, 복구와 자동화 경계",
            "## 13. Troubleshooting matrix",
            "## 14. CLI 옵션 레퍼런스",
            "## 15. 재현성과 증거 부록",
            "final-render applied",
            "artifact/visualization only",
            "manual_action_required",
            "local-run-owned-baked-body-animsequence",
            "NVIDIA-generated head motion이 아니다",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_system_overview_has_concept_and_architecture_figures(self):
        self.assertRegex(
            self.text,
            r"!\[[^]]*(?:흐름|개념)[^]]*\]\(assets/audio2face-hands-on/figures/concept-overview-general-generated-v3\.png\)",
        )
        self.assertRegex(
            self.text,
            r"!\[[^]]*아키텍처[^]]*\]\(assets/audio2face-hands-on/figures/cli-architecture-novice-generated-v3\.png\)",
        )

    def test_all_linked_hands_on_images_exist(self):
        targets = re.findall(
            r"!\[[^]]*\]\((assets/audio2face-hands-on/[^)]+)\)", self.text
        )
        self.assertGreaterEqual(len(targets), 16)
        missing = [target for target in targets if not (ROOT / "docs" / target).is_file()]
        self.assertEqual(missing, [])
        screenshot_targets = {target for target in targets if "/screenshots/" in target}
        self.assertEqual(len(screenshot_targets), 9)
        self.assertEqual(sum("/vnc/" in target for target in targets), 0)
        self.assertGreaterEqual(
            sum("/results/" in target for target in targets), 6,
            "at least six control/result evidence images are required",
        )

    def test_examples_cover_requested_control_surfaces(self):
        for value in (
            "close-up-front",
            "medium-three-quarter-left",
            "medium-three-quarter-right",
            "profile-left",
            "shot-custom-front.json",
            "Taro",
            "Keiji",
            "Sook-ja",
            "v3.0-diffusion",
            "v2.3-regression",
            "motion-v3-dynamic-safe-final-v1.json",
            "motion-v3-ace-node-quality-v4.json",
            "overall_strength",
            "constant",
            "timecoded",
            "global_intensity",
            "region_gains",
            "curve_operations",
            "focal_length_mm",
            "focus_distance_cm",
            "--head-motion",
            "--head-motion-strength",
            "--head-motion-calibration-manifest",
            "subtle-conversational",
            "09-head-motion-all-avatars.png",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_each_major_stage_has_the_same_reader_contract(self):
        headings = list(
            re.finditer(r"^## (\d+)\. Stage (\d+):.*$", self.text, flags=re.MULTILINE)
        )
        self.assertEqual([int(item.group(2)) for item in headings], list(range(1, 9)))
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else self.text.index("\n## 12.")
            section = self.text[heading.start() : end]
            for required in (
                "### 목적",
                "### 명령",
                "### 예상 상태",
                "### 산출물",
                "### 통과 기준",
                "### 실패와 복구",
                "### 경계",
            ):
                with self.subTest(stage=heading.group(2), required=required):
                    self.assertIn(required, section)

    def test_screenshot_manifest_is_complete_and_data_faithful(self):
        self.assertTrue(SCREENSHOT_MANIFEST.is_file())
        payload = json.loads(SCREENSHOT_MANIFEST.read_text(encoding="utf-8"))
        records = payload["screenshots"]
        self.assertEqual(len(records), 9)
        self.assertIn("no generative", payload["disclosure"].lower())
        self.assertGreaterEqual(sum(item["real_terminal_capture"] for item in records), 6)
        self.assertGreaterEqual(sum(item["real_gui_capture"] for item in records), 1)
        for item in records:
            source = ASSETS / item["source_capture_path"]
            output = ASSETS / item["output_path"]
            with self.subTest(output=item["output_path"]):
                self.assertTrue(source.is_file())
                self.assertTrue(output.is_file())
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), item["source_sha256"])
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), item["output_sha256"])
                self.assertEqual(list(Image.open(source).size), item["source_dimensions"])
                self.assertEqual(list(Image.open(output).size), item["output_dimensions"])
                self.assertEqual(len(item["crop_rectangle_xywh"]), 4)
                self.assertFalse(item["generative_pixels_used"])
                self.assertFalse(item["empirical_avatar_pixels_altered"])

    def test_writing_contract_locks_argument_terms_claims_and_screenshots(self):
        self.assertTrue(WRITING_CONTRACT.is_file())
        contract = WRITING_CONTRACT.read_text(encoding="utf-8")
        for value in (
            "## 한 문장 주장",
            "## 용어 ledger",
            "## Claim–evidence–boundary map",
            "## 스크린샷–stage map",
            "NVIDIA Audio2Face-3D v3.0 diffusion",
            "NIM `multi_v3.2`",
            "NVIDIA ACE 2.5",
            "Movie Render Queue",
            "local-run-owned-baked-body-animsequence",
        ):
            with self.subTest(value=value):
                self.assertIn(value, contract)

    def test_hands_on_verification_matches_current_document_and_images(self):
        self.assertTrue(HANDS_ON_VERIFICATION.is_file())
        payload = json.loads(HANDS_ON_VERIFICATION.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["document_sha256"], hashlib.sha256(DOC.read_bytes()).hexdigest())
        self.assertEqual(payload["line_count"], len(self.text.splitlines()))
        self.assertTrue(payload["all_links_exist"])
        self.assertEqual(payload["screenshot_provenance"]["count"], 9)
        self.assertFalse(payload["screenshot_provenance"]["generative_pixels_used"])
        self.assertEqual(payload["authoritative_head_motion"]["run_id"], "20260829-110741-head-motion-sync-final-r7")
        for item in payload["linked_images"]:
            path = ROOT / "docs" / item["relative_path"]
            with self.subTest(path=item["relative_path"]):
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
                self.assertEqual(list(Image.open(path).size), [item["width"], item["height"]])

    def test_no_model_comparison_or_stale_head_motion_blocker_is_reintroduced(self):
        self.assertNotIn("04-model-v23-v30.png", self.text)
        self.assertNotIn("v2.3 vs v3.0", self.text)
        self.assertNotIn("ON MP4 성공 증거가 아직 없", self.text)
        self.assertIn("ceil(audio_duration × fps)", self.text)
        self.assertIn("worked example", self.text)

    def test_official_product_claims_link_to_primary_vendor_docs(self):
        for value in (
            "https://docs.nvidia.com/ace/audio2face-3d-microservice/",
            "https://docs.nvidia.com/ace/ace-unreal-plugin/",
            "https://dev.epicgames.com/documentation/en-us/unreal-engine/",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_all_copy_paste_bash_blocks_are_syntactically_valid(self):
        blocks = re.findall(r"```bash\n(.*?)\n```", self.text, flags=re.DOTALL)
        self.assertGreaterEqual(len(blocks), 12)
        for index, block in enumerate(blocks):
            completed = subprocess.run(
                ["bash", "-n"],
                input=block,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            with self.subTest(block=index):
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_custom_camera_json_matches_the_strict_source_schema(self):
        blocks = re.findall(r"```json\n(.*?)\n```", self.text, flags=re.DOTALL)
        document = next(json.loads(block) for block in blocks if "custom-front-50mm" in block)
        spec = importlib.util.spec_from_file_location("a2f_avatar_shots_doc", SHOT_MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.validate_shot_document(document)
        self.assertEqual(result[0]["id"], "custom-front-50mm")
        self.assertEqual(result[0]["camera"]["focus_distance_cm"], 120.0)

    def test_terminal_evidence_renderer_never_splits_path_arguments(self):
        renderer = (ASSETS / "render_terminal_evidence.py").read_text(encoding="utf-8")
        self.assertNotIn('configs/ \\\\"', renderer)
        self.assertNotIn('official-cli-runs/ \\\\"', renderer)


if __name__ == "__main__":
    unittest.main()
