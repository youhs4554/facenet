import argparse
import base64
import os
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from live_demo import (
    AU_INFO,
    analyze_frame,
    load_multitask,
    load_retinaface,
    load_star_alignment,
    select_device,
)


ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "web_demo_static")
WEIGHTS_REPO = "nutPace/openface_weights"


def weight_path(filename: str) -> str:
    local_path = os.path.join(ROOT, "weights", filename)
    if os.path.exists(local_path):
        return local_path
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise FileNotFoundError(f"Missing weight file: {local_path}") from exc
    return hf_hub_download(repo_id=WEIGHTS_REPO, filename=filename)


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


@dataclass
class OpenFaceAnalyzer:
    device_name: str = ""
    width: int = 480
    min_confidence: float = 0.7

    def __post_init__(self) -> None:
        self._loaded = False
        self._last_time: Optional[float] = None

    def _load(self) -> None:
        import torch

        if self._loaded:
            return
        mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        self.device_name = select_device(self.device_name, torch.cuda.is_available(), mps_available)
        self.device = torch.device(self.device_name)
        self.multitask_model, self.transform = load_multitask(
            weight_path("stage2_epoch_7_loss_1.1606_acc_0.5589.pth"),
            self.device,
        )
        self.retinaface_model, self.retina_cfg = load_retinaface(
            weight_path("mobilenet0.25_Final.pth"),
            self.device,
        )
        self.alignment = load_star_alignment(weight_path("Landmark_98.pkl"), self.device)
        self._loaded = True

    def analyze(self, frame: np.ndarray) -> tuple[np.ndarray, dict]:
        self._load()
        if self.width and frame.shape[1] > self.width:
            scale = self.width / frame.shape[1]
            frame = cv2.resize(frame, (self.width, int(frame.shape[0] * scale)))

        start = time.perf_counter()
        annotated, analysis = analyze_frame(
            frame,
            self.retinaface_model,
            self.retina_cfg,
            self.alignment,
            self.multitask_model,
            self.transform,
            self.device,
            self.min_confidence,
            include_au_panel=False,
            include_gaze=False,
        )
        elapsed = time.perf_counter() - start
        analysis["fps"] = 1.0 / elapsed if elapsed > 0 else 0.0
        analysis["latency_ms"] = elapsed * 1000.0
        return annotated, analysis


def create_app(analyzer: Optional[object] = None) -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
    app.config["ANALYZER"] = analyzer or OpenFaceAnalyzer()

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/status")
    def status():
        active = app.config["ANALYZER"]
        return jsonify({"aus": AU_INFO, "device": getattr(active, "device_name", ""), "ready": True})

    @app.post("/api/analyze")
    def analyze():
        body = request.get_json(silent=True) or {}
        if "image" not in body:
            return jsonify({"error": "image field is required"}), 400

        try:
            frame = decode_image_data_url(body["image"])
            annotated, analysis = app.config["ANALYZER"].analyze(frame)
            return jsonify(
                {
                    "image": encode_jpeg_data_url(annotated),
                    "analysis": analysis,
                    "device": getattr(app.config["ANALYZER"], "device_name", ""),
                }
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenFace 3.0 browser webcam demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--device", default="", help="cpu, cuda, mps, or empty for auto")
    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    analyzer = OpenFaceAnalyzer(device_name=args.device, width=args.width, min_confidence=args.min_confidence)
    app = create_app(analyzer)
    app.run(host=args.host, port=args.port, threaded=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
