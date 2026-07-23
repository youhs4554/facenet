import unittest

from pyfeat_live_core.analysis_queue import AnalysisQueue


class PyFeatAnalyzeQueueTests(unittest.TestCase):
    def test_queue_add_list_remove_and_state(self):
        queue = AnalysisQueue()

        item = queue.add_image("data:image/jpeg;base64,abc", label="sample")
        queue.set_state("running")

        snapshot = queue.snapshot()

        self.assertEqual(snapshot["state"], "running")
        self.assertEqual(snapshot["items"][0]["id"], item.id)
        self.assertEqual(snapshot["items"][0]["label"], "sample")
        self.assertEqual(queue.pending_items()[0].id, item.id)
        self.assertTrue(queue.remove(item.id))
        self.assertEqual(queue.list_items(), [])

    def test_queue_accepts_video_items(self):
        queue = AnalysisQueue()

        item = queue.add_video("data:video/mp4;base64,AAAA", label="clip")

        self.assertEqual(item.kind, "video")
        self.assertEqual(queue.snapshot()["items"][0]["label"], "clip")


if __name__ == "__main__":
    unittest.main()
