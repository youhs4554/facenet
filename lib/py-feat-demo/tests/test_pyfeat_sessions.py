import tempfile
import unittest
from pathlib import Path

from pyfeat_live_core.sessions import (
    append_frame,
    create_session,
    list_sessions,
    read_annotations,
    read_frame,
    read_frames,
    read_session,
    save_annotations,
)


class PyFeatSessionTests(unittest.TestCase):
    def test_session_lifecycle_persists_metadata_frames_and_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata = create_session({"source": "test"}, root=root)
            session_id = metadata["id"]

            append_frame(session_id, {"id": 1, "faces": []}, root=root)
            save_annotations(session_id, {"annotations": [{"kind": "event", "frame": 0}]}, root=root)

            listed = list_sessions(root=root)
            loaded = read_session(session_id, root=root)
            frames = read_frames(session_id, root=root)
            frame = read_frame(session_id, 0, root=root)
            annotations = read_annotations(session_id, root=root)

        self.assertEqual(len(listed), 1)
        self.assertEqual(loaded["id"], session_id)
        self.assertEqual(loaded["source"], "test")
        self.assertEqual(loaded["frame_count"], 1)
        self.assertTrue(loaded["has_frames"])
        self.assertEqual(frames, [{"faces": [], "id": 1}])
        self.assertEqual(frame["id"], 1)
        self.assertEqual(annotations["annotations"][0]["kind"], "event")

    def test_read_frame_rejects_out_of_range_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = create_session(root=root)

            with self.assertRaises(IndexError):
                read_frame(session["id"], 0, root=root)


if __name__ == "__main__":
    unittest.main()
