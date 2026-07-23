import os
import tempfile
import unittest

import cv2
import numpy as np
import pandas as pd

from pyfeat_analyzer import encode_jpeg_data_url
from pyfeat_web_demo import create_app


class FakeLiveAnalyzer:
    device_name = "cpu"

    def __init__(self):
        self.started = False
        self.configured = None

    def start_loading(self):
        self.started = True

    def configure(self, **kwargs):
        self.configured = kwargs
        if kwargs.get("device"):
            self.device_name = kwargs["device"]

    def snapshot(self):
        return {
            "ready": True,
            "state": "ready",
            "device": self.device_name,
            "error": "",
            "labels": {"emotions": ["happiness"], "aus": ["AU12"]},
        }

    def analyze_fex(self, frame):
        return pd.DataFrame(
            [
                {
                    "FaceRectX": 1,
                    "FaceRectY": 2,
                    "FaceRectWidth": 3,
                    "FaceRectHeight": 4,
                    "mesh_x_0": 10,
                    "mesh_y_0": 20,
                    "mesh_x_1": 11,
                    "mesh_y_1": 21,
                    "Happy": 0.75,
                    "AU12": 0.8,
                    "browInnerUp": 0.3,
                    "valence": 0.2,
                    "arousal": 0.1,
                }
            ]
        )

    def analyze_video_fex(self, video):
        return pd.DataFrame(
            [
                {
                    "frame": 0,
                    "FaceRectX": 5,
                    "FaceRectY": 6,
                    "FaceRectWidth": 7,
                    "FaceRectHeight": 8,
                    "mesh_x_0": 15,
                    "mesh_y_0": 16,
                    "Happy": 0.66,
                    "AU12": 0.55,
                }
            ]
        )


class PyFeatLiveApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_config = os.environ.get("PYFEAT_LIVE_CONFIG_DIR")
        self.old_sessions = os.environ.get("PYFEAT_LIVE_SESSION_DIR")
        os.environ["PYFEAT_LIVE_CONFIG_DIR"] = self.tmp.name
        os.environ["PYFEAT_LIVE_SESSION_DIR"] = os.path.join(self.tmp.name, "sessions")

    def tearDown(self):
        if self.old_config is None:
            os.environ.pop("PYFEAT_LIVE_CONFIG_DIR", None)
        else:
            os.environ["PYFEAT_LIVE_CONFIG_DIR"] = self.old_config
        if self.old_sessions is None:
            os.environ.pop("PYFEAT_LIVE_SESSION_DIR", None)
        else:
            os.environ["PYFEAT_LIVE_SESSION_DIR"] = self.old_sessions
        self.tmp.cleanup()

    def make_client(self):
        analyzer = FakeLiveAnalyzer()
        app = create_app(analyzer)
        app.testing = True
        return app.test_client(), analyzer

    def test_system_endpoints_report_health_compute_and_capabilities(self):
        client, _ = self.make_client()

        health = client.get("/api/system/health")
        compute = client.get("/api/system/compute")
        caps = client.get("/api/system/detector-capabilities")
        geometry = client.get("/api/system/overlay-geometry")

        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.get_json()["ok"])
        self.assertTrue(compute.get_json()["cpu"]["available"])
        self.assertEqual(caps.get_json()["Detectorv2"]["landmark_space"], "mp478")
        self.assertIn("mp_tess", geometry.get_json()["edges"])
        self.assertIn("auMesh", geometry.get_json())

    def test_presets_endpoint_includes_builtin_presets(self):
        client, _ = self.make_client()

        response = client.get("/api/presets")

        self.assertEqual(response.status_code, 200)
        preset_ids = {preset["id"] for preset in response.get_json()["presets"]}
        self.assertIn("v2-standard", preset_ids)
        self.assertIn("classic-img2pose", preset_ids)

    def test_live_configure_updates_analyzer_and_generation(self):
        client, analyzer = self.make_client()

        response = client.post(
            "/api/live/configure",
            json={"detector_type": "Detectorv2", "device": "cpu", "preset_id": "v2-fast"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(analyzer.started)
        self.assertEqual(analyzer.configured["device"], "cpu")
        self.assertEqual(payload["generation"], 1)
        self.assertEqual(payload["capabilities"]["landmark_space"], "mp478")

    def test_live_frame_returns_pyfeat_live_face_payload(self):
        client, _ = self.make_client()
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        data_url = encode_jpeg_data_url(image)

        response = client.post("/api/live/frame", json={"image": data_url})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["frame"], [10, 8])
        self.assertEqual(payload["face_count"], 1)
        self.assertEqual(payload["faces"][0]["rect"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(payload["faces"][0]["lm"], [10.0, 20.0, 11.0, 21.0])
        self.assertEqual(payload["faces"][0]["emotions"]["happiness"], 0.75)
        self.assertEqual(payload["faces"][0]["aus"]["AU12"], 0.8)
        self.assertEqual(payload["faces"][0]["blendshapes"]["browInnerUp"], 0.3)

    def test_live_frame_accepts_raw_jpeg_body_for_low_latency_streaming(self):
        client, _ = self.make_client()
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)

        response = client.post(
            "/api/live/frame",
            data=encoded.tobytes(),
            headers={"Content-Type": "image/jpeg"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["frame"], [10, 8])
        self.assertEqual(payload["face_count"], 1)

    def test_live_recording_writes_session_frames_and_annotations(self):
        client, _ = self.make_client()
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        data_url = encode_jpeg_data_url(image)

        started = client.post("/api/live/recording/start", json={"label": "demo"})
        frame = client.post("/api/live/frame", json={"image": data_url})
        stopped = client.post("/api/live/recording/stop")

        self.assertEqual(started.status_code, 201)
        self.assertEqual(frame.status_code, 200)
        self.assertTrue(stopped.get_json()["stopped"])

        session_id = started.get_json()["recording"]["id"]
        sessions = client.get("/api/sessions").get_json()["sessions"]
        session = client.get(f"/api/sessions/{session_id}").get_json()["session"]
        frames = client.get(f"/api/sessions/{session_id}/frames").get_json()["frames"]
        first_frame = client.get(f"/api/sessions/{session_id}/frame/0").get_json()["frame"]
        annotations = client.post(
            f"/api/sessions/{session_id}/annotations",
            json={"annotations": [{"kind": "event", "frame": 0}]},
        ).get_json()

        self.assertEqual(len(sessions), 1)
        self.assertEqual(session["label"], "demo")
        self.assertEqual(session["frame_count"], 1)
        self.assertEqual(len(frames), 1)
        self.assertEqual(first_frame["face_count"], 1)
        self.assertEqual(annotations["annotations"][0]["kind"], "event")

    def test_analyze_queue_processes_image_into_viewer_session(self):
        client, _ = self.make_client()
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        data_url = encode_jpeg_data_url(image)

        added = client.post("/api/analyze/queue", json={"image": data_url, "label": "batch image"})
        ran = client.post("/api/analyze/queue/run")

        self.assertEqual(added.status_code, 201)
        payload = ran.get_json()
        self.assertEqual(payload["state"], "idle")
        self.assertEqual(payload["items"][0]["status"], "completed")

        session_id = payload["items"][0]["session_id"]
        session = client.get(f"/api/sessions/{session_id}").get_json()["session"]
        frame = client.get(f"/api/sessions/{session_id}/frame/0").get_json()["frame"]

        self.assertEqual(session["source"], "analyze")
        self.assertEqual(session["label"], "batch image")
        self.assertEqual(frame["source"], "analyze")
        self.assertEqual(frame["face_count"], 1)

    def test_analyze_queue_processes_video_into_viewer_session(self):
        client, _ = self.make_client()
        video = "data:video/mp4;base64,AAAA"

        added = client.post("/api/analyze/queue", json={"video": video, "label": "batch video"})
        ran = client.post("/api/analyze/queue/run")

        self.assertEqual(added.status_code, 201)
        payload = ran.get_json()
        self.assertEqual(payload["items"][0]["status"], "completed")

        session_id = payload["items"][0]["session_id"]
        session = client.get(f"/api/sessions/{session_id}").get_json()["session"]
        frame = client.get(f"/api/sessions/{session_id}/frame/0").get_json()["frame"]

        self.assertEqual(session["input_kind"], "video")
        self.assertEqual(frame["faces"][0]["rect"], [5.0, 6.0, 7.0, 8.0])


if __name__ == "__main__":
    unittest.main()
