from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def default_sessions_dir() -> Path:
    root = os.environ.get("PYFEAT_LIVE_SESSION_DIR")
    if root:
        return Path(root)
    return Path.home() / "Documents" / "pyfeat-live" / "sessions"


def create_session(metadata: dict | None = None, root: Path | None = None) -> dict:
    sessions_root = root or default_sessions_dir()
    sessions_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    session_dir = sessions_root / session_id
    session_dir.mkdir()
    payload = {
        "id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "live",
        "frame_count": 0,
    }
    payload.update(metadata or {})
    _write_json(session_dir / "metadata.json", payload)
    _write_json(session_dir / "annotations.json", {"annotations": []})
    return payload


def list_sessions(root: Path | None = None) -> list[dict]:
    sessions_root = root or default_sessions_dir()
    if not sessions_root.exists():
        return []
    sessions = []
    for session_dir in sorted(sessions_root.iterdir(), reverse=True):
        if not session_dir.is_dir():
            continue
        try:
            sessions.append(read_session(session_dir.name, root=sessions_root))
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            continue
    return sessions


def read_session(session_id: str, root: Path | None = None) -> dict:
    session_dir = _session_dir(session_id, root)
    metadata = _read_json(session_dir / "metadata.json")
    metadata["id"] = metadata.get("id", session_id)
    metadata["has_video"] = (session_dir / "video.mp4").exists()
    metadata["has_frames"] = (session_dir / "frames.jsonl").exists()
    metadata["annotation_count"] = len(read_annotations(session_id, root=root).get("annotations", []))
    return metadata


def append_frame(session_id: str, frame_payload: dict, root: Path | None = None) -> None:
    session_dir = _session_dir(session_id, root)
    frames_path = session_dir / "frames.jsonl"
    with frames_path.open("a", encoding="utf-8") as frames_file:
        frames_file.write(json.dumps(frame_payload, sort_keys=True) + "\n")
    metadata_path = session_dir / "metadata.json"
    metadata = _read_json(metadata_path)
    metadata["frame_count"] = int(metadata.get("frame_count", 0)) + 1
    metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(metadata_path, metadata)


def read_frames(session_id: str, root: Path | None = None) -> list[dict]:
    frames_path = _session_dir(session_id, root) / "frames.jsonl"
    if not frames_path.exists():
        return []
    frames = []
    for line in frames_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            frames.append(json.loads(line))
    return frames


def read_frame(session_id: str, frame_index: int, root: Path | None = None) -> dict:
    frames = read_frames(session_id, root=root)
    if frame_index < 0 or frame_index >= len(frames):
        raise IndexError("frame index out of range")
    return frames[frame_index]


def read_annotations(session_id: str, root: Path | None = None) -> dict:
    annotations_path = _session_dir(session_id, root) / "annotations.json"
    if not annotations_path.exists():
        return {"annotations": []}
    return _read_json(annotations_path)


def save_annotations(session_id: str, annotations: dict, root: Path | None = None) -> dict:
    payload = annotations if isinstance(annotations, dict) else {"annotations": []}
    if "annotations" not in payload:
        payload = {"annotations": payload}
    _write_json(_session_dir(session_id, root) / "annotations.json", payload)
    return payload


def video_path(session_id: str, root: Path | None = None) -> Path:
    return _session_dir(session_id, root) / "video.mp4"


def _session_dir(session_id: str, root: Path | None = None) -> Path:
    if not SESSION_ID_RE.match(session_id):
        raise ValueError("invalid session id")
    session_dir = (root or default_sessions_dir()) / session_id
    if not session_dir.exists() or not session_dir.is_dir():
        raise FileNotFoundError(session_id)
    return session_dir


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

