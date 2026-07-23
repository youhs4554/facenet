# Py-Feat Web Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Flask webcam demo for Py-Feat `Detectorv2` that follows the existing OpenFace web demo pattern while showing Py-Feat-specific outputs.

**Architecture:** Create an isolated `lib/py-feat-demo/` app. The Flask server owns routing, image decode, status, and analyzer injection; `pyfeat_analyzer.py` owns device selection, Py-Feat loading, inference, and normalized JSON; static HTML/CSS/JS owns camera capture, request pacing, overlays, and dashboard rendering.

**Tech Stack:** Python 3, Flask, NumPy, OpenCV, Py-Feat, pytest, plain HTML/CSS/JavaScript.

---

## Repository Note

`/Users/hossay/workspace/main/facenet` is not currently a git repository. Do not run commit steps from this workspace unless a repository is initialized or the user provides a different git root. When a task says "checkpoint", record the completed checkbox in this plan or `docs/TODO.md`; do not invent a commit in the nested OpenFace repository.

## File Structure

- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/requirements.txt`
  - Runtime and test dependencies for this isolated demo.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_analyzer.py`
  - Device selection, image data URL helpers, analyzer state, Py-Feat wrapper, and normalization.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_web_demo.py`
  - Flask app factory, `/`, `/api/status`, `/api/analyze`, and CLI.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/index.html`
  - One-screen dashboard markup.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/styles.css`
  - Compact dashboard styling aligned with the approved design.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/app.js`
  - Webcam capture, status polling, API requests, overlay drawing, metric rendering.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_analyzer.py`
  - Unit tests for data URL helpers, device selection, and normalization.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_web_demo.py`
  - Flask contract tests with fake analyzer injection.
- Create `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/README.md`
  - Setup, run, model download/cache, device options, and verification notes.
- Modify `/Users/hossay/workspace/main/facenet/docs/TODO.md`
  - Mark plan creation complete and implementation active when execution begins.

## Shared API Contract

Use this shape throughout tests, server, and frontend:

```json
{
  "analysis": {
    "face_count": 1,
    "faces": [
      {
        "box": {"x": 10, "y": 20, "width": 120, "height": 140, "confidence": 0.98},
        "emotions": [{"label": "happiness", "value": 0.72}],
        "aus": [{"code": "AU12", "value": 0.63}],
        "valence": 0.34,
        "arousal": 0.12,
        "pose": {"pitch": 0.1, "roll": -0.02, "yaw": 0.2},
        "gaze": {"x": 0.0, "y": 0.0, "z": 1.0},
        "mesh": [{"x": 0.42, "y": 0.31, "z": -0.02}]
      }
    ],
    "primary_face": 0,
    "fps": 4.7,
    "latency_ms": 212.5
  },
  "device": "mps"
}
```

## Task 1: Dependencies and Analyzer Unit Tests

**Files:**
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/requirements.txt`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_analyzer.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_analyzer.py`

- [x] **Step 1: Create dependency file**

Create `requirements.txt` with:

```text
flask
numpy
opencv-python-headless
pandas
pytest
py-feat
```

- [x] **Step 2: Write failing analyzer tests**

Create `tests/test_pyfeat_analyzer.py` with:

```python
import base64
import unittest

import cv2
import numpy as np
import pandas as pd

from pyfeat_analyzer import (
    AU_LABELS,
    EMOTION_LABELS,
    AnalyzerState,
    decode_image_data_url,
    encode_jpeg_data_url,
    normalize_result,
    select_device,
)


class AnalyzerHelperTests(unittest.TestCase):
    def test_decode_image_data_url_accepts_browser_jpeg_payload(self):
        image = np.full((8, 10, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        payload = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")

        decoded = decode_image_data_url(payload)

        self.assertEqual(decoded.shape, image.shape)

    def test_encode_jpeg_data_url_returns_browser_payload(self):
        payload = encode_jpeg_data_url(np.zeros((6, 7, 3), dtype=np.uint8))

        self.assertTrue(payload.startswith("data:image/jpeg;base64,"))

    def test_select_device_honors_explicit_value(self):
        self.assertEqual(select_device("cpu"), "cpu")
        self.assertEqual(select_device("mps"), "mps")

    def test_state_reports_idle_by_default(self):
        state = AnalyzerState(device_name="cpu")

        self.assertEqual(state.snapshot()["state"], "idle")
        self.assertFalse(state.snapshot()["ready"])


class NormalizeResultTests(unittest.TestCase):
    def test_normalize_result_handles_no_face(self):
        result = normalize_result(pd.DataFrame(), image_shape=(40, 50, 3), latency_ms=100.0)

        self.assertEqual(result["face_count"], 0)
        self.assertEqual(result["faces"], [])
        self.assertIsNone(result["primary_face"])
        self.assertEqual(result["latency_ms"], 100.0)

    def test_normalize_result_maps_fex_like_columns(self):
        row = {
            "FaceRectX": 10,
            "FaceRectY": 20,
            "FaceRectWidth": 120,
            "FaceRectHeight": 140,
            "FaceScore": 0.98,
            "happiness": 0.72,
            "anger": 0.03,
            "disgust": 0.01,
            "fear": 0.02,
            "sadness": 0.04,
            "surprise": 0.10,
            "neutral": 0.08,
            "AU12": 0.63,
            "AU01": 0.25,
            "valence": 0.34,
            "arousal": 0.12,
            "Pitch": 0.1,
            "Roll": -0.02,
            "Yaw": 0.2,
            "gaze_0_x": 0.0,
            "gaze_0_y": 0.0,
            "gaze_0_z": 1.0,
            "x_0": 0.42,
            "y_0": 0.31,
            "z_0": -0.02,
        }

        result = normalize_result(pd.DataFrame([row]), image_shape=(240, 320, 3), latency_ms=200.0)

        self.assertEqual(result["face_count"], 1)
        self.assertEqual(result["primary_face"], 0)
        face = result["faces"][0]
        self.assertEqual(face["box"]["x"], 10.0)
        self.assertEqual(face["box"]["width"], 120.0)
        self.assertEqual(face["box"]["confidence"], 0.98)
        self.assertIn({"label": "happiness", "value": 0.72}, face["emotions"])
        self.assertIn({"code": "AU12", "value": 0.63}, face["aus"])
        self.assertEqual(face["valence"], 0.34)
        self.assertEqual(face["arousal"], 0.12)
        self.assertEqual(face["pose"], {"pitch": 0.1, "roll": -0.02, "yaw": 0.2})
        self.assertEqual(face["gaze"], {"x": 0.0, "y": 0.0, "z": 1.0})
        self.assertEqual(face["mesh"], [{"x": 0.42, "y": 0.31, "z": -0.02}])

    def test_label_lists_are_not_empty(self):
        self.assertGreaterEqual(len(EMOTION_LABELS), 7)
        self.assertGreaterEqual(len(AU_LABELS), 8)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 3: Run analyzer tests to verify they fail**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests/test_pyfeat_analyzer.py -v
```

Expected: FAIL because `pyfeat_analyzer.py` does not exist or missing symbols.

- [x] **Step 4: Implement analyzer helpers and normalization**

Create `pyfeat_analyzer.py` with:

```python
import base64
import math
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import cv2
import numpy as np


EMOTION_LABELS = ["anger", "disgust", "fear", "happiness", "sadness", "surprise", "neutral"]
AU_LABELS = [
    "AU01",
    "AU02",
    "AU04",
    "AU05",
    "AU06",
    "AU07",
    "AU09",
    "AU10",
    "AU11",
    "AU12",
    "AU14",
    "AU15",
    "AU17",
    "AU20",
    "AU23",
    "AU24",
    "AU25",
    "AU26",
    "AU28",
    "AU43",
]


def decode_image_data_url(data_url: str) -> np.ndarray:
    if "," in data_url:
        _, payload = data_url.split(",", 1)
    else:
        payload = data_url
    raw = base64.b64decode(payload)
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Invalid image payload")
    return image


def encode_jpeg_data_url(image: np.ndarray, quality: int = 86) -> str:
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("Could not encode image")
    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def select_device(requested: str = "auto") -> str:
    requested = requested or "auto"
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _to_records(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if hasattr(result, "to_pandas"):
        result = result.to_pandas()
    if hasattr(result, "to_dict"):
        try:
            return result.to_dict(orient="records")
        except TypeError:
            pass
    if isinstance(result, list):
        return [dict(item) for item in result]
    if isinstance(result, dict):
        if "faces" in result:
            return list(result["faces"])
        return [result]
    return []


def _number(row: dict[str, Any], names: list[str], default: float = 0.0) -> float:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        return number
    return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _box(row: dict[str, Any]) -> dict[str, float]:
    x = _number(row, ["FaceRectX", "face_x", "x", "box_x", "bbox_x"])
    y = _number(row, ["FaceRectY", "face_y", "y", "box_y", "bbox_y"])
    width = _number(row, ["FaceRectWidth", "face_width", "width", "box_width", "bbox_width"])
    height = _number(row, ["FaceRectHeight", "face_height", "height", "box_height", "bbox_height"])
    if width <= 0:
        x2 = _number(row, ["FaceRectX2", "x2", "bbox_x2"], x)
        width = max(0.0, x2 - x)
    if height <= 0:
        y2 = _number(row, ["FaceRectY2", "y2", "bbox_y2"], y)
        height = max(0.0, y2 - y)
    confidence = _clamp(_number(row, ["FaceScore", "face_score", "confidence", "score"], 1.0))
    return {"x": x, "y": y, "width": width, "height": height, "confidence": confidence}


def _emotions(row: dict[str, Any]) -> list[dict[str, float | str]]:
    items = []
    for label in EMOTION_LABELS:
        value = _clamp(_number(row, [label, label.capitalize(), f"emotion_{label}"]))
        items.append({"label": label, "value": value})
    return sorted(items, key=lambda item: float(item["value"]), reverse=True)


def _aus(row: dict[str, Any]) -> list[dict[str, float | str]]:
    items = []
    for code in AU_LABELS:
        value = _clamp(_number(row, [code, code.replace("AU", "AU_"), code.lower()]))
        items.append({"code": code, "value": value})
    return sorted(items, key=lambda item: float(item["value"]), reverse=True)


def _mesh(row: dict[str, Any], max_points: int = 478) -> list[dict[str, float]]:
    points = []
    for index in range(max_points):
        x_name = f"x_{index}"
        y_name = f"y_{index}"
        if x_name not in row or y_name not in row:
            continue
        points.append(
            {
                "x": _number(row, [x_name]),
                "y": _number(row, [y_name]),
                "z": _number(row, [f"z_{index}"]),
            }
        )
    return points


def normalize_result(result: Any, image_shape: tuple[int, ...], latency_ms: float) -> dict[str, Any]:
    records = _to_records(result)
    faces = []
    for row in records:
        faces.append(
            {
                "box": _box(row),
                "emotions": _emotions(row),
                "aus": _aus(row),
                "valence": _number(row, ["valence", "Valence"]),
                "arousal": _number(row, ["arousal", "Arousal"]),
                "pose": {
                    "pitch": _number(row, ["Pitch", "pitch", "pose_pitch"]),
                    "roll": _number(row, ["Roll", "roll", "pose_roll"]),
                    "yaw": _number(row, ["Yaw", "yaw", "pose_yaw"]),
                },
                "gaze": {
                    "x": _number(row, ["gaze_0_x", "gaze_x", "gazeX"]),
                    "y": _number(row, ["gaze_0_y", "gaze_y", "gazeY"]),
                    "z": _number(row, ["gaze_0_z", "gaze_z", "gazeZ"], 1.0),
                },
                "mesh": _mesh(row),
            }
        )
    fps = 1000.0 / latency_ms if latency_ms > 0 else 0.0
    return {
        "face_count": len(faces),
        "faces": faces,
        "primary_face": 0 if faces else None,
        "fps": fps,
        "latency_ms": float(latency_ms),
    }


@dataclass
class AnalyzerState:
    device_name: str = "auto"
    state: str = "idle"
    error: str = ""
    _detector: Optional[Any] = field(default=None, init=False, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            device = select_device(self.device_name)
            return {
                "ready": self.state == "ready",
                "state": self.state,
                "device": device,
                "error": self.error,
                "labels": {"emotions": EMOTION_LABELS, "aus": AU_LABELS},
            }

    def start_loading(self) -> None:
        with self._lock:
            if self.state in {"loading", "ready"}:
                return
            self.state = "loading"
            self.error = ""
            self._thread = threading.Thread(target=self._load, daemon=True)
            self._thread.start()

    def _load(self) -> None:
        try:
            from feat import Detectorv2

            device = select_device(self.device_name)
            detector = Detectorv2(device=device)
            with self._lock:
                self._detector = detector
                self.state = "ready"
                self.device_name = device
        except Exception as exc:
            with self._lock:
                self.state = "error"
                self.error = str(exc)

    def analyze(self, frame: np.ndarray) -> dict[str, Any]:
        with self._lock:
            detector = self._detector
            state = self.state
        if state != "ready" or detector is None:
            raise RuntimeError("Analyzer is not ready")

        start = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp:
            temp_path = temp.name
        try:
            cv2.imwrite(temp_path, frame)
            result = detector.detect(temp_path, data_type="image")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return normalize_result(result, frame.shape, latency_ms)
```

- [x] **Step 5: Run analyzer tests to verify they pass**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests/test_pyfeat_analyzer.py -v
```

Expected: PASS.

- [x] **Step 6: Checkpoint**

Run:

```bash
git -C /Users/hossay/workspace/main/facenet rev-parse --show-toplevel
```

Expected: `fatal: not a git repository...`. Record Task 1 completion in this plan or `docs/TODO.md`; do not commit in the nested OpenFace repository.

## Task 2: Flask API Contract

**Files:**
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_web_demo.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_web_demo.py`

- [x] **Step 1: Write failing Flask tests**

Create `tests/test_pyfeat_web_demo.py` with:

```python
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
                    "box": {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0, "confidence": 0.9},
                    "emotions": [{"label": "happiness", "value": 0.8}],
                    "aus": [{"code": "AU12", "value": 0.7}],
                    "valence": 0.2,
                    "arousal": 0.1,
                    "pose": {"pitch": 0.0, "roll": 0.0, "yaw": 0.0},
                    "gaze": {"x": 0.0, "y": 0.0, "z": 1.0},
                    "mesh": [],
                }
            ],
            "primary_face": 0,
            "fps": 5.0,
            "latency_ms": 200.0,
        }


class WebDemoTests(unittest.TestCase):
    def test_status_starts_loading_and_returns_snapshot(self):
        analyzer = FakeAnalyzer()
        app = create_app(analyzer=analyzer)

        body = app.test_client().get("/api/status").get_json()

        self.assertTrue(analyzer.started)
        self.assertEqual(body["state"], "ready")
        self.assertEqual(body["device"], "cpu")

    def test_analyze_requires_image(self):
        app = create_app(analyzer=FakeAnalyzer())

        response = app.test_client().post("/api/analyze", json={})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_analyze_returns_normalized_response(self):
        app = create_app(analyzer=FakeAnalyzer())
        source = encode_jpeg_data_url(np.zeros((6, 7, 3), dtype=np.uint8))

        response = app.test_client().post("/api/analyze", json={"image": source})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["device"], "cpu")
        self.assertEqual(body["analysis"]["face_count"], 1)
        self.assertEqual(body["analysis"]["faces"][0]["emotions"][0]["label"], "happiness")


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run Flask tests to verify they fail**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests/test_pyfeat_web_demo.py -v
```

Expected: FAIL because `pyfeat_web_demo.py` does not exist.

- [x] **Step 3: Implement Flask app**

Create `pyfeat_web_demo.py` with:

```python
import argparse
import os
from typing import Optional

from flask import Flask, jsonify, request, send_from_directory

from pyfeat_analyzer import AnalyzerState, decode_image_data_url


ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")


def create_app(analyzer: Optional[object] = None) -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
    app.config["ANALYZER"] = analyzer or AnalyzerState()

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/status")
    def status():
        active = app.config["ANALYZER"]
        active.start_loading()
        return jsonify(active.snapshot())

    @app.post("/api/analyze")
    def analyze():
        body = request.get_json(silent=True) or {}
        if "image" not in body:
            return jsonify({"error": "image field is required"}), 400
        try:
            frame = decode_image_data_url(body["image"])
            analysis = app.config["ANALYZER"].analyze(frame)
            return jsonify(
                {
                    "analysis": analysis,
                    "device": app.config["ANALYZER"].snapshot().get("device", ""),
                }
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Py-Feat live browser webcam demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or mps")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    analyzer = AnalyzerState(device_name=args.device)
    app = create_app(analyzer)
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run API tests**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests/test_pyfeat_analyzer.py tests/test_pyfeat_web_demo.py -v
```

Expected: PASS.

## Task 3: Static Dashboard Shell

**Files:**
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/index.html`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/styles.css`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/app.js`

- [x] **Step 1: Create dashboard HTML**

Create `static/index.html` with:

```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Py-Feat Live Demo</title>
    <link rel="icon" href="data:," />
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <header class="app-header">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">PF</div>
        <div>
          <h1>Py-Feat Live Demo</h1>
          <p>Real-time facial expression analysis</p>
        </div>
      </div>
      <section class="header-stats" aria-label="runtime status">
        <div><span>Model</span><strong id="modelState">loading</strong></div>
        <div><span>Device</span><strong id="deviceBadge">auto</strong></div>
        <div><span>FPS</span><strong id="headerFps">0.0</strong></div>
        <div><span>Latency</span><strong id="latencyText">0 ms</strong></div>
      </section>
    </header>

    <main class="dashboard">
      <section class="left-column">
        <section class="card camera-card">
          <div class="card-title"><h2>1. Camera Input</h2></div>
          <div class="video-shell">
            <video id="camera" autoplay muted playsinline></video>
          </div>
          <canvas id="captureCanvas" hidden></canvas>
          <div class="settings-grid">
            <label>Camera <select id="cameraSelect"></select></label>
            <label>Resolution <select id="resolutionSelect"><option value="640x480">640 x 480</option><option value="960x720">960 x 720</option><option value="1280x720">1280 x 720</option></select></label>
            <label>Flip <select id="flipSelect"><option value="off">Off</option><option value="on">On</option></select></label>
            <label>Interval <input id="intervalInput" type="number" min="180" step="20" value="420" /></label>
          </div>
          <div class="run-controls">
            <button id="startBtn" type="button" disabled>Start</button>
            <button id="stopBtn" type="button" disabled>Stop</button>
          </div>
          <div id="cameraStatus" class="status-line">Waiting for model...</div>
        </section>
      </section>

      <section class="center-column">
        <section class="card output-card">
          <div class="card-title"><h2>2. Analysis Output</h2></div>
          <div class="result-frame">
            <video id="mirror" autoplay muted playsinline></video>
            <canvas id="overlayCanvas"></canvas>
            <div id="emptyState">Start를 누르면 분석 결과가 여기에 표시됩니다.</div>
            <div id="analysisStatus" class="overlay-status">Waiting</div>
          </div>
          <div class="overlay-controls">
            <label><input id="boxToggle" type="checkbox" checked /> Box</label>
            <label><input id="meshToggle" type="checkbox" checked /> Mesh</label>
            <label><input id="gazeToggle" type="checkbox" checked /> Gaze</label>
            <label><input id="poseToggle" type="checkbox" checked /> Pose</label>
            <button id="downloadBtn" type="button">Download Frame</button>
          </div>
        </section>
      </section>

      <aside class="right-column">
        <section class="card">
          <div class="card-title"><h2>3. Emotion</h2></div>
          <div id="emotionList" class="bar-list"></div>
        </section>
        <section class="card">
          <div class="card-title"><h2>4. Valence / Arousal</h2></div>
          <canvas id="vaCanvas" class="va-canvas" width="320" height="240"></canvas>
        </section>
        <section class="card">
          <div class="card-title"><h2>5. Pose & Gaze</h2></div>
          <dl class="metric-grid">
            <div><dt>Pitch</dt><dd id="posePitch">0.00</dd></div>
            <div><dt>Roll</dt><dd id="poseRoll">0.00</dd></div>
            <div><dt>Yaw</dt><dd id="poseYaw">0.00</dd></div>
            <div><dt>Gaze</dt><dd id="gazeText">0.00, 0.00, 1.00</dd></div>
          </dl>
        </section>
        <section class="card">
          <div class="card-title"><h2>6. Action Units</h2></div>
          <div id="auList" class="bar-list au-list"></div>
        </section>
      </aside>
    </main>

    <script src="/app.js"></script>
  </body>
</html>
```

- [x] **Step 2: Create CSS**

Create `static/styles.css` with:

```css
:root {
  color-scheme: light;
  --bg: #f5f7f8;
  --header: #111820;
  --surface: #ffffff;
  --text: #17202a;
  --muted: #657386;
  --border: #dce3ea;
  --line: #e9eef2;
  --accent: #208b8f;
  --green: #26a269;
  --yellow: #d99b13;
  --red: #d64545;
  --blue: #3f6fe5;
  --shadow: 0 12px 28px rgba(17, 24, 32, 0.08);
}
* { box-sizing: border-box; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0;
}
button, input, select { font: inherit; }
button, select, input {
  border: 1px solid var(--border);
  border-radius: 7px;
}
button {
  align-items: center;
  background: var(--surface);
  cursor: pointer;
  display: inline-flex;
  font-weight: 800;
  justify-content: center;
  min-height: 40px;
  padding: 0 16px;
}
button:disabled { cursor: not-allowed; opacity: 0.5; }
.app-header {
  align-items: center;
  background: var(--header);
  color: #fff;
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(320px, 1fr) minmax(520px, 1.2fr);
  min-height: 78px;
  padding: 12px 20px;
}
.brand { align-items: center; display: flex; gap: 14px; min-width: 0; }
.brand-mark {
  align-items: center;
  border: 1px solid rgba(255,255,255,0.28);
  border-radius: 8px;
  color: #9fe0d7;
  display: flex;
  font-weight: 900;
  height: 50px;
  justify-content: center;
  width: 50px;
}
.brand h1 { font-size: 26px; line-height: 1.05; margin: 0; }
.brand p { color: #c7d1dc; font-size: 14px; margin: 5px 0 0; }
.header-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.header-stats div { border-left: 1px solid rgba(255,255,255,0.16); padding: 0 14px; }
.header-stats span { color: #b7c5d3; display: block; font-size: 13px; margin-bottom: 4px; }
.header-stats strong { color: #fff; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dashboard {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(320px, 0.9fr) minmax(480px, 1.35fr) minmax(340px, 0.95fr);
  padding: 14px;
}
.left-column, .center-column, .right-column { align-content: start; display: grid; gap: 14px; min-width: 0; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow);
  min-width: 0;
  overflow: hidden;
}
.card-title { align-items: center; display: flex; min-height: 48px; padding: 11px 16px; }
.card-title h2 { font-size: 17px; line-height: 1.2; margin: 0; }
.video-shell, .result-frame {
  background: #101416;
  margin: 0 12px;
  overflow: hidden;
  position: relative;
}
.video-shell { aspect-ratio: 4 / 3; border-radius: 7px; }
.result-frame {
  align-items: center;
  aspect-ratio: 4 / 3;
  border-radius: 7px;
  display: flex;
  justify-content: center;
}
video { display: block; height: 100%; object-fit: cover; width: 100%; }
body.flip-video video { transform: scaleX(-1); }
#mirror { height: 100%; object-fit: contain; width: 100%; }
#overlayCanvas { height: 100%; left: 0; position: absolute; top: 0; width: 100%; }
#emptyState {
  color: #b7c4c8;
  font-size: 14px;
  padding: 18px;
  position: absolute;
  text-align: center;
}
.has-stream #emptyState { display: none; }
.overlay-status {
  background: rgba(16, 20, 22, 0.76);
  border-radius: 6px;
  bottom: 12px;
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  left: 12px;
  padding: 7px 10px;
  position: absolute;
}
.settings-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 12px;
}
.settings-grid label { color: var(--muted); display: grid; font-size: 12px; gap: 5px; }
.settings-grid select, .settings-grid input { min-height: 36px; padding: 0 9px; width: 100%; }
.run-controls, .overlay-controls {
  align-items: center;
  border-top: 1px solid var(--line);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px;
}
#startBtn { background: var(--green); border-color: var(--green); color: #fff; }
#stopBtn { background: var(--red); border-color: var(--red); color: #fff; }
.status-line { border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; padding: 10px 12px; }
.bar-list { display: grid; gap: 9px; padding: 0 14px 14px; }
.metric-row { display: grid; gap: 5px; }
.metric-line { align-items: center; display: grid; gap: 8px; grid-template-columns: minmax(90px, 1fr) 1.4fr 46px; }
.metric-name { color: var(--text); font-size: 13px; font-weight: 750; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.metric-value { color: var(--muted); font-variant-numeric: tabular-nums; text-align: right; }
.bar-track { background: #edf1f4; border-radius: 999px; height: 10px; overflow: hidden; }
.bar-fill { background: var(--accent); height: 100%; width: 0; }
.va-canvas { display: block; height: auto; max-width: 100%; padding: 0 14px 14px; width: 100%; }
.metric-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; padding: 0 14px 14px; }
.metric-grid div { background: #f8fafb; border: 1px solid var(--line); border-radius: 7px; padding: 10px; }
.metric-grid dt { color: var(--muted); font-size: 12px; }
.metric-grid dd { font-size: 18px; font-weight: 850; margin: 4px 0 0; }
@media (max-width: 1180px) {
  .app-header, .dashboard { grid-template-columns: 1fr; }
}
```

- [x] **Step 3: Create minimal JS boot file**

Create `static/app.js` with:

```javascript
const state = {
  labels: { emotions: [], aus: [] },
  latestAnalysis: null,
  vaTrail: [],
};

function byId(id) {
  return document.getElementById(id);
}

async function loadStatus() {
  const response = await fetch("/api/status");
  const body = await response.json();
  state.labels = body.labels || { emotions: [], aus: [] };
  byId("modelState").textContent = body.state || "unknown";
  byId("deviceBadge").textContent = body.device || "auto";
  byId("cameraStatus").textContent = body.error || (body.ready ? "Model ready." : "Loading model...");
  byId("startBtn").disabled = !body.ready;
  renderBars(byId("emotionList"), (state.labels.emotions || []).map((label) => ({ label, value: 0 })), "label");
  renderBars(byId("auList"), (state.labels.aus || []).map((code) => ({ code, value: 0 })), "code");
  if (!body.ready && body.state !== "error") {
    window.setTimeout(loadStatus, 1500);
  }
}

function renderBars(container, items, nameKey) {
  container.innerHTML = "";
  for (const item of items || []) {
    const value = Math.max(0, Math.min(1, Number(item.value || 0)));
    const row = document.createElement("div");
    row.className = "metric-row";
    row.innerHTML = `
      <div class="metric-line">
        <span class="metric-name">${item[nameKey] || ""}</span>
        <div class="bar-track"><div class="bar-fill" style="width: ${(value * 100).toFixed(1)}%"></div></div>
        <span class="metric-value">${value.toFixed(2)}</span>
      </div>
    `;
    container.appendChild(row);
  }
}

function drawValenceArousal() {
  const canvas = byId("vaCanvas");
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#dce3ea";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(width / 2, 10);
  context.lineTo(width / 2, height - 10);
  context.moveTo(10, height / 2);
  context.lineTo(width - 10, height / 2);
  context.stroke();
  for (const [index, point] of state.vaTrail.entries()) {
    const x = width / 2 + Math.max(-1, Math.min(1, point.valence)) * (width / 2 - 20);
    const y = height / 2 - Math.max(-1, Math.min(1, point.arousal)) * (height / 2 - 20);
    context.fillStyle = index === state.vaTrail.length - 1 ? "#208b8f" : "rgba(32, 139, 143, 0.28)";
    context.beginPath();
    context.arc(x, y, index === state.vaTrail.length - 1 ? 6 : 3, 0, Math.PI * 2);
    context.fill();
  }
}

loadStatus();
drawValenceArousal();
```

- [x] **Step 4: Smoke-test static route**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests/test_pyfeat_web_demo.py -v
```

Expected: PASS. Static files are not deeply tested yet, but Flask app construction must still pass.

## Task 4: Webcam Capture, Request Loop, and Rendering

**Files:**
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/app.js`

- [x] **Step 1: Replace `static/app.js` with complete interactive implementation**

Replace the file with:

```javascript
const video = document.getElementById("camera");
const mirror = document.getElementById("mirror");
const captureCanvas = document.getElementById("captureCanvas");
const overlayCanvas = document.getElementById("overlayCanvas");
const resultFrame = document.querySelector(".result-frame");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const cameraSelect = document.getElementById("cameraSelect");
const resolutionSelect = document.getElementById("resolutionSelect");
const flipSelect = document.getElementById("flipSelect");
const intervalInput = document.getElementById("intervalInput");
const analysisStatus = document.getElementById("analysisStatus");
const downloadBtn = document.getElementById("downloadBtn");

const state = {
  labels: { emotions: [], aus: [] },
  stream: null,
  running: false,
  inFlight: false,
  lastRequestAt: 0,
  latestAnalysis: null,
  vaTrail: [],
};

function byId(id) {
  return document.getElementById(id);
}

function parseResolution(value) {
  const [width, height] = value.split("x").map((part) => Number(part));
  return { width, height };
}

function setStatus(text) {
  analysisStatus.textContent = text;
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const body = await response.json();
    state.labels = body.labels || { emotions: [], aus: [] };
    byId("modelState").textContent = body.state || "unknown";
    byId("deviceBadge").textContent = body.device || "auto";
    byId("cameraStatus").textContent = body.error || (body.ready ? "Model ready." : "Loading model...");
    startBtn.disabled = !body.ready;
    renderBars(byId("emotionList"), (state.labels.emotions || []).map((label) => ({ label, value: 0 })), "label");
    renderBars(byId("auList"), (state.labels.aus || []).map((code) => ({ code, value: 0 })), "code");
    if (!body.ready && body.state !== "error") {
      window.setTimeout(loadStatus, 1500);
    }
  } catch (error) {
    byId("modelState").textContent = "error";
    byId("cameraStatus").textContent = error.message;
  }
}

async function listCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return;
  }
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cameras = devices.filter((device) => device.kind === "videoinput");
  cameraSelect.innerHTML = "";
  for (const [index, camera] of cameras.entries()) {
    const option = document.createElement("option");
    option.value = camera.deviceId;
    option.textContent = camera.label || `Camera ${index + 1}`;
    cameraSelect.appendChild(option);
  }
}

function renderBars(container, items, nameKey) {
  container.innerHTML = "";
  const sorted = [...(items || [])].sort((a, b) => Number(b.value || 0) - Number(a.value || 0));
  for (const item of sorted) {
    const value = Math.max(0, Math.min(1, Number(item.value || 0)));
    const row = document.createElement("div");
    row.className = "metric-row";
    row.innerHTML = `
      <div class="metric-line">
        <span class="metric-name">${item[nameKey] || ""}</span>
        <div class="bar-track"><div class="bar-fill" style="width: ${(value * 100).toFixed(1)}%"></div></div>
        <span class="metric-value">${value.toFixed(2)}</span>
      </div>
    `;
    container.appendChild(row);
  }
}

function captureFrame() {
  const width = video.videoWidth || 640;
  const height = video.videoHeight || 480;
  const targetWidth = 480;
  const scale = Math.min(1, targetWidth / width);
  captureCanvas.width = Math.round(width * scale);
  captureCanvas.height = Math.round(height * scale);
  const context = captureCanvas.getContext("2d");
  if (flipSelect.value === "on") {
    context.translate(captureCanvas.width, 0);
    context.scale(-1, 1);
  }
  context.drawImage(video, 0, 0, captureCanvas.width, captureCanvas.height);
  return captureCanvas.toDataURL("image/jpeg", 0.82);
}

function clearOverlay() {
  const context = overlayCanvas.getContext("2d");
  overlayCanvas.width = overlayCanvas.clientWidth;
  overlayCanvas.height = overlayCanvas.clientHeight;
  context.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

function drawOverlay() {
  clearOverlay();
  const analysis = state.latestAnalysis;
  if (!analysis || !analysis.faces || !analysis.faces.length) {
    return;
  }
  const face = analysis.faces[analysis.primary_face || 0];
  const sourceWidth = captureCanvas.width || 480;
  const sourceHeight = captureCanvas.height || 360;
  const scaleX = overlayCanvas.width / sourceWidth;
  const scaleY = overlayCanvas.height / sourceHeight;
  const context = overlayCanvas.getContext("2d");
  const box = face.box || {};
  const x = Number(box.x || 0) * scaleX;
  const y = Number(box.y || 0) * scaleY;
  const width = Number(box.width || 0) * scaleX;
  const height = Number(box.height || 0) * scaleY;

  if (byId("boxToggle").checked) {
    context.strokeStyle = "#26a269";
    context.lineWidth = 2;
    context.strokeRect(x, y, width, height);
  }
  if (byId("meshToggle").checked) {
    context.fillStyle = "rgba(63, 111, 229, 0.72)";
    for (const point of (face.mesh || []).filter((_, index) => index % 8 === 0)) {
      const px = Number(point.x || 0) * scaleX;
      const py = Number(point.y || 0) * scaleY;
      context.beginPath();
      context.arc(px, py, 2, 0, Math.PI * 2);
      context.fill();
    }
  }
  if (byId("gazeToggle").checked) {
    const gaze = face.gaze || {};
    const originX = x + width / 2;
    const originY = y + height * 0.42;
    const endX = originX + Number(gaze.x || 0) * 60;
    const endY = originY - Number(gaze.y || 0) * 60;
    context.strokeStyle = "#d99b13";
    context.lineWidth = 3;
    context.beginPath();
    context.moveTo(originX, originY);
    context.lineTo(endX, endY);
    context.stroke();
  }
  if (byId("poseToggle").checked) {
    const pose = face.pose || {};
    context.fillStyle = "rgba(16, 20, 22, 0.78)";
    context.fillRect(x, Math.max(0, y - 28), 150, 24);
    context.fillStyle = "#ffffff";
    context.font = "12px system-ui";
    context.fillText(`yaw ${Number(pose.yaw || 0).toFixed(2)}`, x + 8, Math.max(16, y - 11));
  }
}

function drawValenceArousal() {
  const canvas = byId("vaCanvas");
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#dce3ea";
  context.beginPath();
  context.moveTo(width / 2, 10);
  context.lineTo(width / 2, height - 10);
  context.moveTo(10, height / 2);
  context.lineTo(width - 10, height / 2);
  context.stroke();
  for (const [index, point] of state.vaTrail.entries()) {
    const x = width / 2 + Math.max(-1, Math.min(1, point.valence)) * (width / 2 - 20);
    const y = height / 2 - Math.max(-1, Math.min(1, point.arousal)) * (height / 2 - 20);
    context.fillStyle = index === state.vaTrail.length - 1 ? "#208b8f" : "rgba(32, 139, 143, 0.28)";
    context.beginPath();
    context.arc(x, y, index === state.vaTrail.length - 1 ? 6 : 3, 0, Math.PI * 2);
    context.fill();
  }
}

function renderAnalysis(body) {
  const analysis = body.analysis || {};
  state.latestAnalysis = analysis;
  byId("deviceBadge").textContent = body.device || "auto";
  byId("headerFps").textContent = Number(analysis.fps || 0).toFixed(1);
  byId("latencyText").textContent = `${Number(analysis.latency_ms || 0).toFixed(0)} ms`;
  const face = (analysis.faces || [])[analysis.primary_face || 0];
  if (face) {
    renderBars(byId("emotionList"), face.emotions || [], "label");
    renderBars(byId("auList"), face.aus || [], "code");
    const pose = face.pose || {};
    byId("posePitch").textContent = Number(pose.pitch || 0).toFixed(2);
    byId("poseRoll").textContent = Number(pose.roll || 0).toFixed(2);
    byId("poseYaw").textContent = Number(pose.yaw || 0).toFixed(2);
    const gaze = face.gaze || {};
    byId("gazeText").textContent = `${Number(gaze.x || 0).toFixed(2)}, ${Number(gaze.y || 0).toFixed(2)}, ${Number(gaze.z || 1).toFixed(2)}`;
    state.vaTrail.push({ valence: Number(face.valence || 0), arousal: Number(face.arousal || 0) });
    state.vaTrail = state.vaTrail.slice(-24);
    setStatus(`Faces: ${analysis.face_count}`);
  } else {
    setStatus("No face");
  }
  drawValenceArousal();
  drawOverlay();
}

async function analyzeOnce() {
  if (!state.running || state.inFlight || !video.videoWidth) {
    return;
  }
  const now = performance.now();
  const intervalMs = Math.max(180, Number(intervalInput.value || 420));
  if (now - state.lastRequestAt < intervalMs) {
    return;
  }
  state.lastRequestAt = now;
  state.inFlight = true;
  setStatus("Analyzing...");
  try {
    const image = captureFrame();
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || "analysis failed");
    }
    renderAnalysis(body);
  } catch (error) {
    setStatus(error.message);
  } finally {
    state.inFlight = false;
  }
}

function loop() {
  analyzeOnce();
  if (state.running) {
    requestAnimationFrame(loop);
  }
}

function stopStream() {
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
  }
  state.stream = null;
  video.srcObject = null;
  mirror.srcObject = null;
  state.running = false;
  startBtn.disabled = false;
  stopBtn.disabled = true;
  resultFrame.classList.remove("has-stream");
}

async function startCamera() {
  stopStream();
  const selected = parseResolution(resolutionSelect.value);
  const constraints = {
    video: {
      width: { ideal: selected.width },
      height: { ideal: selected.height },
      facingMode: "user",
    },
    audio: false,
  };
  if (cameraSelect.value) {
    constraints.video.deviceId = { ideal: cameraSelect.value };
  }
  state.stream = await navigator.mediaDevices.getUserMedia(constraints);
  video.srcObject = state.stream;
  mirror.srcObject = state.stream;
  await video.play();
  await mirror.play();
  await listCameras();
  document.body.classList.toggle("flip-video", flipSelect.value === "on");
  state.running = true;
  startBtn.disabled = true;
  stopBtn.disabled = false;
  resultFrame.classList.add("has-stream");
  loop();
}

startBtn.addEventListener("click", async () => {
  try {
    await startCamera();
  } catch (error) {
    byId("cameraStatus").textContent = error.message;
  }
});
stopBtn.addEventListener("click", stopStream);
flipSelect.addEventListener("change", () => {
  document.body.classList.toggle("flip-video", flipSelect.value === "on");
});
for (const id of ["boxToggle", "meshToggle", "gazeToggle", "poseToggle"]) {
  byId(id).addEventListener("change", drawOverlay);
}
downloadBtn.addEventListener("click", () => {
  const link = document.createElement("a");
  link.href = captureCanvas.toDataURL("image/jpeg", 0.86);
  link.download = "py-feat-frame.jpg";
  link.click();
});
window.addEventListener("beforeunload", stopStream);
window.addEventListener("resize", drawOverlay);

loadStatus();
listCameras();
drawValenceArousal();
```

- [x] **Step 2: Run existing tests after frontend change**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests -v
```

Expected: PASS.

## Task 5: README and Run Verification

**Files:**
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/README.md`
- Modify: `/Users/hossay/workspace/main/facenet/docs/TODO.md`

- [x] **Step 1: Create README**

Create `README.md` with:

```markdown
# Py-Feat Live Web Demo

This is a local browser webcam demo for `cosanlab/py-feat`. It follows the Flask + static frontend pattern of the OpenFace 3.0 demo in this workspace, but uses Py-Feat `Detectorv2` outputs.

## Setup

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
source .venv/bin/activate
python pyfeat_web_demo.py --host 127.0.0.1 --port 7861 --device auto
```

Open `http://127.0.0.1:7861`.

## Device Options

- `--device auto`: prefer CUDA, then MPS, then CPU.
- `--device cuda`: use CUDA.
- `--device mps`: use Apple Silicon MPS.
- `--device cpu`: use CPU.

## First-Run Behavior

The first `/api/status` call starts Py-Feat model loading. Py-Feat may download model weights into its cache on first use. During this time the Start button remains disabled and the header shows the model state.

## Demo Outputs

The demo displays:

- Face box and FaceMesh overlay.
- Emotion bars.
- Action Unit bars.
- Valence/arousal plot.
- Head pose values.
- Gaze vector values and overlay.
- FPS, latency, device, and face count.

## Test

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests -v
```

The tests use fake analyzer injection and do not require downloading Py-Feat model weights.
```

- [x] **Step 2: Update TODO**

Modify `docs/TODO.md` so implementation progress is visible:

```markdown
# Current Task: Py-Feat Web Demo

- [x] Inspect current workspace and referenced OpenFace web demo.
- [x] Confirm Py-Feat Detectorv2 output shape from official docs.
- [x] Define demo requirements and UI design.
- [x] Write design spec.
- [x] User reviews design spec.
- [x] Create implementation plan after design approval.
- [ ] Implement the Py-Feat web demo.
- [ ] Verify the demo end to end.
```

- [x] **Step 3: Run all tests**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python -m pytest tests -v
```

Expected: PASS.

- [x] **Step 4: Start local server**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
python pyfeat_web_demo.py --host 127.0.0.1 --port 7861 --device auto
```

Expected: Flask starts on `http://127.0.0.1:7861`. If Py-Feat dependencies are not installed, the app should still start and `/api/status` should report `state: error` after model load fails.

- [ ] **Step 5: Browser verification**

Partial verification completed on 2026-07-02:

- Server started on `http://127.0.0.1:7861`.
- `/`, `/styles.css`, `/app.js`, and `/api/status` responded.
- Brave Browser was launched through Playwright with `executablePath`.
- Desktop and mobile layouts rendered without horizontal overflow or JS page errors.
- Real Py-Feat ready/webcam analysis remains blocked in this local environment because `xgboost` cannot load `libomp.dylib`; install OpenMP (for example `brew install libomp`) before final live-model verification.

Open `http://127.0.0.1:7861` and verify:

```text
Header renders Py-Feat Live Demo.
Model status updates from loading to ready or error.
Camera controls are visible.
Start is disabled until ready.
With fake or real ready analyzer, Start opens webcam.
Only one request is in flight at a time.
Emotion, AU, valence/arousal, pose, gaze, and overlay areas render without layout shift.
Stop ends camera tracks.
```

## Self-Review Checklist

- Spec coverage:
  - Live webcam: Task 3 and Task 4.
  - Flask/static structure: Task 2 and Task 3.
  - Lazy Py-Feat Detectorv2: Task 1 and Task 2.
  - Device options: Task 1, Task 2, Task 5.
  - `/api/status` and `/api/analyze`: Task 2.
  - Emotion/AU/VA/Pose/Gaze/Mesh UI: Task 3 and Task 4.
  - Error handling: Task 1 and Task 2.
  - Tests with fake analyzer: Task 1 and Task 2.
  - README: Task 5.
- Placeholder scan:
  - No unresolved placeholder marker text should remain in this plan.
- Type consistency:
  - `AnalyzerState.snapshot()`, `AnalyzerState.start_loading()`, and `AnalyzerState.analyze(frame)` are used consistently by `pyfeat_web_demo.py`.
  - Frontend consumes `analysis.faces`, `analysis.primary_face`, `face.emotions`, `face.aus`, `face.pose`, `face.gaze`, and `face.mesh` exactly as normalized by `pyfeat_analyzer.py`.
