import unittest

from pyfeat_live_core.overlay_geometry import DLIB_PARTS_EDGES, triangles_from_tessellation_edges


class PyFeatOverlayGeometryTests(unittest.TestCase):
    def test_dlib_parts_include_closed_eye_and_lip_edges(self):
        self.assertIn([41, 36], DLIB_PARTS_EDGES)
        self.assertIn([47, 42], DLIB_PARTS_EDGES)
        self.assertIn([59, 48], DLIB_PARTS_EDGES)
        self.assertIn([67, 60], DLIB_PARTS_EDGES)

    def test_triangles_from_tessellation_edges_matches_pyfeat_live_pattern(self):
        edges = [[0, 1], [1, 2], [2, 0], [3, 4], [4, 5], [5, 3]]

        triangles = triangles_from_tessellation_edges(edges)

        self.assertEqual(triangles, [[0, 1, 2], [3, 4, 5]])


if __name__ == "__main__":
    unittest.main()
