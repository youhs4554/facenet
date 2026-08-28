import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "scripts/audio2face-metahuman/run-a2f-metahuman.py"
DOC = ROOT / "docs/audio2face-metahuman-cli-hands-on.ko.md"


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
        self.assertEqual(len(options), 29)  # 28 user controls plus --help.
        missing = sorted(option for option in options if f"`{option}`" not in self.text)
        self.assertEqual(missing, [], f"undocumented CLI options: {missing}")

    def test_core_control_categories_and_truth_boundaries_exist(self):
        required = (
            "## Introduction",
            "## 1. 사전 점검",
            "## 2. 첫 번째 v3.0 영상 만들기",
            "## 3. 구도와 카메라",
            "## 4. 아바타 선택",
            "## 5. 모션 강도와 얼굴 파라미터",
            "## 6. 감정 제어",
            "## 7. 실행 환경 참고",
            "## 8. 렌더·복구·자동화 옵션",
            "## 9. 결과 검증",
            "## 전체 CLI 옵션 레퍼런스",
            "final-render applied",
            "artifact/visualization only",
            "manual_action_required",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_introduction_has_concept_and_architecture_figures(self):
        self.assertRegex(
            self.text,
            r"!\[[^]]*개념도[^]]*\]\(assets/audio2face-hands-on/figures/concept-overview-general-generated-v3\.png\)",
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
        self.assertGreaterEqual(
            sum("/vnc/" in target for target in targets), 6,
            "at least six real VNC screenshots are required",
        )
        self.assertGreaterEqual(
            sum("/results/" in target for target in targets), 8,
            "at least eight result/evidence images are required",
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
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)


if __name__ == "__main__":
    unittest.main()
