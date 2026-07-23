import argparse
import os
import threading
import time
from typing import Optional

from flask import Flask, jsonify, request, send_file, send_from_directory

from pyfeat_analyzer import AnalyzerState, decode_image_data_url
from pyfeat_live_core.analysis_queue import AnalysisQueue, touch
from pyfeat_live_core.capabilities import all_capabilities, capabilities_for, compute_info
from pyfeat_live_core.overlay_geometry import overlay_geometry
from pyfeat_live_core.presets import (
    Preset,
    default_presets_path,
    load_presets,
    merged_presets,
    preset_by_id,
    save_presets,
)
from pyfeat_live_core.serialization import serialize_faces
from pyfeat_live_core.sessions import (
    append_frame,
    create_session,
    list_sessions,
    read_annotations,
    read_frame,
    read_frames,
    read_session,
    save_annotations,
    video_path,
)

import cv2
import numpy as np


ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")


def create_app(analyzer: Optional[object] = None) -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
    app.config["ANALYZER"] = AnalyzerState() if analyzer is None else analyzer
    app.config["ANALYZE_QUEUE"] = AnalysisQueue()
    app.config["LIVE"] = {
        "frame_id": 0,
        "generation": 0,
        "config": {
            "detector_type": "Detectorv2",
            "device": getattr(app.config["ANALYZER"], "device_name", "auto"),
            "preset_id": "v2-standard",
            "detection_size": 640,
        },
        "hints": {},
        "logs": [],
        "recording": None,
        "detection_in_flight": False,
        "latest_frame": None,
        "worker_thread": None,
        "worker_condition": threading.Condition(),
        "cached_payload": None,
        "lock": threading.Lock(),
    }

    @app.after_request
    def no_cache_static_during_local_demo(response):
        if request.path in {"/", "/index.html", "/styles.css", "/app.js"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/system/health")
    def system_health():
        active = app.config["ANALYZER"]
        return jsonify(
            {
                "ok": True,
                "time": time.time(),
                "analyzer": active.snapshot() if hasattr(active, "snapshot") else {},
                "live": _public_live_state(app.config["LIVE"]),
            }
        )

    @app.get("/api/system/compute")
    def system_compute():
        return jsonify(compute_info())

    @app.get("/api/system/detector-capabilities")
    def system_detector_capabilities():
        return jsonify(all_capabilities())

    @app.get("/api/system/logs")
    def system_logs():
        return jsonify({"logs": app.config["LIVE"]["logs"][-100:]})

    @app.get("/api/system/overlay-geometry")
    def system_overlay_geometry():
        return jsonify(overlay_geometry())

    @app.get("/api/presets")
    def presets():
        return jsonify({"presets": [preset.to_dict() for preset in merged_presets()]})

    @app.post("/api/presets")
    def save_preset():
        payload = request.get_json(silent=True) or {}
        if not payload.get("id") or not payload.get("name") or not payload.get("detector_type"):
            return jsonify({"error": "id, name, and detector_type are required"}), 400
        preset = _preset_from_payload(payload)
        existing = [item for item in load_presets() if item.id != preset.id and not item.builtin]
        existing.append(preset)
        save_presets(existing)
        return jsonify({"preset": preset.to_dict()}), 201

    @app.delete("/api/presets/<preset_id>")
    def delete_preset(preset_id):
        presets_path = default_presets_path()
        custom = [
            preset
            for preset in load_presets(presets_path)
            if preset.id != preset_id and not preset.builtin
        ]
        save_presets(custom, presets_path)
        return jsonify({"deleted": preset_id})

    @app.get("/api/status")
    def status():
        active = app.config["ANALYZER"]
        autoload = request.args.get("autoload", "1").lower() not in {"0", "false", "no"}
        if autoload:
            active.start_loading()
        return jsonify(active.snapshot())

    @app.post("/api/live/configure")
    def live_configure():
        payload = request.get_json(silent=True) or {}
        live = app.config["LIVE"]
        config = dict(live["config"])
        preset = preset_by_id(payload.get("preset_id", config.get("preset_id", "v2-standard")))
        if preset:
            config.update(
                {
                    key: value
                    for key, value in preset.to_dict().items()
                    if key not in {"id", "name", "builtin"} and value is not None
                }
            )
            config["preset_id"] = preset.id
        config.update({key: value for key, value in payload.items() if value is not None})
        detector_type = config.get("detector_type", "Detectorv2")
        device = config.get("device", "auto")
        active = app.config["ANALYZER"]
        try:
            if hasattr(active, "configure"):
                active.configure(
                    device=device,
                    detector_type=detector_type,
                    face_model=config.get("face_model"),
                    landmark_model=config.get("landmark_model"),
                    au_model=config.get("au_model"),
                    emotion_model=config.get("emotion_model"),
                    identity_model=config.get("identity_model"),
                    gaze_model=config.get("gaze_model"),
                )
            if hasattr(active, "start_loading"):
                active.start_loading()
        except Exception as exc:
            _append_log(app, str(exc))
            return jsonify({"error": str(exc)}), 400
        live["config"] = config
        live["generation"] += 1
        with live["worker_condition"]:
            live["latest_frame"] = None
        with live["lock"]:
            live["cached_payload"] = None
            live["detection_in_flight"] = False
        return jsonify(
            {
                "config": config,
                "generation": live["generation"],
                "capabilities": capabilities_for(detector_type),
                "analyzer": active.snapshot() if hasattr(active, "snapshot") else {},
            }
        )

    @app.post("/api/live/hints")
    def live_hints():
        payload = request.get_json(silent=True) or {}
        app.config["LIVE"]["hints"] = payload
        return jsonify({"hints": payload})

    @app.post("/api/live/frame")
    def live_frame():
        active = app.config["ANALYZER"]
        live = app.config["LIVE"]
        try:
            frame = _decode_request_frame()
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not app.testing:
            _submit_live_frame(app, frame)
            return jsonify(_cached_live_payload(app, frame, last_id=request.headers.get("x-last-result-id")))

        started = time.perf_counter()
        try:
            raw = active.analyze_fex(frame) if hasattr(active, "analyze_fex") else active.analyze(frame)
        except Exception as exc:
            _append_log(app, str(exc))
            return jsonify({"error": str(exc)}), 503

        latency_ms = (time.perf_counter() - started) * 1000.0
        frame_payload = _build_live_frame_payload(app, raw, frame, latency_ms)
        if live.get("recording"):
            append_frame(live["recording"]["id"], frame_payload)
        return jsonify(frame_payload)

    @app.post("/api/live/recording/start")
    def live_recording_start():
        live = app.config["LIVE"]
        if live.get("recording"):
            return jsonify({"recording": live["recording"]})
        payload = request.get_json(silent=True) or {}
        metadata = {
            "source": "live",
            "config": live["config"],
            "label": payload.get("label", ""),
        }
        session = create_session(metadata)
        live["recording"] = session
        return jsonify({"recording": session}), 201

    @app.post("/api/live/recording/stop")
    def live_recording_stop():
        live = app.config["LIVE"]
        recording = live.get("recording")
        live["recording"] = None
        return jsonify({"recording": recording, "stopped": recording is not None})

    @app.get("/api/sessions")
    def sessions_index():
        return jsonify({"sessions": list_sessions()})

    @app.get("/api/sessions/<session_id>")
    def sessions_show(session_id):
        try:
            return jsonify({"session": read_session(session_id)})
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/sessions/<session_id>/frames")
    def sessions_frames(session_id):
        try:
            return jsonify({"frames": read_frames(session_id)})
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/sessions/<session_id>/frame/<int:frame_index>")
    def sessions_frame(session_id, frame_index):
        try:
            return jsonify({"frame": read_frame(session_id, frame_index)})
        except IndexError as exc:
            return jsonify({"error": str(exc)}), 404
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/sessions/<session_id>/video")
    def sessions_video(session_id):
        try:
            path = video_path(session_id)
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404
        if not path.exists():
            return jsonify({"error": "video is not available for this session"}), 404
        return send_file(path, mimetype="video/mp4")

    @app.get("/api/sessions/<session_id>/annotations")
    def sessions_annotations(session_id):
        try:
            return jsonify(read_annotations(session_id))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/sessions/<session_id>/annotations")
    def sessions_annotations_save(session_id):
        payload = request.get_json(silent=True) or {"annotations": []}
        try:
            return jsonify(save_annotations(session_id, payload))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/analyze/queue")
    def analyze_queue_index():
        return jsonify(app.config["ANALYZE_QUEUE"].snapshot())

    @app.post("/api/analyze/queue")
    def analyze_queue_add():
        payload = request.get_json(silent=True) or {}
        image = payload.get("image")
        video = payload.get("video")
        if not image and not video:
            return jsonify({"error": "image or video field is required"}), 400
        queue = app.config["ANALYZE_QUEUE"]
        if video:
            item = queue.add_video(video, label=payload.get("label", ""))
        else:
            item = queue.add_image(image, label=payload.get("label", ""))
        return jsonify({"item": item.to_dict()}), 201

    @app.post("/api/analyze/queue/run")
    def analyze_queue_run():
        queue = app.config["ANALYZE_QUEUE"]
        active = app.config["ANALYZER"]
        queue.set_state("running")
        for item in queue.pending_items():
            if queue.state != "running":
                break
            item.status = "running"
            item.progress = 0.1
            touch(item)
            try:
                frame = decode_image_data_url(item.image) if item.kind == "image" else None
                if item.kind == "video":
                    if not hasattr(active, "analyze_video_fex"):
                        raise RuntimeError("Analyzer does not support video analysis")
                    raw = active.analyze_video_fex(item.video)
                    frame_payloads = _frame_payloads_from_result(
                        raw,
                        frame_size=[0, 0],
                        generation=app.config["LIVE"]["generation"],
                        source="analyze",
                    )
                else:
                    raw = active.analyze_fex(frame) if hasattr(active, "analyze_fex") else active.analyze(frame)
                    height, width = frame.shape[:2]
                    frame_payloads = [
                        {
                            "id": 1,
                            "generation": app.config["LIVE"]["generation"],
                            "frame": [width, height],
                            "faces": serialize_faces(raw, mp_landmarks=True),
                            "source": "analyze",
                        }
                    ]
                session = create_session(
                    {
                        "source": "analyze",
                        "label": item.label,
                        "queue_item_id": item.id,
                        "input_kind": item.kind,
                        "config": app.config["LIVE"]["config"],
                    }
                )
                for index, frame_payload in enumerate(frame_payloads, start=1):
                    frame_payload["id"] = frame_payload.get("id") or index
                    frame_payload["face_count"] = len(frame_payload.get("faces", []))
                    append_frame(session["id"], frame_payload)
                item.session_id = session["id"]
                item.status = "completed"
                item.progress = 1.0
                item.error = ""
            except Exception as exc:
                item.status = "error"
                item.error = str(exc)
                item.progress = 0.0
                _append_log(app, str(exc))
            touch(item)
        if queue.state == "running":
            queue.set_state("idle")
        return jsonify(queue.snapshot())

    @app.post("/api/analyze/queue/pause")
    def analyze_queue_pause():
        app.config["ANALYZE_QUEUE"].set_state("paused")
        return jsonify(app.config["ANALYZE_QUEUE"].snapshot())

    @app.post("/api/analyze/queue/stop")
    def analyze_queue_stop():
        queue = app.config["ANALYZE_QUEUE"]
        queue.set_state("idle")
        for item in queue.items:
            if item.status == "running":
                item.status = "pending"
                item.progress = 0.0
                touch(item)
        return jsonify(queue.snapshot())

    @app.delete("/api/analyze/queue/<item_id>")
    def analyze_queue_delete(item_id):
        removed = app.config["ANALYZE_QUEUE"].remove(item_id)
        return jsonify({"deleted": removed, "id": item_id})

    @app.post("/api/analyze")
    def analyze():
        active = app.config["ANALYZER"]
        payload = request.get_json(silent=True) or {}
        image = payload.get("image")
        if not image:
            return jsonify({"error": "image field is required"}), 400

        try:
            frame = decode_image_data_url(image)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            analysis = active.analyze(frame)
            device = active.snapshot().get("device", "")
            return jsonify({"analysis": analysis, "device": device})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app


def _decode_request_frame():
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        image = payload.get("image")
        if not image:
            raise ValueError("image field is required")
        return decode_image_data_url(image)

    raw = request.get_data()
    if not raw:
        raise ValueError("JPEG request body is required")
    encoded = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Invalid JPEG request body")
    return frame


def _cached_live_payload(app, frame=None, last_id=None):
    live = app.config["LIVE"]
    cached = live.get("cached_payload")
    if cached:
        if last_id and str(cached.get("id")) == str(last_id):
            return {
                "id": cached.get("id"),
                "generation": cached.get("generation"),
                "frame": cached.get("frame"),
                "face_count": cached.get("face_count", 0),
                "latency_ms": cached.get("latency_ms", 0.0),
                "inference_ms": cached.get("inference_ms", 0.0),
                "serialize_ms": cached.get("serialize_ms", 0.0),
                "fps": cached.get("fps", 0.0),
                "device": cached.get("device", ""),
                "live_mode": cached.get("live_mode", ""),
                "pending": live.get("detection_in_flight", False),
                "unchanged": True,
            }
        payload = dict(cached)
        payload["pending"] = live.get("detection_in_flight", False)
        return payload
    height, width = frame.shape[:2] if frame is not None else (480, 640)
    active = app.config["ANALYZER"]
    return {
        "id": live["frame_id"],
        "generation": live["generation"],
        "frame": [width, height],
        "faces": [],
        "face_count": 0,
        "latency_ms": 0.0,
        "fps": 0.0,
        "device": active.snapshot().get("device", "") if hasattr(active, "snapshot") else "",
        "live_mode": active.snapshot().get("live_mode", "") if hasattr(active, "snapshot") else "",
        "pending": live.get("detection_in_flight", False),
    }


def _build_live_frame_payload(app, raw, frame, inference_ms):
    live = app.config["LIVE"]
    active = app.config["ANALYZER"]
    live["frame_id"] += 1
    detector_type = live["config"].get("detector_type", "Detectorv2")
    mp_landmarks = capabilities_for(detector_type)["landmark_space"] == "mp478"
    serialize_started = time.perf_counter()
    faces = serialize_faces(
        raw,
        mp_landmarks=mp_landmarks,
        include_blendshapes=bool(live.get("hints", {}).get("blendshapes", True)),
    )
    serialize_ms = (time.perf_counter() - serialize_started) * 1000.0
    latency_ms = inference_ms + serialize_ms
    height, width = frame.shape[:2]
    snapshot = active.snapshot() if hasattr(active, "snapshot") else {}
    return {
        "id": live["frame_id"],
        "generation": live["generation"],
        "frame": [width, height],
        "faces": faces,
        "face_count": len(faces),
        "latency_ms": latency_ms,
        "serialize_ms": serialize_ms,
        "inference_ms": inference_ms,
        "fps": 1000.0 / latency_ms if latency_ms > 0 else 0.0,
        "device": snapshot.get("device", ""),
        "live_mode": snapshot.get("live_mode", ""),
        "pending": False,
    }


def _run_live_detection(app, frame):
    active = app.config["ANALYZER"]
    live = app.config["LIVE"]
    generation = live.get("generation", 0)
    started = time.perf_counter()
    try:
        raw = active.analyze_fex(frame) if hasattr(active, "analyze_fex") else active.analyze(frame)
        latency_ms = (time.perf_counter() - started) * 1000.0
        payload = _build_live_frame_payload(app, raw, frame, latency_ms)
        with live["lock"]:
            if generation == live.get("generation", 0):
                live["cached_payload"] = payload
        if live.get("recording"):
            append_frame(live["recording"]["id"], payload)
    except Exception as exc:
        _append_log(app, str(exc))


def _submit_live_frame(app, frame):
    live = app.config["LIVE"]
    with live["worker_condition"]:
        live["latest_frame"] = frame
        thread = live.get("worker_thread")
        if thread is None or not thread.is_alive():
            thread = threading.Thread(target=_live_worker_loop, args=(app,), daemon=True)
            live["worker_thread"] = thread
            thread.start()
        live["worker_condition"].notify()


def _live_worker_loop(app):
    live = app.config["LIVE"]
    while True:
        with live["worker_condition"]:
            while live.get("latest_frame") is None:
                live["worker_condition"].wait()
            frame = live["latest_frame"]
            live["latest_frame"] = None
        with live["lock"]:
            live["detection_in_flight"] = True
        _run_live_detection(app, frame)
        with live["lock"]:
            live["detection_in_flight"] = False


def _preset_from_payload(payload):
    allowed = {field.name for field in Preset.__dataclass_fields__.values()}
    values = {key: value for key, value in payload.items() if key in allowed}
    values["builtin"] = False
    return Preset(**values)


def _append_log(app, message):
    app.config["LIVE"]["logs"].append({"time": time.time(), "message": message})


def _public_live_state(live):
    hidden = {"lock", "worker_condition", "worker_thread", "latest_frame"}
    return {key: value for key, value in live.items() if key not in hidden}


def _frame_payloads_from_result(result, frame_size, generation, source):
    frame = result.to_pandas() if hasattr(result, "to_pandas") else result
    if hasattr(frame, "empty") and hasattr(frame, "groupby"):
        if frame.empty:
            return [{"generation": generation, "frame": frame_size, "faces": [], "source": source}]
        frame_column = _frame_column(frame)
        if frame_column:
            payloads = []
            for frame_id, group in frame.groupby(frame_column, sort=True):
                payloads.append(
                    {
                        "id": int(frame_id) + 1 if str(frame_id).isdigit() else len(payloads) + 1,
                        "generation": generation,
                        "frame": frame_size,
                        "faces": serialize_faces(group, mp_landmarks=True),
                        "source": source,
                    }
                )
            return payloads
    return [{"generation": generation, "frame": frame_size, "faces": serialize_faces(frame, mp_landmarks=True), "source": source}]


def _frame_column(frame):
    for column in ("frame", "Frame", "frame_id", "FrameID"):
        if column in frame.columns:
            return column
    return None


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--device", default="auto")
    return parser


def main():
    args = build_parser().parse_args()
    app = create_app(AnalyzerState(device_name=args.device))
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
