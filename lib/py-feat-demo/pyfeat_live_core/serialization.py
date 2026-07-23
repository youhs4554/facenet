from __future__ import annotations

import math
import re


EMOTION_ALIASES = {
    "anger": ("anger", "Anger"),
    "disgust": ("disgust", "Disgust"),
    "fear": ("fear", "Fear"),
    "happiness": ("happiness", "Happy"),
    "sadness": ("sadness", "Sad"),
    "surprise": ("surprise", "Surprise"),
    "neutral": ("neutral", "Neutral", "_neutral"),
}
AU_RE = re.compile(r"^AU\d{2}$")
MESH_RE = re.compile(r"^mesh_([xyz])_(\d+)$")
CLASSIC_LANDMARK_RE = re.compile(r"^([xyz])_(\d+)$")


def serialize_faces(result, mp_landmarks: bool = True, include_blendshapes: bool = True) -> list[dict]:
    rows = _rows_from_result(result)
    return [
        _serialize_face(row, index, mp_landmarks, include_blendshapes)
        for index, row in enumerate(rows)
    ]


def _serialize_face(row, face_idx: int, mp_landmarks: bool, include_blendshapes: bool) -> dict:
    lm = _flat_landmarks(row, mesh=mp_landmarks)
    if not lm and mp_landmarks:
        lm = _flat_landmarks(row, mesh=False)
    return {
        "face_idx": face_idx,
        "rect": [
            _number(row, "FaceRectX"),
            _number(row, "FaceRectY"),
            _number(row, "FaceRectWidth"),
            _number(row, "FaceRectHeight"),
        ],
        "score": _number(row, "FaceScore"),
        "lm": lm,
        "landmark_count": len(lm) // 2,
        "pose": [_number(row, "Pitch"), _number(row, "Roll"), _number(row, "Yaw")],
        "gaze": [_number(row, "gaze_0_x"), _number(row, "gaze_0_y"), _number(row, "gaze_0_z")],
        "emotions": _emotions(row),
        "aus": _aus(row),
        "blendshapes": _blendshapes(row) if include_blendshapes else {},
        "valence_arousal": {
            "valence": _number(row, "valence"),
            "arousal": _number(row, "arousal"),
        },
    }


def _flat_landmarks(row, mesh: bool) -> list[float]:
    direct = _direct_flat_landmarks(row, mesh)
    if direct:
        return direct
    pattern = MESH_RE if mesh else CLASSIC_LANDMARK_RE
    keys = list(_keys(row))
    key_set = set(keys)
    indices = set()
    for key in keys:
        if not isinstance(key, str):
            continue
        match = pattern.match(key)
        if match:
            indices.add(int(match.group(2)))
    prefix = "mesh_" if mesh else ""
    points = []
    for index in sorted(indices):
        if f"{prefix}x_{index}" in key_set and f"{prefix}y_{index}" in key_set:
            points.extend([_number(row, f"{prefix}x_{index}"), _number(row, f"{prefix}y_{index}")])
    return points


def _direct_flat_landmarks(row, mesh: bool) -> list[float]:
    prefix = "mesh_" if mesh else ""
    expected = 478 if mesh else 68
    first_x = f"{prefix}x_0"
    first_y = f"{prefix}y_0"
    last_x = f"{prefix}x_{expected - 1}"
    last_y = f"{prefix}y_{expected - 1}"
    key_set = set(_keys(row))
    if first_x not in key_set or first_y not in key_set or last_x not in key_set or last_y not in key_set:
        return []
    points = []
    for index in range(expected):
        x_key = f"{prefix}x_{index}"
        y_key = f"{prefix}y_{index}"
        if x_key not in key_set or y_key not in key_set:
            return []
        points.extend([_number(row, x_key), _number(row, y_key)])
    return points


def _emotions(row) -> dict[str, float]:
    key_set = set(_keys(row))
    return {
        label: _number_from_aliases(row, aliases)
        for label, aliases in EMOTION_ALIASES.items()
        if any(key in key_set for key in aliases)
    }


def _aus(row) -> dict[str, float]:
    return {key: _number(row, key) for key in _keys(row) if isinstance(key, str) and AU_RE.match(key)}


def _blendshapes(row) -> dict[str, float]:
    blocked = set(EMOTION_ALIASES) | {alias for aliases in EMOTION_ALIASES.values() for alias in aliases}
    blocked.update({"FaceRectX", "FaceRectY", "FaceRectWidth", "FaceRectHeight", "FaceScore"})
    blocked.update({"Pitch", "Roll", "Yaw", "valence", "arousal"})
    blocked.update({"gaze_0_x", "gaze_0_y", "gaze_0_z"})
    shapes = {}
    for key in _keys(row):
        if not isinstance(key, str) or key in blocked or AU_RE.match(key):
            continue
        if MESH_RE.match(key) or CLASSIC_LANDMARK_RE.match(key):
            continue
        value = _number(row, key, None)
        if value is not None:
            shapes[key] = value
    return shapes


def _rows_from_result(result) -> list:
    if result is None:
        return []
    if hasattr(result, "to_pandas"):
        result = result.to_pandas()
    if hasattr(result, "empty") and hasattr(result, "iterrows"):
        if result.empty:
            return []
        return [row for _, row in result.iterrows()]
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []


def _keys(row):
    if hasattr(row, "index"):
        return row.index
    if hasattr(row, "keys"):
        return row.keys()
    return []


def _has(row, key: str) -> bool:
    return key in set(_keys(row))


def _number_from_aliases(row, keys, default=0.0) -> float:
    for key in keys:
        value = _number(row, key, None)
        if value is not None:
            return value
    return default


def _number(row, key: str, default=0.0) -> float:
    try:
        value = row[key]
    except (KeyError, TypeError):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number
