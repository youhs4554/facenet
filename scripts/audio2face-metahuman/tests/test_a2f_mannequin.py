import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
MODULE = ROOT / "a2f_mannequin.py"
MODEL_DIR = REPO / ".tools/audio2face3d/v3/models/Audio2Face-3D-v3.0-b741327"
DATASET_DIR = (
    REPO
    / ".tools/audio2face3d/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire"
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MannequinGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motion = load("a2f_motion_mannequin_test", ROOT / "a2f_motion.py")
        cls.module = load("a2f_mannequin", MODULE)
        cls.basis = cls.module.load_nvidia_mannequin_basis(
            MODEL_DIR / "bs_skin_Claire.npz",
            MODEL_DIR / "bs_tongue_Claire.npz",
        )

    def test_official_basis_maps_exact_a2f_68_and_records_provenance(self):
        self.assertEqual(self.basis.curve_names, tuple(self.motion.BLENDSHAPE_NAMES))
        self.assertEqual(self.basis.skin_neutral.shape, (24002, 3))
        self.assertEqual(self.basis.tongue_neutral.shape, (5602, 3))
        self.assertEqual(self.basis.skin_deltas.shape, (52, 24002, 3))
        self.assertEqual(self.basis.tongue_deltas.shape, (16, 5602, 3))
        self.assertEqual(self.basis.license, "NVIDIA Open Model License")
        self.assertIn("Audio2Face-3D-v3.0", self.basis.source_model)

    def test_zero_weights_return_neutral_and_distinct_expression_deforms_geometry(self):
        zero = np.zeros(68, dtype=np.float32)
        neutral_skin, neutral_tongue = self.module.deform_mannequin(self.basis, zero)
        self.assertTrue(np.array_equal(neutral_skin, self.basis.skin_neutral))
        self.assertTrue(np.array_equal(neutral_tongue, self.basis.tongue_neutral))

        jaw = zero.copy()
        jaw[self.motion.BLENDSHAPE_NAMES.index("JawOpen")] = 0.8
        jaw_skin, jaw_tongue = self.module.deform_mannequin(self.basis, jaw)
        self.assertGreater(float(np.max(np.abs(jaw_skin - neutral_skin))), 0.1)
        self.assertTrue(np.array_equal(jaw_tongue, neutral_tongue))

        combined = zero.copy()
        combined[self.motion.BLENDSHAPE_NAMES.index("JawOpen")] = 0.8
        combined[self.motion.BLENDSHAPE_NAMES.index("MouthClose")] = 0.4
        combined_skin, _ = self.module.deform_mannequin(self.basis, combined)
        expected_skin = (
            self.basis.skin_neutral
            + 0.8
            * self.basis.skin_deltas[
                self.motion.BLENDSHAPE_NAMES.index("JawOpen")
            ]
            + 0.4
            * self.basis.skin_deltas[
                self.motion.BLENDSHAPE_NAMES.index("MouthClose")
            ]
        )
        self.assertTrue(np.allclose(combined_skin, expected_skin, atol=1e-6))

        tongue = zero.copy()
        tongue[self.motion.BLENDSHAPE_NAMES.index("TongueTipUp")] = 0.8
        tongue_skin, tongue_geometry = self.module.deform_mannequin(
            self.basis, tongue
        )
        self.assertTrue(np.array_equal(tongue_skin, neutral_skin))
        self.assertGreater(
            float(np.max(np.abs(tongue_geometry - neutral_tongue))), 0.1
        )

    def test_rendered_frame_hash_changes_with_real_geometry_and_is_deterministic(self):
        zero = np.zeros(68, dtype=np.float32)
        jaw = zero.copy()
        jaw[self.motion.BLENDSHAPE_NAMES.index("JawOpen")] = 0.8
        neutral, neutral_meta = self.module.render_mannequin_frame(
            self.basis, zero, width=640, height=540, frame_index=0,
            time_seconds=0.0, source_label="raw",
        )
        expressed, expressed_meta = self.module.render_mannequin_frame(
            self.basis, jaw, width=640, height=540, frame_index=1,
            time_seconds=1 / 30, source_label="raw",
        )
        neutral_again, _ = self.module.render_mannequin_frame(
            self.basis, zero, width=640, height=540, frame_index=0,
            time_seconds=0.0, source_label="raw",
        )
        digest = lambda image: hashlib.sha256(image.tobytes()).hexdigest()
        self.assertEqual(digest(neutral), digest(neutral_again))
        self.assertNotEqual(digest(neutral), digest(expressed))
        self.assertGreater(expressed_meta["max_vertex_displacement"], 0.1)
        self.assertEqual(neutral_meta["max_vertex_displacement"], 0.0)

    def test_frame_sequence_is_contiguous_and_geometry_hashes_vary(self):
        series = self.motion.synthetic_motion_series(frame_count=3, fps=30.0)
        jaw_index = self.motion.BLENDSHAPE_NAMES.index("JawOpen")
        series["frames"][1]["values"][jaw_index] = 0.8
        with tempfile.TemporaryDirectory() as temp_dir:
            record = self.module.render_mannequin_frames(
                series,
                self.basis,
                Path(temp_dir),
                width=320,
                height=270,
                source_label="effective",
            )
            names = [Path(item["path"]).name for item in record["frames"]]
            hashes = [item["sha256"] for item in record["frames"]]
            geometry_hashes = [item["geometry_sha256"] for item in record["frames"]]
        self.assertEqual(names, ["frame.0000.png", "frame.0001.png", "frame.0002.png"])
        self.assertNotEqual(hashes[0], hashes[1])
        self.assertNotEqual(geometry_hashes[0], geometry_hashes[1])
        self.assertEqual(geometry_hashes[0], geometry_hashes[2])

    def test_triptych_command_is_1920x1080_exact_frames_and_avatar_audio(self):
        command = self.module.build_diagnostic_triptych_command(
            ffmpeg=Path("/tools/ffmpeg"),
            avatar=Path("/run/avatar.mp4"),
            mannequin=Path("/run/mannequin.mp4"),
            curves=Path("/run/curves.mp4"),
            output=Path("/run/triptych.mp4"),
            fps=30,
            frame_count=109,
        )
        joined = " ".join(command)
        self.assertIn("vstack=inputs=2", joined)
        self.assertIn("hstack=inputs=2", joined)
        self.assertIn("pad=1280:1080", joined)
        self.assertIn("settb=AVTB", joined)
        self.assertIn("setpts=N/(30*TB)", joined)
        self.assertIn("-map 0:a:0", joined)
        self.assertIn("-frames:v 109", joined)
        self.assertNotIn("-shortest", command)

    def test_official_claire_topology_renders_clean_triangle_surface(self):
        basis = self.module.load_nvidia_mannequin_basis(
            DATASET_DIR / "bs_data/bs_skin.npz",
            DATASET_DIR / "bs_data/bs_tongue.npz",
            topology_path=(
                DATASET_DIR / "geom/fullface/claire_lowres_topology.json"
            ),
        )
        self.assertGreater(len(basis.skin_triangles), 2500)
        self.assertGreater(len(basis.tongue_triangles), 900)
        self.assertEqual(basis.render_mode, "triangle_surface")
        self.assertIn("evaluation", basis.license.casefold())
        image, metadata = self.module.render_mannequin_frame(
            basis,
            np.zeros(68, dtype=np.float32),
            width=640,
            height=540,
            frame_index=0,
            time_seconds=0.0,
            source_label="raw",
        )
        pixels = np.asarray(image)
        background = np.array([10, 14, 22], dtype=np.uint8)
        covered = np.any(pixels != background, axis=2)
        self.assertGreater(int(covered.sum()), 60000)
        self.assertEqual(metadata["render_mode"], "triangle_surface")
        self.assertEqual(
            metadata["semantic_label"],
            "Claire reference geometry — pre-MetaHuman retarget",
        )

    def test_resampled_impulse_deforms_mannequin_at_same_master_frame(self):
        series = self.motion.synthetic_motion_series(frame_count=5, fps=2.0)
        times = [0.0, 0.47, 1.0, 1.53, 2.0]
        jaw = self.motion.BLENDSHAPE_NAMES.index("JawOpen")
        for frame, timestamp in zip(series["frames"], times):
            frame["time_seconds"] = timestamp
            frame["values"][jaw] = 0.8 if timestamp == 1.0 else 0.0
        sampled = self.motion.resample_series(series, fps=30.0, frame_count=61)
        neutral_skin, _ = self.module.deform_mannequin(
            self.basis, sampled["frames"][0]["values"]
        )
        pulse_skin, _ = self.module.deform_mannequin(
            self.basis, sampled["frames"][30]["values"]
        )
        self.assertEqual(sampled["frames"][30]["time_seconds"], 1.0)
        self.assertGreater(
            float(np.max(np.abs(pulse_skin - neutral_skin))), 0.1
        )


if __name__ == "__main__":
    unittest.main()
