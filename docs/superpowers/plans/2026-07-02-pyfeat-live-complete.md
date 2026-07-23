# Py-Feat.Live Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/` into a Py-Feat.Live-inspired local web app with functional Live, Viewer, Analyze, Presets/Settings, session persistence, and browser/API verification.

**Architecture:** Keep the existing Flask/plain-JS app, but split backend behavior into `pyfeat_live_core` modules. Preserve `/api/status` and `/api/analyze` while adding Py-Feat.Live-shaped APIs under `/api/live`, `/api/system`, `/api/presets`, `/api/sessions`, and `/api/analyze/queue`. The frontend becomes a single static SPA with top-level routes rendered by JS state.

**Tech Stack:** Python 3, Flask, Py-Feat, NumPy, OpenCV, pandas, pytest, plain HTML/CSS/JavaScript, Brave/Playwright for rendered QA.

---

## Source References

- Design spec: `/Users/hossay/workspace/main/facenet/docs/superpowers/specs/2026-07-02-pyfeat-live-complete-design.md`
- Current app: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/`
- Official Py-Feat.Live reference clone: `/tmp/pyfeat-live-reference`
- Official docs: `https://py-feat.org/`, `https://py-feat.org/pages/models/`

## Repository Note

`/Users/hossay/workspace/main/facenet` is not a git repository. Do not run commit steps unless a repository is initialized or the user provides a git root. Use `docs/TODO.md` and this plan's checkboxes as progress checkpoints.

## File Structure

Create:

- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/__init__.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/capabilities.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/presets.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/serialization.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/sessions.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/analysis_queue.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_live_core.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_live_api.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_sessions.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_analyze_queue.py`

Modify:

- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_analyzer.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_web_demo.py`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/index.html`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/styles.css`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/app.js`
- `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/README.md`
- `/Users/hossay/workspace/main/facenet/docs/TODO.md`

## Milestone 1: Core Contracts

### Task 1: Capabilities, Presets, And Face Serialization

**Files:**
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/__init__.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/capabilities.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/presets.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/serialization.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_live_core.py`

- [ ] **Step 1: Write failing core tests**

Create `tests/test_pyfeat_live_core.py`:

```python
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
        self.assertEqual(BUILTIN_PRESET_IDS[0], "v2-standard")
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
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
PYTHONDONTWRITEBYTECODE=1 uv run --with pytest --with pandas python -m pytest -p no:cacheprovider tests/test_pyfeat_live_core.py -v
```

Expected: FAIL because `pyfeat_live_core` modules do not exist.

- [ ] **Step 3: Implement `capabilities.py`**

Create `pyfeat_live_core/capabilities.py`:

```python
from __future__ import annotations


def capabilities_for(detector_type: str) -> dict:
    if detector_type == "Detectorv1":
        return {
            "detector_type": "Detectorv1",
            "landmark_space": "dlib68",
            "overlay_kind": "dlib68",
            "has_valence_arousal": False,
            "has_blendshapes": False,
            "has_gaze": True,
            "models": {
                "face_model": ["retinaface", "img2pose"],
                "facepose_model": ["pose_mlp", "pnp_dlt", "img2pose"],
                "landmark_model": ["mobilefacenet", "mobilenet", "pfld"],
                "au_model": ["xgb", "svm", None],
                "emotion_model": ["resmasknet", "svm", None],
                "identity_model": [None, "arcface", "facenet"],
                "gaze_model": ["l2cs", None],
            },
        }
    return {
        "detector_type": "Detectorv2",
        "landmark_space": "mp478",
        "overlay_kind": "mesh478",
        "has_valence_arousal": True,
        "has_blendshapes": True,
        "has_gaze": True,
        "models": {
            "identity_model": [None, "arcface", "facenet"],
        },
    }


def all_capabilities() -> dict:
    return {
        "Detectorv2": capabilities_for("Detectorv2"),
        "Detectorv1": capabilities_for("Detectorv1"),
    }


def compute_info() -> dict:
    info = {
        "cpu": {"available": True, "label": "CPU"},
        "mps": {"available": False, "label": "Apple Metal"},
        "cuda": {"available": False, "label": "CUDA"},
    }
    try:
        import torch

        info["cuda"]["available"] = bool(torch.cuda.is_available())
        info["mps"]["available"] = bool(
            hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        )
    except Exception:
        pass
    return info
```

- [ ] **Step 4: Implement `presets.py`**

Create `pyfeat_live_core/presets.py`:

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


PRESETS_VERSION = 1
BUILTIN_PRESET_IDS = ["v2-standard", "v2-fast", "classic-retinaface", "classic-img2pose"]


@dataclass
class Preset:
    id: str
    name: str
    detector_type: str = "Detectorv2"
    face_model: str = "retinaface"
    landmark_model: str = "mp_facemesh_v2"
    au_model: Optional[str] = "mp_blendshapes"
    emotion_model: Optional[str] = "resmasknet"
    identity_model: Optional[str] = None
    gaze_model: Optional[str] = "l2cs"
    facepose_model: Optional[str] = "pose_mlp"
    builtin: bool = False


def default_presets_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "pyfeat-live" / "presets.json"


def builtin_presets() -> list[Preset]:
    return [
        Preset(id="v2-standard", name="Detectorv2 · standard", builtin=True),
        Preset(id="v2-fast", name="Detectorv2 · fast", identity_model=None, builtin=True),
        Preset(
            id="classic-retinaface",
            name="Detectorv1 · retinaface",
            detector_type="Detectorv1",
            landmark_model="mobilefacenet",
            au_model="xgb",
            identity_model=None,
            builtin=True,
        ),
        Preset(
            id="classic-img2pose",
            name="Detectorv1 · img2pose",
            detector_type="Detectorv1",
            face_model="img2pose",
            facepose_model="img2pose",
            landmark_model="mobilefacenet",
            au_model="xgb",
            identity_model=None,
            builtin=True,
        ),
    ]


def load_presets(path: Path | None = None) -> list[Preset]:
    target = path or default_presets_path()
    if not target.exists():
        return builtin_presets()
    with open(target, encoding="utf-8") as file:
        payload = json.load(file)
    if payload.get("version") != PRESETS_VERSION:
        raise ValueError("Unsupported presets version")
    return [Preset(**item) for item in payload.get("presets", [])]


def save_presets(presets: list[Preset], path: Path | None = None) -> None:
    target = path or default_presets_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": PRESETS_VERSION, "presets": [asdict(preset) for preset in presets]}
    tmp = target.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
    tmp.replace(target)
```

- [ ] **Step 5: Implement `serialization.py`**

Create `pyfeat_live_core/serialization.py`:

```python
from __future__ import annotations

import math
from typing import Any


EMOTION_ALIASES = {
    "anger": ("anger", "Anger"),
    "disgust": ("disgust", "Disgust"),
    "fear": ("fear", "Fear"),
    "happiness": ("happiness", "Happy"),
    "sadness": ("sadness", "Sad"),
    "surprise": ("surprise", "Surprise"),
    "neutral": ("neutral", "Neutral", "_neutral"),
}
BLENDSHAPE_NAMES = [
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight", "eyeBlinkLeft", "eyeBlinkRight",
    "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight",
    "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight",
    "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthFunnel", "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthPressLeft", "mouthPressRight", "mouthPucker", "mouthRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight",
]


def serialize_faces(fex, *, mp_landmarks: bool) -> list[dict[str, Any]]:
    rows = _rows_from_fex(fex)
    return [_serialize_row(row, mp_landmarks=mp_landmarks, fallback_idx=index) for index, row in enumerate(rows)]


def _rows_from_fex(fex):
    if fex is None:
        return []
    if hasattr(fex, "to_pandas"):
        fex = fex.to_pandas()
    if hasattr(fex, "empty") and fex.empty:
        return []
    if hasattr(fex, "iterrows"):
        return [row for _, row in fex.iterrows()]
    if isinstance(fex, list):
        return fex
    if isinstance(fex, dict):
        return [fex]
    return []


def _serialize_row(row, *, mp_landmarks: bool, fallback_idx: int) -> dict[str, Any]:
    rect = [
        _num(row, "FaceRectX"),
        _num(row, "FaceRectY"),
        _num(row, "FaceRectWidth"),
        _num(row, "FaceRectHeight"),
    ]
    lm = _flat_landmarks(row, prefer_mesh=mp_landmarks)
    face = {
        "face_idx": int(_num(row, "face_idx", fallback_idx)),
        "rect": rect,
        "lm": lm,
        "landmark_count": len(lm) // 2,
        "pose": [_num(row, "Pitch"), _num(row, "Roll"), _num(row, "Yaw")],
        "gaze": [
            _num(row, "gaze_0_x", _num(row, "gaze_pitch")),
            _num(row, "gaze_0_y", _num(row, "gaze_yaw")),
            _num(row, "gaze_0_z"),
        ],
        "emotions": _emotions(row),
        "aus": _prefixed_values(row, "AU"),
        "blendshapes": {name: _num(row, name) for name in BLENDSHAPE_NAMES if _has(row, name)},
    }
    if _has(row, "valence") and _has(row, "arousal"):
        face["valence_arousal"] = {"valence": _num(row, "valence"), "arousal": _num(row, "arousal")}
    return face


def _flat_landmarks(row, *, prefer_mesh: bool) -> list[float | None]:
    prefix = "mesh_" if prefer_mesh and _has(row, "mesh_x_0") else ""
    indices = set()
    for key in _keys(row):
        if not isinstance(key, str):
            continue
        if prefix and key.startswith("mesh_x_") and key.rsplit("_", 1)[-1].isdigit():
            indices.add(int(key.rsplit("_", 1)[-1]))
        elif not prefix and key.startswith("x_") and key.rsplit("_", 1)[-1].isdigit():
            indices.add(int(key.rsplit("_", 1)[-1]))
    out = []
    for index in sorted(indices):
        out.append(_num(row, f"{prefix}x_{index}"))
        out.append(_num(row, f"{prefix}y_{index}"))
    return out


def _emotions(row) -> dict[str, float]:
    return {label: _num_from_aliases(row, aliases) for label, aliases in EMOTION_ALIASES.items()}


def _prefixed_values(row, prefix: str) -> dict[str, float]:
    return {key: _num(row, key) for key in _keys(row) if isinstance(key, str) and key.startswith(prefix)}


def _num_from_aliases(row, aliases: tuple[str, ...]) -> float:
    for key in aliases:
        if _has(row, key):
            return _num(row, key)
    return 0.0


def _num(row, key: str, default=0.0):
    try:
        value = row.get(key, default) if hasattr(row, "get") else row[key]
    except (KeyError, TypeError):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _has(row, key: str) -> bool:
    return key in set(_keys(row))


def _keys(row):
    if hasattr(row, "index"):
        return row.index
    if hasattr(row, "keys"):
        return row.keys()
    return []
```

- [ ] **Step 6: Run core tests**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
PYTHONDONTWRITEBYTECODE=1 uv run --with pytest --with pandas python -m pytest -p no:cacheprovider tests/test_pyfeat_live_core.py -v
```

Expected: PASS.

## Milestone 2: System, Presets, And Live APIs

### Task 2: Add Flask Routes For System, Presets, And Live Frame

**Files:**
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_analyzer.py`
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_web_demo.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_live_api.py`

- [ ] **Step 1: Write API tests with fake analyzer**

Create `tests/test_pyfeat_live_api.py`:

```python
import json
import unittest

import cv2
import numpy as np
import pandas as pd

from pyfeat_analyzer import encode_jpeg_data_url
from pyfeat_web_demo import create_app


class LiveFakeAnalyzer:
    device_name = "cpu"

    def __init__(self):
        self.started = False
        self.configured = {}

    def start_loading(self):
        self.started = True

    def snapshot(self):
        return {
            "ready": True,
            "state": "ready",
            "error": "",
            "device": "cpu",
            "labels": {"emotions": ["neutral"], "aus": ["AU12"], "au_descriptions": {"AU12": "Lip Corner Puller"}},
        }

    def configure(self, **kwargs):
        self.configured = kwargs

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
                    "Neutral": 0.8,
                    "AU12": 0.7,
                    "valence": 0.2,
                    "arousal": 0.1,
                }
            ]
        )

    def analyze(self, frame):
        return {"face_count": 1, "faces": [], "primary_face": 0, "fps": 1, "latency_ms": 1}


class PyFeatLiveApiTests(unittest.TestCase):
    def make_client(self):
        app = create_app(LiveFakeAnalyzer())
        app.testing = True
        return app.test_client()

    def test_system_health(self):
        payload = self.make_client().get("/api/system/health").get_json()

        self.assertEqual(payload["ok"], True)
        self.assertIn("version", payload)

    def test_system_detector_capabilities(self):
        payload = self.make_client().get("/api/system/detector-capabilities").get_json()

        self.assertIn("Detectorv2", payload)
        self.assertEqual(payload["Detectorv2"]["landmark_space"], "mp478")

    def test_presets_returns_builtin_presets(self):
        payload = self.make_client().get("/api/presets").get_json()

        self.assertTrue(any(item["id"] == "v2-standard" for item in payload))

    def test_live_configure_updates_analyzer(self):
        response = self.make_client().post(
            "/api/live/configure",
            json={"detector_type": "Detectorv2", "device": "cpu", "identity_model": None},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["detector_type"], "Detectorv2")

    def test_live_frame_accepts_jpeg_body_and_returns_faces(self):
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        data_url = encode_jpeg_data_url(image)
        raw = data_url.split(",", 1)[1]
        encoded = __import__("base64").b64decode(raw)

        response = self.make_client().post(
            "/api/live/frame",
            data=encoded,
            headers={"Content-Type": "image/jpeg", "X-Frame-Id": "9"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["id"], 9)
        self.assertEqual(payload["frame"], [10, 8])
        self.assertEqual(payload["faces"][0]["landmark_count"], 1)
        self.assertEqual(payload["faces"][0]["emotions"]["neutral"], 0.8)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run API tests and confirm failure**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
PYTHONDONTWRITEBYTECODE=1 uv run --with pytest --with numpy --with opencv-python-headless --with pandas --with flask python -m pytest -p no:cacheprovider tests/test_pyfeat_live_api.py -v
```

Expected: FAIL because new routes do not exist.

- [ ] **Step 3: Add `AnalyzerState.configure` and `analyze_fex`**

Modify `pyfeat_analyzer.py`:

```python
    def configure(self, **kwargs):
        requested_device = kwargs.get("device")
        if requested_device:
            with self._lock:
                if requested_device != self.device_name:
                    self.device_name = requested_device
                    self.detector = None
                    self.state = "idle"
                    self.error = ""

    def analyze_fex(self, frame):
        if self.detector is None:
            raise RuntimeError("Analyzer is not ready")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_path = temp_file.name
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise ValueError("Could not encode image")
            with open(temp_path, "wb") as temp_file:
                temp_file.write(encoded.tobytes())
            return self.detector.detect(temp_path, data_type="image")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
```

Then refactor `analyze` to call `analyze_fex(frame)` and normalize the returned result.

- [ ] **Step 4: Add routes to `pyfeat_web_demo.py`**

Import:

```python
import base64
import time

import cv2
import numpy as np

from pyfeat_live_core.capabilities import all_capabilities, compute_info
from pyfeat_live_core.presets import load_presets
from pyfeat_live_core.serialization import serialize_faces
```

Add routes inside `create_app`:

```python
    @app.get("/api/system/health")
    def system_health():
        return jsonify({"ok": True, "version": "local", "app": "py-feat-demo"})

    @app.get("/api/system/compute")
    def system_compute():
        return jsonify(compute_info())

    @app.get("/api/system/detector-capabilities")
    def detector_capabilities():
        return jsonify(all_capabilities())

    @app.get("/api/system/logs")
    def system_logs():
        return jsonify([])

    @app.get("/api/presets")
    def presets():
        return jsonify([preset.__dict__ for preset in load_presets()])

    @app.post("/api/live/configure")
    def live_configure():
        payload = request.get_json(silent=True) or {}
        active = app.config["ANALYZER"]
        if hasattr(active, "configure"):
            active.configure(**payload)
        active.start_loading()
        return jsonify(payload)

    @app.post("/api/live/hints")
    def live_hints():
        return jsonify(request.get_json(silent=True) or {})

    @app.post("/api/live/frame")
    def live_frame():
        active = app.config["ANALYZER"]
        raw = request.get_data()
        if not raw:
            return jsonify({"error": "empty body"}), 400
        encoded = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "could not decode image"}), 400
        started = time.perf_counter()
        try:
            fex = active.analyze_fex(frame)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        faces = serialize_faces(fex, mp_landmarks=True)
        frame_id = int(request.headers.get("X-Frame-Id", "-1"))
        return jsonify({
            "id": frame_id,
            "generation": frame_id,
            "frame": [int(frame.shape[1]), int(frame.shape[0])],
            "faces": faces,
            "latency_ms": elapsed_ms,
        })
```

- [ ] **Step 5: Run API tests**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
PYTHONDONTWRITEBYTECODE=1 uv run --with pytest --with numpy --with opencv-python-headless --with pandas --with flask python -m pytest -p no:cacheprovider tests/test_pyfeat_live_api.py -v
```

Expected: PASS.

## Milestone 3: Session IO And Recording Stubs

### Task 3: Add Session Directory, Frame Persistence, And Annotation IO

**Files:**
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/sessions.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_sessions.py`
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_web_demo.py`

- [ ] **Step 1: Implement tests for session IO**

Create tests that assert:

- `create_session(root, metadata)` creates a timestamped directory.
- `append_frame(session_dir, payload)` writes one JSON line.
- `list_sessions(root)` returns session metadata.
- `save_annotations` and `load_annotations` round-trip markers.

- [ ] **Step 2: Implement `sessions.py`**

Implement functions:

- `default_sessions_root()`
- `create_session(root=None, metadata=None)`
- `append_frame(session_dir, frame_payload)`
- `read_frames(session_dir)`
- `list_sessions(root=None)`
- `save_annotations(session_dir, annotations)`
- `load_annotations(session_dir)`

- [ ] **Step 3: Add session routes**

Add:

- `GET /api/sessions`
- `GET /api/sessions/<session_id>`
- `GET /api/sessions/<session_id>/frames`
- `GET /api/sessions/<session_id>/frame/<int:frame_index>`
- `GET /api/sessions/<session_id>/annotations`
- `POST /api/sessions/<session_id>/annotations`

- [ ] **Step 4: Add recording start/stop routes**

Implement a lightweight recording mode:

- `POST /api/live/recording/start` creates a session and stores its path in app config.
- `POST /api/live/recording/stop` clears active recording and returns session id.
- `/api/live/frame` appends frame JSON to active session when recording is active.

Video writing can be added after session JSON is stable; session JSON is the required first proof.

## Milestone 4: Analyze Queue

### Task 4: Add Local Analyze Queue

**Files:**
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_live_core/analysis_queue.py`
- Create: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/tests/test_pyfeat_analyze_queue.py`
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/pyfeat_web_demo.py`

- [ ] **Step 1: Implement queue tests**

Cover:

- Add image file to queue.
- Patch queued item.
- Delete queued item.
- Run queue with fake analyzer.
- Completed item writes a session.
- Failed item records error.

- [ ] **Step 2: Implement queue model**

Use dataclasses:

- `AnalyzeQueueItem`
- `PipelineConfig`
- `VideoParams`
- `AnalyzeQueue`

Statuses: `queued`, `running`, `done`, `failed`, `cancelled`.

- [ ] **Step 3: Add Analyze routes**

Add:

- `GET /api/analyze/queue`
- `POST /api/analyze/queue`
- `PATCH /api/analyze/queue/<item_id>`
- `DELETE /api/analyze/queue/<item_id>`
- `POST /api/analyze/run`
- `POST /api/analyze/pause`
- `POST /api/analyze/stop`
- `POST /api/analyze/queue/clear-done`

## Milestone 5: Frontend SPA Shell

### Task 5: Rework Static UI Into Live/Viewer/Analyze/Settings

**Files:**
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/index.html`
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/styles.css`
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/static/app.js`

- [ ] **Step 1: Add app shell**

`index.html` should contain:

- Top nav buttons with `data-route`.
- `<section id="liveView">`
- `<section id="viewerView">`
- `<section id="analyzeView">`
- `<section id="settingsView">`

- [ ] **Step 2: Port current camera UI into Live**

Keep existing camera preview and analysis canvas, but move controls into:

- Left sidebar.
- Center stage.
- Bottom control bar.
- Right inspector.

- [ ] **Step 3: Switch Live capture to `/api/live/frame`**

Use JPEG body upload instead of data URL JSON:

```js
async function uploadLiveFrame(blob, frameId) {
  const response = await fetch("/api/live/frame", {
    method: "POST",
    headers: { "Content-Type": "image/jpeg", "X-Frame-Id": String(frameId) },
    body: blob,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || "live frame failed");
  }
  return response.json();
}
```

- [ ] **Step 4: Draw overlays from `faces[].lm`**

The renderer should support:

- Faceboxes.
- Landmark points.
- Landmark lines.
- Mesh points.
- Gaze.
- Emotion bars.
- AU bars.
- Valence/arousal.
- Blendshape summary.

- [ ] **Step 5: Add Viewer UI**

Viewer should:

- Fetch `/api/sessions`.
- Load frames for selected session.
- Scrub frame index.
- Draw selected frame overlays.
- Show frame inspector.
- Save/load annotations.

- [ ] **Step 6: Add Analyze UI**

Analyze should:

- Upload files to `/api/analyze/queue`.
- Show queue list.
- Run/pause/stop queue.
- Open completed session in Viewer.

- [ ] **Step 7: Add Settings UI**

Settings should:

- Show presets from `/api/presets`.
- Show compute info.
- Show session directory note.
- Show macOS dependency note.

## Milestone 6: Documentation And Verification

### Task 6: Full Verification

**Files:**
- Modify: `/Users/hossay/workspace/main/facenet/lib/py-feat-demo/README.md`
- Modify: `/Users/hossay/workspace/main/facenet/docs/TODO.md`

- [ ] **Step 1: Run full unit tests**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
PYTHONDONTWRITEBYTECODE=1 uv run --with pytest --with numpy --with opencv-python-headless --with pandas --with flask python -m pytest -p no:cacheprovider tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Start server with real Py-Feat**

Run:

```bash
cd /Users/hossay/workspace/main/facenet/lib/py-feat-demo
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib PATH=/opt/homebrew/bin:$PATH PYTHONDONTWRITEBYTECODE=1 \
uv run --with py-feat --with flask --with numpy --with opencv-python-headless --with pandas \
python pyfeat_web_demo.py --host 127.0.0.1 --port 7861 --device cpu
```

Expected: server listens at `http://127.0.0.1:7861`.

- [ ] **Step 3: API smoke**

Check:

- `/api/system/health`
- `/api/system/compute`
- `/api/system/detector-capabilities`
- `/api/presets`
- `/api/status`
- `/api/live/configure`
- `/api/live/frame`
- `/api/sessions`
- `/api/analyze/queue`

Expected: JSON responses with no 500s.

- [ ] **Step 4: Real image smoke**

Send a face image to `/api/live/frame`.

Expected:

- `faces.length >= 1`
- `landmark_count == 478` for Detectorv2
- 20 AU keys
- emotion keys include `neutral` and `happiness`

- [ ] **Step 5: Browser QA**

Use Brave Playwright if in-app Browser is unavailable.

Check:

- Desktop 1440x900.
- Mobile 390x844.
- App title and nav render.
- Live, Viewer, Analyze, Settings routes switch.
- No horizontal overflow.
- No console errors.
- Live injected sample response displays overlays and metrics.
- Viewer can load a generated session.
- Analyze queue controls update UI state.

- [ ] **Step 6: README update**

Document:

- Live/Viewer/Analyze workflows.
- macOS `libomp` and FFmpeg dependency notes.
- Run command.
- Test command.
- Current deviations from official Py-Feat.Live.

- [ ] **Step 7: Completion audit**

Audit against:

- Design spec in `docs/superpowers/specs/2026-07-02-pyfeat-live-complete-design.md`.
- This implementation plan.
- Current rendered UI.
- Test output.
- API smoke output.

Only mark the active goal complete if every in-scope item is implemented and verified.
