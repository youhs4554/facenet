import base64
import unittest

import cv2
import numpy as np


class WebDemoTests(unittest.TestCase):
    def test_decode_data_url_accepts_browser_jpeg_payload(self):
        from web_demo import decode_image_data_url

        image = np.full((8, 10, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        payload = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")

        decoded = decode_image_data_url(payload)

        self.assertEqual(decoded.shape, image.shape)

    def test_create_app_uses_injected_analyzer(self):
        from web_demo import create_app, encode_jpeg_data_url

        class FakeAnalyzer:
            device_name = "mps"

            def analyze(self, frame):
                annotated = np.zeros((6, 7, 3), dtype=np.uint8)
                return annotated, {
                    "emotion": {"label": "Happy", "confidence": 0.91},
                    "aus": [{"code": "AU12", "name_en": "Lip Corner Puller", "name_ko": "입꼬리 당김", "value": 0.73}],
                    "fps": 12.3,
                }

        app = create_app(analyzer=FakeAnalyzer())
        client = app.test_client()
        source = encode_jpeg_data_url(np.zeros((6, 7, 3), dtype=np.uint8))

        response = client.post("/api/analyze", json={"image": source})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["device"], "mps")
        self.assertTrue(body["image"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(body["analysis"]["emotion"]["label"], "Happy")
        self.assertEqual(body["analysis"]["aus"][0]["name_ko"], "입꼬리 당김")

    def test_status_includes_au_glossary(self):
        from web_demo import create_app

        app = create_app(analyzer=object())
        body = app.test_client().get("/api/status").get_json()

        self.assertIn({"code": "AU12", "name_en": "Lip Corner Puller", "name_ko": "입꼬리 당김"}, body["aus"])


if __name__ == "__main__":
    unittest.main()
