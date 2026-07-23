from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    detector_type: str
    device: str = "auto"
    detection_size: int = 640
    face_model: str | None = None
    facepose_model: str | None = None
    landmark_model: str | None = None
    au_model: str | None = None
    emotion_model: str | None = None
    identity_model: str | None = None
    gaze_model: str | None = None
    max_fps: int = 12
    builtin: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


BUILTIN_PRESETS = [
    Preset(
        id="v2-realtime",
        name="Detectorv2 · realtime",
        detector_type="Detectorv2",
        detection_size=360,
        max_fps=30,
    ),
    Preset(
        id="v2-standard",
        name="Detectorv2 · standard",
        detector_type="Detectorv2",
        detection_size=640,
        max_fps=12,
    ),
    Preset(
        id="v2-fast",
        name="Detectorv2 · fast",
        detector_type="Detectorv2",
        detection_size=360,
        max_fps=18,
    ),
    Preset(
        id="classic-retinaface",
        name="Detectorv1 · retinaface",
        detector_type="Detectorv1",
        detection_size=640,
        face_model="retinaface",
        facepose_model="pose_mlp",
        landmark_model="mobilefacenet",
        au_model="xgb",
        emotion_model="resmasknet",
        gaze_model="l2cs",
        max_fps=8,
    ),
    Preset(
        id="classic-img2pose",
        name="Detectorv1 · img2pose",
        detector_type="Detectorv1",
        detection_size=512,
        face_model="img2pose",
        facepose_model="img2pose",
        landmark_model="mobilefacenet",
        au_model="xgb",
        emotion_model="resmasknet",
        gaze_model="l2cs",
        max_fps=8,
    ),
]
BUILTIN_PRESET_IDS = [preset.id for preset in BUILTIN_PRESETS]


def default_config_dir() -> Path:
    root = os.environ.get("PYFEAT_LIVE_CONFIG_DIR")
    if root:
        return Path(root)
    return Path.home() / ".config" / "pyfeat-live-web"


def default_presets_path() -> Path:
    return default_config_dir() / "presets.json"


def load_presets(path: Path | None = None) -> list[Preset]:
    preset_path = path or default_presets_path()
    if not preset_path.exists():
        return list(BUILTIN_PRESETS)
    try:
        payload = json.loads(preset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(BUILTIN_PRESETS)
    presets = payload if isinstance(payload, list) else payload.get("presets", [])
    loaded = [_preset_from_dict(item) for item in presets if isinstance(item, dict)]
    return loaded or list(BUILTIN_PRESETS)


def save_presets(presets: list[Preset], path: Path | None = None) -> None:
    preset_path = path or default_presets_path()
    preset_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [preset.to_dict() for preset in presets]
    preset_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def merged_presets(path: Path | None = None) -> list[Preset]:
    custom = [preset for preset in load_presets(path) if not preset.builtin]
    by_id = {preset.id: preset for preset in BUILTIN_PRESETS}
    by_id.update({preset.id: preset for preset in custom})
    return list(by_id.values())


def preset_by_id(preset_id: str, path: Path | None = None) -> Preset | None:
    for preset in merged_presets(path):
        if preset.id == preset_id:
            return preset
    return None


def _preset_from_dict(payload: dict) -> Preset:
    allowed = {field.name for field in Preset.__dataclass_fields__.values()}
    values = {key: value for key, value in payload.items() if key in allowed}
    return Preset(**values)
