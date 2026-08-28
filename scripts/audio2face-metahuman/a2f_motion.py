#!/usr/bin/env python3
"""Validated, reproducible Audio2Face blendshape and emotion artifacts.

The canonical names mirror the NVIDIA Audio2Face-3D NIM 2.0 CSV output.
This module deliberately keeps artifact post-processing separate from the
model/runtime configuration so raw inference is always preserved.
"""

from __future__ import annotations

import copy
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


BLENDSHAPE_NAMES = (
    "EyeBlinkLeft", "EyeLookDownLeft", "EyeLookInLeft", "EyeLookOutLeft",
    "EyeLookUpLeft", "EyeSquintLeft", "EyeWideLeft", "EyeBlinkRight",
    "EyeLookDownRight", "EyeLookInRight", "EyeLookOutRight", "EyeLookUpRight",
    "EyeSquintRight", "EyeWideRight", "JawForward", "JawLeft", "JawRight",
    "JawOpen", "MouthClose", "MouthFunnel", "MouthPucker", "MouthLeft",
    "MouthRight", "MouthSmileLeft", "MouthSmileRight", "MouthFrownLeft",
    "MouthFrownRight", "MouthDimpleLeft", "MouthDimpleRight",
    "MouthStretchLeft", "MouthStretchRight", "MouthRollLower",
    "MouthRollUpper", "MouthShrugLower", "MouthShrugUpper", "MouthPressLeft",
    "MouthPressRight", "MouthLowerDownLeft", "MouthLowerDownRight",
    "MouthUpperUpLeft", "MouthUpperUpRight", "BrowDownLeft", "BrowDownRight",
    "BrowInnerUp", "BrowOuterUpLeft", "BrowOuterUpRight", "CheekPuff",
    "CheekSquintLeft", "CheekSquintRight", "NoseSneerLeft", "NoseSneerRight",
    "TongueOut", "TongueTipUp", "TongueTipDown", "TongueTipLeft",
    "TongueTipRight", "TongueRollUp", "TongueRollDown", "TongueRollLeft",
    "TongueRollRight", "TongueUp", "TongueDown", "TongueLeft", "TongueRight",
    "TongueIn", "TongueStretch", "TongueWide", "TongueNarrow",
)

EMOTION_NAMES = (
    "disgust", "joy", "grief", "outofbreath", "pain", "amazement",
    "anger", "cheekiness", "sadness", "fear",
)

REGIONS = {
    "eyes": tuple(name for name in BLENDSHAPE_NAMES if name.startswith("Eye")),
    "jaw": tuple(name for name in BLENDSHAPE_NAMES if name.startswith("Jaw")),
    "mouth": tuple(name for name in BLENDSHAPE_NAMES if name.startswith("Mouth")),
    "brows": tuple(name for name in BLENDSHAPE_NAMES if name.startswith("Brow")),
    "cheeks": tuple(
        name for name in BLENDSHAPE_NAMES
        if name.startswith("Cheek") or name.startswith("Nose")
    ),
    "tongue": tuple(name for name in BLENDSHAPE_NAMES if name.startswith("Tongue")),
}

# Exact runtime parameter names consumed by installed NVIDIA ACE 2.5
# (Audio2FaceParameters.h + AIMA2FContext.cpp). Deployment-time snake_case
# names are intentionally not accepted by this runtime config contract.
FACE_PARAMETER_SPECS = {
    "skinStrength": (0.0, 2.0),
    "upperFaceStrength": (0.0, 2.0),
    "lowerFaceStrength": (0.0, 2.0),
    "eyelidOpenOffset": (-1.0, 1.0),
    "blinkStrength": (0.0, 2.0),
    "lipOpenOffset": (-0.2, 0.2),
    "upperFaceSmoothing": (0.0, 0.1),
    "lowerFaceSmoothing": (0.0, 0.1),
    "faceMaskLevel": (0.0, 1.0),
    "faceMaskSoftness": (0.001, 0.5),
    "tongueStrength": (0.0, 3.0),
    "tongueHeightOffset": (-3.0, 3.0),
    "tongueDepthOffset": (-3.0, 3.0),
    "inputStrength": (0.0, 3.0),
    "blinkOffset": (-1.0, 1.0),
}
FACE_PARAMETER_NAMES = set(FACE_PARAMETER_SPECS)

# ACE 2.5's Apply ACE Face Animations node officially publishes the ARKit-style
# face curves plus TongueOut. The installed NVIDIA A2F MetaHuman pose asset also
# contains the remaining 15 tongue solver poses, but those are an explicit
# run-owned bake capability rather than an ACE source-stream contract.
ACE25_SOURCE_CURVE_NAMES = BLENDSHAPE_NAMES[:52]
ACE25_RENDER_CURVE_NAMES = ACE25_SOURCE_CURVE_NAMES  # compatibility alias
A2F_POSE_ASSET_EXTENDED_CURVE_NAMES = BLENDSHAPE_NAMES


def final_render_curve_names(config: dict[str, Any]) -> tuple[str, ...]:
    if config.get("final_render_profile", "ace-source") == "pose-asset-extended":
        return A2F_POSE_ASSET_EXTENDED_CURVE_NAMES
    return ACE25_SOURCE_CURVE_NAMES


class MotionDataError(ValueError):
    """Raised when an inference artifact violates the stable data contract."""


class MotionConfigError(ValueError):
    """Raised when a versioned motion configuration is invalid."""


def _finite(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise MotionDataError(f"{label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise MotionDataError(f"{label} must be finite")
    return parsed


def _parse_series_csv(
    path: Path,
    names: tuple[str, ...],
    prefix: str,
    time_headers: tuple[str, ...],
    kind: str,
    source: str,
    timebase_hz: float | None = None,
) -> dict[str, Any]:
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
    except OSError as exc:
        raise MotionDataError(f"cannot read {path}: {exc}") from exc
    if not rows:
        raise MotionDataError(f"empty {kind} CSV: {path}")

    header = rows[0]
    time_candidates = [index for index, value in enumerate(header) if value in time_headers]
    if len(time_candidates) != 1:
        raise MotionDataError(f"{kind} CSV requires one time column")
    time_index = time_candidates[0]
    expected = {f"{prefix}{name}" for name in names}
    actual = {value for value in header if value.startswith(prefix)}
    if actual != expected or len(actual) != len(names):
        raise MotionDataError(
            f"{kind} schema mismatch: expected {len(names)} canonical columns, got {len(actual)}"
        )
    indexes = [header.index(f"{prefix}{name}") for name in names]
    frames: list[dict[str, Any]] = []
    previous = -math.inf
    for fallback_index, row in enumerate(rows[1:]):
        if not row or all(not cell.strip() for cell in row):
            continue
        if max([time_index, *indexes]) >= len(row):
            raise MotionDataError(f"short row {fallback_index + 2} in {path}")
        timestamp = _finite(row[time_index], f"time row {fallback_index}")
        if timebase_hz is not None:
            if not math.isfinite(timebase_hz) or timebase_hz <= 0:
                raise MotionDataError("timebase_hz must be positive and finite")
            timestamp /= timebase_hz
        if timestamp <= previous:
            raise MotionDataError("timestamps must be strictly increasing")
        previous = timestamp
        frame_index = fallback_index
        if header and header[0] == "" and row[0] != "":
            try:
                frame_index = int(row[0])
            except ValueError as exc:
                raise MotionDataError(f"invalid frame index at row {fallback_index + 2}") from exc
        values = [_finite(row[index], f"{name} row {fallback_index}") for name, index in zip(names, indexes)]
        frames.append(
            {"frame_index": frame_index, "time_seconds": timestamp, "values": values}
        )
    if not frames:
        raise MotionDataError(f"no frames in {path}")
    key = "curve_names" if kind == "blendshape" else "emotion_names"
    result = {
        "schema_version": 1,
        "kind": kind,
        key: list(names),
        "source": source,
        "frames": frames,
    }
    if timebase_hz is not None:
        result["source_timebase_hz"] = float(timebase_hz)
    return result


def parse_animation_csv(path: Path, source_name: str = "nvidia-a2f-raw") -> dict[str, Any]:
    return _parse_series_csv(
        path, BLENDSHAPE_NAMES, "blendShapes.", ("timeCode", "time_seconds"),
        "blendshape", source_name,
    )


def parse_emotion_csv(
    path: Path,
    source_name: str = "nvidia-a2e",
    timebase_hz: float | None = None,
) -> dict[str, Any]:
    return _parse_series_csv(
        path, EMOTION_NAMES, "emotion_values.", ("time_code", "timeCode", "time_seconds"),
        "emotion", source_name, timebase_hz,
    )


def synthetic_motion_series(frame_count: int = 3, fps: float = 30.0) -> dict[str, Any]:
    if frame_count < 1 or not math.isfinite(fps) or fps <= 0:
        raise MotionDataError("frame_count and fps must be positive")
    return {
        "schema_version": 1,
        "kind": "blendshape",
        "curve_names": list(BLENDSHAPE_NAMES),
        "source": "synthetic-test-fixture",
        "frames": [
            {"frame_index": index, "time_seconds": index / fps, "values": [0.0] * 68}
            for index in range(frame_count)
        ],
    }


def synthetic_emotion_series(frame_count: int = 3, fps: float = 30.0) -> dict[str, Any]:
    if frame_count < 1 or not math.isfinite(fps) or fps <= 0:
        raise MotionDataError("frame_count and fps must be positive")
    return {
        "schema_version": 1,
        "kind": "emotion",
        "emotion_names": list(EMOTION_NAMES),
        "source": "synthetic-test-fixture",
        "frames": [
            {"frame_index": index, "time_seconds": index / fps, "values": [0.0] * 10}
            for index in range(frame_count)
        ],
    }


def resample_series(
    series: dict[str, Any], *, fps: float, frame_count: int
) -> dict[str, Any]:
    """Linearly resample a timecoded series without changing the source artifact."""
    if frame_count < 1 or not math.isfinite(fps) or fps <= 0:
        raise MotionDataError("frame_count and fps must be positive")
    source_frames = series.get("frames")
    if not isinstance(source_frames, list) or not source_frames:
        raise MotionDataError("series has no frames")
    times = [float(frame["time_seconds"]) for frame in source_frames]
    if any(
        not math.isfinite(value) or value < 0.0
        for value in times
    ) or any(right <= left for left, right in zip(times, times[1:])):
        raise MotionDataError("source timecodes must be finite and strictly increasing")
    channel_count = len(source_frames[0]["values"])
    output_frames = []
    for frame_index in range(frame_count):
        target = frame_index / fps
        right_index = bisect.bisect_left(times, target)
        if right_index <= 0:
            left_index = right_index = 0
            alpha = 0.0
            values = [float(value) for value in source_frames[0]["values"]]
        elif right_index >= len(times):
            left_index = right_index = len(times) - 1
            alpha = 0.0
            values = [float(value) for value in source_frames[-1]["values"]]
        elif times[right_index] == target:
            left_index = right_index
            alpha = 0.0
            values = [float(value) for value in source_frames[right_index]["values"]]
        else:
            left_index = right_index - 1
            left_time, right_time = times[left_index], times[right_index]
            alpha = (target - left_time) / (right_time - left_time)
            left_values = source_frames[left_index]["values"]
            right_values = source_frames[right_index]["values"]
            if len(left_values) != channel_count or len(right_values) != channel_count:
                raise MotionDataError("source channel count changes between frames")
            values = [
                float(left) + alpha * (float(right) - float(left))
                for left, right in zip(left_values, right_values)
            ]
        if len(values) != channel_count or not all(math.isfinite(value) for value in values):
            raise MotionDataError("resampled values are invalid")
        output_frames.append(
            {
                "frame_index": frame_index,
                "time_seconds": target,
                "values": values,
                "source_mapping": {
                    "target_time_seconds": target,
                    "left_frame_index": int(
                        source_frames[left_index].get("frame_index", left_index)
                    ),
                    "right_frame_index": int(
                        source_frames[right_index].get("frame_index", right_index)
                    ),
                    "left_time_seconds": float(times[left_index]),
                    "right_time_seconds": float(times[right_index]),
                    "interpolation_alpha": float(alpha),
                },
            }
        )
    result = copy.deepcopy(series)
    result["source"] = f"{series.get('source', 'unknown')}|resampled"
    result["frames"] = output_frames
    result["resampling"] = {
        "method": "linear-timecode",
        "source_frames": len(source_frames),
        "target_frames": frame_count,
        "target_fps": float(fps),
    }
    return result


def _config_number(value: Any, label: str, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise MotionConfigError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise MotionConfigError(f"{label} must be finite")
    if minimum is not None and parsed < minimum:
        raise MotionConfigError(f"{label} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise MotionConfigError(f"{label} must be <= {maximum}")
    return parsed


def resolve_motion_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "baseline",
        "curve_application": "artifact_only",
        "final_render_profile": "ace-source",
        "face_parameters": {},
        "nvidia_runtime_curve_parameters": {
            "enable_clamping": False,
            "multipliers": {},
            "offsets": {},
        },
        "emotion": {"overall_strength": None, "constant": {}, "timecoded": []},
        "artifact_postprocess": {
            "global_intensity": 1.0,
            "attack": 1.0,
            "release": 1.0,
            "region_gains": {},
            "curve_operations": {},
        },
    }


def validate_motion_config(document: dict[str, Any], audio_duration: float | None = None) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise MotionConfigError("configuration must be a JSON object")
    allowed = {
        "schema_version", "mode", "curve_application", "final_render_profile", "face_parameters",
        "nvidia_runtime_curve_parameters",
        "emotion", "artifact_postprocess",
    }
    unknown = set(document) - allowed
    if unknown:
        raise MotionConfigError(f"unknown configuration keys: {sorted(unknown)}")
    if document.get("schema_version") != 1:
        raise MotionConfigError("schema_version must be 1")
    mode = document.get("mode")
    if mode not in {"baseline", "enhanced"}:
        raise MotionConfigError("mode must be baseline or enhanced")
    result = resolve_motion_config()
    result["mode"] = mode
    curve_application = document.get("curve_application", "artifact_only")
    if curve_application not in {"artifact_only", "final_render"}:
        raise MotionConfigError(
            "curve_application must be artifact_only or final_render"
        )
    result["curve_application"] = curve_application
    final_render_profile = document.get("final_render_profile", "ace-source")
    if final_render_profile not in {"ace-source", "pose-asset-extended"}:
        raise MotionConfigError(
            "final_render_profile must be ace-source or pose-asset-extended"
        )
    if final_render_profile != "ace-source" and curve_application != "final_render":
        raise MotionConfigError(
            "pose-asset-extended requires curve_application=final_render"
        )
    result["final_render_profile"] = final_render_profile

    face = document.get("face_parameters", {})
    if not isinstance(face, dict) or set(face) - FACE_PARAMETER_NAMES:
        raise MotionConfigError("face_parameters contains unsupported names")
    result["face_parameters"] = {}
    for name, value in face.items():
        minimum, maximum = FACE_PARAMETER_SPECS[name]
        result["face_parameters"][name] = _config_number(
            value, f"face_parameters.{name}", minimum, maximum
        )

    runtime_curves = document.get("nvidia_runtime_curve_parameters", {})
    allowed_runtime = {"enable_clamping", "multipliers", "offsets"}
    if not isinstance(runtime_curves, dict) or set(runtime_curves) - allowed_runtime:
        raise MotionConfigError(
            "nvidia_runtime_curve_parameters contains unsupported keys"
        )
    enable_runtime_clamping = runtime_curves.get("enable_clamping", False)
    if not isinstance(enable_runtime_clamping, bool):
        raise MotionConfigError(
            "nvidia_runtime_curve_parameters.enable_clamping must be boolean"
        )
    runtime_multipliers = runtime_curves.get("multipliers", {})
    runtime_offsets = runtime_curves.get("offsets", {})
    supported_runtime_curves = set(ACE25_SOURCE_CURVE_NAMES)
    for label, values in (
        ("multipliers", runtime_multipliers),
        ("offsets", runtime_offsets),
    ):
        if not isinstance(values, dict):
            raise MotionConfigError(
                f"nvidia_runtime_curve_parameters.{label} must be an object"
            )
        unsupported = set(values) - supported_runtime_curves
        if unsupported:
            raise MotionConfigError(
                "NVIDIA ACE runtime does not consume curves: "
                + ", ".join(sorted(unsupported))
            )
    normalized_runtime_multipliers = {
        name: _config_number(
            value,
            f"nvidia_runtime_curve_parameters.multipliers.{name}",
            0.0,
            12.0,
        )
        for name, value in runtime_multipliers.items()
    }
    normalized_runtime_offsets = {
        name: _config_number(
            value,
            f"nvidia_runtime_curve_parameters.offsets.{name}",
            -1.0,
            1.0,
        )
        for name, value in runtime_offsets.items()
    }
    if mode == "baseline" and (
        enable_runtime_clamping
        or normalized_runtime_multipliers
        or normalized_runtime_offsets
    ):
        raise MotionConfigError(
            "mode=baseline cannot override NVIDIA runtime curve parameters"
        )
    result["nvidia_runtime_curve_parameters"] = {
        "enable_clamping": enable_runtime_clamping,
        "multipliers": normalized_runtime_multipliers,
        "offsets": normalized_runtime_offsets,
    }

    emotion = document.get("emotion", {})
    if not isinstance(emotion, dict) or set(emotion) - {"overall_strength", "constant", "timecoded"}:
        raise MotionConfigError("emotion contains unsupported keys")
    strength = emotion.get("overall_strength")
    if strength is not None:
        strength = _config_number(strength, "emotion.overall_strength", 0.0, 1.0)
    constant = emotion.get("constant", {})
    if not isinstance(constant, dict) or set(constant) - set(EMOTION_NAMES):
        raise MotionConfigError("emotion.constant contains unsupported names")
    constant_values = {
        name: _config_number(value, f"emotion.constant.{name}", 0.0, 1.0)
        for name, value in constant.items()
    }
    timecoded = emotion.get("timecoded", [])
    if not isinstance(timecoded, list):
        raise MotionConfigError("emotion.timecoded must be a list")
    normalized_timecoded = []
    previous = -math.inf
    for index, entry in enumerate(timecoded):
        if not isinstance(entry, dict) or set(entry) != {"time_seconds", "values"}:
            raise MotionConfigError(f"emotion.timecoded[{index}] has invalid keys")
        timestamp = _config_number(entry["time_seconds"], f"emotion.timecoded[{index}].time_seconds", 0.0)
        if timestamp <= previous:
            raise MotionConfigError("emotion timecodes must be strictly increasing")
        if audio_duration is not None and timestamp > audio_duration:
            raise MotionConfigError("emotion timecode exceeds audio duration")
        previous = timestamp
        values = entry["values"]
        if not isinstance(values, dict) or set(values) - set(EMOTION_NAMES):
            raise MotionConfigError("timecoded emotion contains unsupported names")
        normalized_timecoded.append({
            "time_seconds": timestamp,
            "values": {
                name: _config_number(value, f"emotion.{name}", 0.0, 1.0)
                for name, value in values.items()
            },
        })
    result["emotion"] = {
        "overall_strength": strength,
        "constant": constant_values,
        "timecoded": normalized_timecoded,
    }
    if constant_values and normalized_timecoded:
        raise MotionConfigError(
            "emotion.constant and emotion.timecoded are mutually exclusive"
        )

    post = document.get("artifact_postprocess", {})
    allowed_post = {"global_intensity", "attack", "release", "region_gains", "curve_operations"}
    if not isinstance(post, dict) or set(post) - allowed_post:
        raise MotionConfigError("artifact_postprocess contains unsupported keys")
    global_intensity = _config_number(post.get("global_intensity", 1.0), "global_intensity", 0.0, 4.0)
    attack = _config_number(post.get("attack", 1.0), "attack", 0.0, 1.0)
    release = _config_number(post.get("release", 1.0), "release", 0.0, 1.0)
    region_gains = post.get("region_gains", {})
    if not isinstance(region_gains, dict) or set(region_gains) - set(REGIONS):
        raise MotionConfigError("region_gains contains unsupported names")
    region_gains = {
        name: _config_number(value, f"region_gains.{name}", 0.0, 4.0)
        for name, value in region_gains.items()
    }
    operations = post.get("curve_operations", {})
    if not isinstance(operations, dict) or set(operations) - set(BLENDSHAPE_NAMES):
        raise MotionConfigError("curve_operations contains unsupported names")
    normalized_operations: dict[str, Any] = {}
    for name, operation in operations.items():
        if not isinstance(operation, dict) or set(operation) - {"gain", "bias", "clamp"}:
            raise MotionConfigError(f"invalid operation for {name}")
        clamp = operation.get("clamp", [0.0, 1.0])
        if not isinstance(clamp, list) or len(clamp) != 2:
            raise MotionConfigError(f"invalid clamp for {name}")
        low = _config_number(clamp[0], f"{name}.clamp[0]")
        high = _config_number(clamp[1], f"{name}.clamp[1]")
        if low > high:
            raise MotionConfigError(f"invalid clamp order for {name}")
        normalized_operations[name] = {
            "gain": _config_number(operation.get("gain", 1.0), f"{name}.gain", 0.0, 4.0),
            "bias": _config_number(operation.get("bias", 0.0), f"{name}.bias", -1.0, 1.0),
            "clamp": [low, high],
        }
    result["artifact_postprocess"] = {
        "global_intensity": global_intensity,
        "attack": attack,
        "release": release,
        "region_gains": region_gains,
        "curve_operations": normalized_operations,
    }
    has_postprocess = (
        abs(global_intensity - 1.0) > 1e-12
        or abs(attack - 1.0) > 1e-12
        or abs(release - 1.0) > 1e-12
        or any(abs(value - 1.0) > 1e-12 for value in region_gains.values())
        or any(
            abs(operation["gain"] - 1.0) > 1e-12
            or abs(operation["bias"]) > 1e-12
            or operation["clamp"] != [0.0, 1.0]
            for operation in normalized_operations.values()
        )
    )
    if mode == "baseline" and has_postprocess:
        raise MotionConfigError(
            "mode=baseline requires identity artifact_postprocess; "
            "use mode=enhanced to apply curve controls"
        )
    if (
        (has_postprocess or normalized_timecoded)
        and "curve_application" not in document
    ):
        raise MotionConfigError(
            "curve_application must explicitly select artifact_only or final_render "
            "when timecoded emotion or curve postprocess is configured"
        )
    if curve_application == "final_render":
        if (
            final_render_profile == "ace-source"
            and abs(region_gains.get("tongue", 1.0) - 1.0) > 1e-12
        ):
            raise MotionConfigError(
                "ACE source final_render does not consume the extended tongue region"
            )
        supported_curves = set(final_render_curve_names(result))
        unsupported = set(normalized_operations) - supported_curves
        if unsupported:
            raise MotionConfigError(
                "selected final_render profile does not consume curves: "
                + ", ".join(sorted(unsupported))
            )
    return result


def _region_gain(name: str, gains: dict[str, float]) -> float:
    for region, members in REGIONS.items():
        if name in members:
            return gains.get(region, 1.0)
    return 1.0


def apply_motion_enhancement(series: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if series.get("curve_names") != list(BLENDSHAPE_NAMES):
        raise MotionDataError("series does not use the canonical 68-curve schema")
    if config.get("mode") == "baseline":
        return copy.deepcopy(series)
    post = config["artifact_postprocess"]
    output = copy.deepcopy(series)
    output["source"] = "artifact-postprocess"
    previous: list[float] | None = None
    for frame in output["frames"]:
        values: list[float] = []
        for index, (name, raw_value) in enumerate(zip(BLENDSHAPE_NAMES, frame["values"])):
            value = _finite(raw_value, name) * post["global_intensity"]
            value *= _region_gain(name, post["region_gains"])
            operation = post["curve_operations"].get(name, {})
            value = value * operation.get("gain", 1.0) + operation.get("bias", 0.0)
            low, high = operation.get("clamp", [0.0, 1.0])
            value = min(max(value, low), high)
            if previous is not None:
                coefficient = post["attack"] if value > previous[index] else post["release"]
                value = previous[index] + coefficient * (value - previous[index])
                value = min(max(value, low), high)
            values.append(value)
        frame["values"] = values
        previous = values
    return output


def compare_motion_series(raw: dict[str, Any], effective: dict[str, Any]) -> dict[str, Any]:
    if raw.get("curve_names") != effective.get("curve_names") or len(raw["frames"]) != len(effective["frames"]):
        raise MotionDataError("series schemas/frame counts differ")
    metrics: dict[str, Any] = {"curves": {}}
    saturated = 0
    total = 0
    for index, name in enumerate(BLENDSHAPE_NAMES):
        a = [float(frame["values"][index]) for frame in raw["frames"]]
        b = [float(frame["values"][index]) for frame in effective["frames"]]
        rmse = math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b)) / len(a))
        jerk = 0.0
        if len(b) >= 3:
            jerk = sum(abs(b[i] - 2 * b[i - 1] + b[i - 2]) for i in range(2, len(b))) / (len(b) - 2)
        metrics["curves"][name] = {
            "raw_min": min(a), "raw_max": max(a),
            "effective_min": min(b), "effective_max": max(b),
            "rmse": rmse, "effective_temporal_second_difference_mean": jerk,
        }
        saturated += sum(1 for value in b if value <= 0.0 or value >= 1.0)
        total += len(b)
    metrics["saturation_fraction"] = saturated / total if total else 0.0
    return metrics


def build_effective_nim_config(
    base: dict[str, Any],
    config: dict[str, Any],
    *,
    include_artifact_postprocess: bool = True,
) -> dict[str, Any]:
    effective = copy.deepcopy(base)
    effective.setdefault("face_parameters", {}).update(config["face_parameters"])
    blendshape = effective.setdefault("blendshape_parameters", {})
    multipliers = blendshape.setdefault("multipliers", {})
    offsets = blendshape.setdefault("offsets", {})
    runtime_curves = config["nvidia_runtime_curve_parameters"]
    for name, multiplier in runtime_curves["multipliers"].items():
        multipliers[name] = multiplier
    for name, offset in runtime_curves["offsets"].items():
        offsets[name] = offset
    if runtime_curves["enable_clamping"]:
        blendshape["enable_clamping_bs_weight"] = True
    post = config["artifact_postprocess"]
    if config["mode"] == "enhanced" and include_artifact_postprocess:
        for name in BLENDSHAPE_NAMES:
            operation = post["curve_operations"].get(name, {})
            gain = (
                post["global_intensity"]
                * _region_gain(name, post["region_gains"])
                * operation.get("gain", 1.0)
            )
            multipliers[name] = float(multipliers.get(name, 1.0)) * gain
            offsets[name] = float(offsets.get(name, 0.0)) + operation.get("bias", 0.0)
        if post["curve_operations"]:
            blendshape["enable_clamping_bs_weight"] = True
    strength = config["emotion"].get("overall_strength")
    if strength is not None:
        effective.setdefault("post_processing_parameters", {})["emotion_strength"] = strength
    if config["emotion"]["constant"]:
        canonical_emotion = {
            name: float(config["emotion"]["constant"].get(name, 0.0))
            for name in EMOTION_NAMES
        }
        effective["beginning_emotion"] = canonical_emotion
        effective.setdefault("post_processing_parameters", {}).update(
            {
                "enable_preferred_emotion": True,
                "preferred_emotion_strength": 1.0,
            }
        )
        effective["emotion_with_timecode_list"] = {
            "emotion_with_timecode1": {
                "time_code": 0.0,
                "emotions": copy.deepcopy(canonical_emotion),
            }
        }
    elif config["emotion"]["timecoded"]:
        effective["emotion_with_timecode_list"] = {
            f"emotion_with_timecode{index + 1}": {
                "time_code": entry["time_seconds"],
                "emotions": {
                    name: float(entry["values"].get(name, 0.0))
                    for name in EMOTION_NAMES
                },
            }
            for index, entry in enumerate(config["emotion"]["timecoded"])
        }
    return effective


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_motion_series(series: dict[str, Any], json_path: Path, csv_path: Path) -> dict[str, Any]:
    json_path, csv_path = Path(json_path), Path(csv_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(series, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    names = series.get("curve_names") or series.get("emotion_names")
    if not isinstance(names, list):
        raise MotionDataError("series has no names")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frame_index", "time_seconds", *names])
        for frame in series["frames"]:
            writer.writerow([frame["frame_index"], frame["time_seconds"], *frame["values"]])
    return {
        "schema_version": 1,
        "json": {"path": str(json_path), "sha256": sha256_file(json_path)},
        "csv": {"path": str(csv_path), "sha256": sha256_file(csv_path)},
        "frames": len(series["frames"]),
        "channels": len(names),
    }
