import os
import tempfile
import unittest

import numpy as np

from pyfeat_analyzer import encode_jpeg_data_url
from pyfeat_web_demo import create_app


class FakeAnalyzer:
    device_name = "cpu"

    def __init__(self):
        self.started = False

    def start_loading(self):
        self.started = True

    def snapshot(self):
        return {
            "ready": True,
            "state": "ready",
            "device": "cpu",
            "error": "",
            "labels": {"emotions": ["happiness"], "aus": ["AU12"]},
        }

    def analyze(self, frame):
        return {
            "face_count": 1,
            "faces": [
                {
                    "box": {
                        "x": 1.0,
                        "y": 2.0,
                        "width": 3.0,
                        "height": 4.0,
                        "confidence": 0.9,
                    },
                    "emotions": [{"label": "happiness", "value": 0.8}],
                    "aus": [{"code": "AU12", "value": 0.7}],
                    "valence": 0.5,
                    "arousal": 0.4,
                    "pose": {"pitch": 0.1, "roll": 0.2, "yaw": 0.3},
                    "gaze": {"x": 0.0, "y": 0.0, "z": 1.0},
                    "mesh": [],
                }
            ],
            "primary_face": 0,
            "fps": 5.0,
            "latency_ms": 200.0,
        }


class FailingAnalyzer(FakeAnalyzer):
    def analyze(self, frame):
        raise ValueError("model failed")


class PyFeatWebDemoTests(unittest.TestCase):
    def make_client(self):
        analyzer = FakeAnalyzer()
        app = create_app(analyzer)
        app.testing = True
        return app.test_client(), analyzer

    def test_status_starts_analyzer_and_returns_ready_device(self):
        client, analyzer = self.make_client()

        response = client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(analyzer.started)
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["device"], "cpu")

    def test_status_can_skip_autoload_for_fast_initial_page_load(self):
        client, analyzer = self.make_client()

        response = client.get("/api/status?autoload=0")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(analyzer.started)

    def test_analyze_with_empty_json_returns_bad_request_error(self):
        client, _ = self.make_client()

        response = client.post("/api/analyze", json={})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_analyze_with_invalid_image_payload_returns_bad_request_error(self):
        client, _ = self.make_client()

        response = client.post("/api/analyze", json={"image": "not a jpeg"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_analyze_with_analyzer_value_error_returns_server_error(self):
        app = create_app(FailingAnalyzer())
        app.testing = True
        client = app.test_client()
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        data_url = encode_jpeg_data_url(image)

        response = client.post("/api/analyze", json={"image": data_url})

        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.get_json())

    def test_analyze_with_jpeg_data_url_returns_analysis(self):
        client, _ = self.make_client()
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        data_url = encode_jpeg_data_url(image)

        response = client.post("/api/analyze", json={"image": data_url})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["device"], "cpu")
        self.assertEqual(payload["analysis"]["face_count"], 1)
        self.assertEqual(payload["analysis"]["faces"][0]["emotions"][0]["label"], "happiness")

    def test_index_serves_configured_static_index(self):
        app = create_app(FakeAnalyzer())
        app.testing = True
        with tempfile.TemporaryDirectory() as static_dir:
            app.static_folder = static_dir
            index_path = os.path.join(static_dir, "index.html")
            with open(index_path, "w", encoding="utf-8") as index_file:
                index_file.write("<!doctype html><title>Py-Feat Demo</title>")

            response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Py-Feat Demo", response.data)


if __name__ == "__main__":
    unittest.main()
