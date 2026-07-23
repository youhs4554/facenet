import argparse
import os
import threading
import time
from types import SimpleNamespace
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")


def create_app(analyzer: Optional[object] = None) -> FastAPI:
    app = FastAPI(title="Py-Feat.Live Web Demo")
    runtime = SimpleNamespace(
        analyzer=AnalyzerState() if analyzer is None else analyzer,
        analyze_queue=AnalysisQueue(),
        live=None,
    )
    runtime.live = {
        "frame_id": 0,
        "generation": 0,
        "config": {
            "detector_type": "Detectorv2",
            "device": getattr(runtime.analyzer, "device_name", "auto"),
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
    app.state.runtime = runtime

    @app.middleware("http")
    async def no_cache_static_during_local_demo(request: Request, call_next):
        response = await call_next(request)
        if request.url.path in {"/", "/index.html", "/styles.css", "/app.js"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/api/system/health")
    def system_health():
        return {
            "ok": True,
            "time": time.time(),
            "analyzer": _snapshot(runtime.analyzer),
            "live": _public_live_state(runtime.live),
        }

    @app.get("/api/system/compute")
    def system_compute():
        return compute_info()

    @app.get("/api/system/detector-capabilities")
    def system_detector_capabilities():
        return all_capabilities()

    @app.get("/api/system/logs")
    def system_logs():
        return {"logs": runtime.live["logs"][-100:]}

    @app.get("/api/system/overlay-geometry")
    def system_overlay_geometry():
        return overlay_geometry()

    @app.get("/api/presets")
    def presets():
        return {"presets": [preset.to_dict() for preset in merged_presets()]}

    @app.post("/api/presets")
    async def save_preset(request: Request):
        payload = await _json_payload(request)
        if not payload.get("id") or not payload.get("name") or not payload.get("detector_type"):
            return _error("id, name, and detector_type are required", 400)
        preset = _preset_from_payload(payload)
        existing = [item for item in load_presets() if item.id != preset.id and not item.builtin]
        existing.append(preset)
        save_presets(existing)
        return JSONResponse({"preset": preset.to_dict()}, status_code=201)

    @app.delete("/api/presets/{preset_id}")
    def delete_preset(preset_id: str):
        presets_path = default_presets_path()
        custom = [
            preset
            for preset in load_presets(presets_path)
            if preset.id != preset_id and not preset.builtin
        ]
        save_presets(custom, presets_path)
        return {"deleted": preset_id}

    @app.get("/api/status")
    def status(autoload: str = "1"):
        if autoload.lower() not in {"0", "false", "no"}:
            runtime.analyzer.start_loading()
        return _snapshot(runtime.analyzer)

    @app.post("/api/live/configure")
    async def live_configure(request: Request):
        payload = await _json_payload(request)
        live = runtime.live
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
        try:
            if hasattr(runtime.analyzer, "configure"):
                runtime.analyzer.configure(
                    device=device,
                    detector_type=detector_type,
                    face_model=config.get("face_model"),
                    landmark_model=config.get("landmark_model"),
                    au_model=config.get("au_model"),
                    emotion_model=config.get("emotion_model"),
                    identity_model=config.get("identity_model"),
                    gaze_model=config.get("gaze_model"),
                )
            if hasattr(runtime.analyzer, "start_loading"):
                runtime.analyzer.start_loading()
        except Exception as exc:
            _append_log(runtime, str(exc))
            return _error(str(exc), 400)
        live["config"] = config
        live["generation"] += 1
        with live["worker_condition"]:
            live["latest_frame"] = None
        with live["lock"]:
            live["cached_payload"] = None
            live["detection_in_flight"] = False
        return {
            "config": config,
            "generation": live["generation"],
            "capabilities": capabilities_for(detector_type),
            "analyzer": _snapshot(runtime.analyzer),
        }

    @app.post("/api/live/hints")
    async def live_hints(request: Request):
        payload = await _json_payload(request)
        runtime.live["hints"] = payload
        return {"hints": payload}

    @app.post("/api/live/frame")
    async def live_frame(request: Request):
        try:
            frame = await _decode_request_frame(request)
        except ValueError as exc:
            return _error(str(exc), 400)
        _submit_live_frame(runtime, frame)
        return _cached_live_payload(runtime, frame, last_id=request.headers.get("x-last-result-id"))

    @app.post("/api/live/recording/start")
    async def live_recording_start(request: Request):
        live = runtime.live
        if live.get("recording"):
            return {"recording": live["recording"]}
        payload = await _json_payload(request)
        session = create_session(
            {
                "source": "live",
                "config": live["config"],
                "label": payload.get("label", ""),
            }
        )
        live["recording"] = session
        return JSONResponse({"recording": session}, status_code=201)

    @app.post("/api/live/recording/stop")
    def live_recording_stop():
        recording = runtime.live.get("recording")
        runtime.live["recording"] = None
        return {"recording": recording, "stopped": recording is not None}

    @app.get("/api/sessions")
    def sessions_index():
        return {"sessions": list_sessions()}

    @app.get("/api/sessions/{session_id}")
    def sessions_show(session_id: str):
        try:
            return {"session": read_session(session_id)}
        except (FileNotFoundError, ValueError) as exc:
            return _error(str(exc), 404)

    @app.get("/api/sessions/{session_id}/frames")
    def sessions_frames(session_id: str):
        try:
            return {"frames": read_frames(session_id)}
        except (FileNotFoundError, ValueError) as exc:
            return _error(str(exc), 404)

    @app.get("/api/sessions/{session_id}/frame/{frame_index}")
    def sessions_frame(session_id: str, frame_index: int):
        try:
            return {"frame": read_frame(session_id, frame_index)}
        except (FileNotFoundError, ValueError, IndexError) as exc:
            return _error(str(exc), 404)

    @app.get("/api/sessions/{session_id}/video")
    def sessions_video(session_id: str):
        try:
            path = video_path(session_id)
        except (FileNotFoundError, ValueError) as exc:
            return _error(str(exc), 404)
        if not path.exists():
            return _error("video is not available for this session", 404)
        return FileResponse(path, media_type="video/mp4")

    @app.get("/api/sessions/{session_id}/annotations")
    def sessions_annotations(session_id: str):
        try:
            return read_annotations(session_id)
        except (FileNotFoundError, ValueError) as exc:
            return _error(str(exc), 404)

    @app.post("/api/sessions/{session_id}/annotations")
    async def sessions_annotations_save(session_id: str, request: Request):
        payload = await _json_payload(request) or {"annotations": []}
        try:
            return save_annotations(session_id, payload)
        except (FileNotFoundError, ValueError) as exc:
            return _error(str(exc), 404)

    @app.get("/api/analyze/queue")
    def analyze_queue_index():
        return runtime.analyze_queue.snapshot()

    @app.post("/api/analyze/queue")
    async def analyze_queue_add(request: Request):
        payload = await _json_payload(request)
        image = payload.get("image")
        video = payload.get("video")
        if not image and not video:
            return _error("image or video field is required", 400)
        if video:
            item = runtime.analyze_queue.add_video(video, label=payload.get("label", ""))
        else:
            item = runtime.analyze_queue.add_image(image, label=payload.get("label", ""))
        return JSONResponse({"item": item.to_dict()}, status_code=201)

    @app.post("/api/analyze/queue/run")
    def analyze_queue_run():
        queue = runtime.analyze_queue
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
                    if not hasattr(runtime.analyzer, "analyze_video_fex"):
                        raise RuntimeError("Analyzer does not support video analysis")
                    raw = runtime.analyzer.analyze_video_fex(item.video)
                    frame_payloads = _frame_payloads_from_result(
                        raw,
                        frame_size=[0, 0],
                        generation=runtime.live["generation"],
                        source="analyze",
                    )
                else:
                    raw = (
                        runtime.analyzer.analyze_fex(frame)
                        if hasattr(runtime.analyzer, "analyze_fex")
                        else runtime.analyzer.analyze(frame)
                    )
                    height, width = frame.shape[:2]
                    frame_payloads = [
                        {
                            "id": 1,
                            "generation": runtime.live["generation"],
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
                        "config": runtime.live["config"],
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
                _append_log(runtime, str(exc))
            touch(item)
        if queue.state == "running":
            queue.set_state("idle")
        return queue.snapshot()

    @app.post("/api/analyze/queue/pause")
    def analyze_queue_pause():
        runtime.analyze_queue.set_state("paused")
        return runtime.analyze_queue.snapshot()

    @app.post("/api/analyze/queue/stop")
    def analyze_queue_stop():
        queue = runtime.analyze_queue
        queue.set_state("idle")
        for item in queue.items:
            if item.status == "running":
                item.status = "pending"
                item.progress = 0.0
                touch(item)
        return queue.snapshot()

    @app.delete("/api/analyze/queue/{item_id}")
    def analyze_queue_delete(item_id: str):
        removed = runtime.analyze_queue.remove(item_id)
        return {"deleted": removed, "id": item_id}

    @app.post("/api/analyze")
    async def analyze(request: Request):
        payload = await _json_payload(request)
        image = payload.get("image")
        if not image:
            return _error("image field is required", 400)
        try:
            frame = decode_image_data_url(image)
        except ValueError as exc:
            return _error(str(exc), 400)
        try:
            analysis = runtime.analyzer.analyze(frame)
            return {"analysis": analysis, "device": _snapshot(runtime.analyzer).get("device", "")}
        except Exception as exc:
            return _error(str(exc), 500)

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
    return app


async def _json_payload(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _decode_request_frame(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await _json_payload(request)
        image = payload.get("image")
        if not image:
            raise ValueError("image field is required")
        return decode_image_data_url(image)
    raw = await request.body()
    if not raw:
        raise ValueError("JPEG request body is required")
    encoded = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Invalid JPEG request body")
    return frame


def _snapshot(analyzer) -> dict:
    return analyzer.snapshot() if hasattr(analyzer, "snapshot") else {}


def _error(message: str, status_code: int):
    return JSONResponse({"error": message}, status_code=status_code)


def _cached_live_payload(runtime, frame=None, last_id=None):
    live = runtime.live
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
    snapshot = _snapshot(runtime.analyzer)
    return {
        "id": live["frame_id"],
        "generation": live["generation"],
        "frame": [width, height],
        "faces": [],
        "face_count": 0,
        "latency_ms": 0.0,
        "fps": 0.0,
        "device": snapshot.get("device", ""),
        "live_mode": snapshot.get("live_mode", ""),
        "pending": live.get("detection_in_flight", False),
    }


def _build_live_frame_payload(runtime, raw, frame, inference_ms):
    live = runtime.live
    live["frame_id"] += 1
    detector_type = live["config"].get("detector_type", "Detectorv2")
    mp_landmarks = capabilities_for(detector_type)["landmark_space"] == "mp478"
    serialize_started = time.perf_counter()
    faces = serialize_faces(
        raw,
        mp_landmarks=mp_landmarks,
        include_blendshapes=bool(live.get("hints", {}).get("blendshapes")),
    )
    serialize_ms = (time.perf_counter() - serialize_started) * 1000.0
    latency_ms = inference_ms + serialize_ms
    height, width = frame.shape[:2]
    snapshot = _snapshot(runtime.analyzer)
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


def _run_live_detection(runtime, frame):
    live = runtime.live
    generation = live.get("generation", 0)
    started = time.perf_counter()
    try:
        raw = (
            runtime.analyzer.analyze_fex(frame)
            if hasattr(runtime.analyzer, "analyze_fex")
            else runtime.analyzer.analyze(frame)
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        payload = _build_live_frame_payload(runtime, raw, frame, latency_ms)
        with live["lock"]:
            if generation == live.get("generation", 0):
                live["cached_payload"] = payload
        if live.get("recording"):
            append_frame(live["recording"]["id"], payload)
    except Exception as exc:
        _append_log(runtime, str(exc))


def _submit_live_frame(runtime, frame):
    live = runtime.live
    with live["worker_condition"]:
        live["latest_frame"] = frame
        thread = live.get("worker_thread")
        if thread is None or not thread.is_alive():
            thread = threading.Thread(target=_live_worker_loop, args=(runtime,), daemon=True)
            live["worker_thread"] = thread
            thread.start()
        live["worker_condition"].notify()


def _live_worker_loop(runtime):
    live = runtime.live
    while True:
        with live["worker_condition"]:
            while live.get("latest_frame") is None:
                live["worker_condition"].wait()
            frame = live["latest_frame"]
            live["latest_frame"] = None
        with live["lock"]:
            live["detection_in_flight"] = True
        _run_live_detection(runtime, frame)
        with live["lock"]:
            live["detection_in_flight"] = False


def _preset_from_payload(payload):
    allowed = {field.name for field in Preset.__dataclass_fields__.values()}
    values = {key: value for key, value in payload.items() if key in allowed}
    values["builtin"] = False
    return Preset(**values)


def _append_log(runtime, message):
    runtime.live["logs"].append({"time": time.time(), "message": message})


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
    import uvicorn

    args = build_parser().parse_args()
    app = create_app(AnalyzerState(device_name=args.device))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
