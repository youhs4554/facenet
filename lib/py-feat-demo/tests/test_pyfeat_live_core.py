import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pyfeat_live_core.capabilities import capabilities_for, compute_info
from pyfeat_live_core.presets import (
    BUILTIN_PRESET_IDS,
    Preset,
    load_presets,
    save_presets,
)
from pyfeat_live_core.serialization import serialize_faces


class PyFeatLiveCoreTests(unittest.TestCase):
    def test_detectorv2_capabilities_include_dense_outputs(self):
        caps = capabilities_for("Detectorv2")

        self.assertEqual(caps["landmark_space"], "mp478")
        self.assertTrue(caps["has_valence_arousal"])
        self.assertTrue(caps["has_blendshapes"])
        self.assertTrue(caps["has_gaze"])

    def test_detectorv1_capabilities_are_classic(self):
        caps = capabilities_for("Detectorv1")

        self.assertEqual(caps["landmark_space"], "dlib68")
        self.assertFalse(caps["has_valence_arousal"])
        self.assertFalse(caps["has_blendshapes"])

    def test_compute_info_always_reports_cpu(self):
        info = compute_info()

        self.assertTrue(info["cpu"]["available"])
        self.assertIn("mps", info)
        self.assertIn("cuda", info)

    def test_builtin_presets_load_without_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            presets = load_presets(Path(tmp) / "missing.json")

        self.assertGreaterEqual(len(presets), 4)
        self.assertEqual(BUILTIN_PRESET_IDS[0], "v2-realtime")
        self.assertTrue(any(p.id == "v2-standard" for p in presets))
        self.assertTrue(any(p.id == "classic-img2pose" for p in presets))

    def test_custom_presets_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "presets.json"
            original = [
                Preset(id="custom", name="Custom", detector_type="Detectorv2", builtin=False)
            ]

            save_presets(original, path)
            loaded = load_presets(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "custom")
        self.assertEqual(loaded[0].name, "Custom")

    def test_serialize_faces_prefers_detectorv2_mesh_columns(self):
        frame = pd.DataFrame(
            [
                {
                    "FaceRectX": 10,
                    "FaceRectY": 20,
                    "FaceRectWidth": 30,
                    "FaceRectHeight": 40,
                    "mesh_x_0": 101,
                    "mesh_y_0": 201,
                    "mesh_x_1": 102,
                    "mesh_y_1": 202,
                    "x_0": 11,
                    "y_0": 21,
                    "Pitch": 1,
                    "Roll": 2,
                    "Yaw": 3,
                    "gaze_0_x": 0.1,
                    "gaze_0_y": 0.2,
                    "gaze_0_z": 0.3,
                    "Happy": 0.7,
                    "Neutral": 0.2,
                    "AU12": 0.8,
                    "browInnerUp": 0.4,
                    "valence": 0.5,
                    "arousal": -0.2,
                }
            ]
        )

        faces = serialize_faces(frame, mp_landmarks=True)

        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0]["rect"], [10.0, 20.0, 30.0, 40.0])
        self.assertEqual(faces[0]["lm"], [101.0, 201.0, 102.0, 202.0])
        self.assertEqual(faces[0]["landmark_count"], 2)
        self.assertEqual(faces[0]["pose"], [1.0, 2.0, 3.0])
        self.assertEqual(faces[0]["gaze"], [0.1, 0.2, 0.3])
        self.assertEqual(faces[0]["emotions"]["happiness"], 0.7)
        self.assertEqual(faces[0]["aus"]["AU12"], 0.8)
        self.assertEqual(faces[0]["blendshapes"]["browInnerUp"], 0.4)
        self.assertEqual(faces[0]["valence_arousal"], {"valence": 0.5, "arousal": -0.2})


if __name__ == "__main__":
    unittest.main()
