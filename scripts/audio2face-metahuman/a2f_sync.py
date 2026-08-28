#!/usr/bin/env python3
"""Content-level Audio2Face timeline verification helpers."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any

import numpy as np


class A2FSyncError(ValueError):
    """Raised when content sync cannot be evaluated safely."""


def interpolate_curve_keys(
    times: list[float], values: list[float], target_time: float
) -> float:
    if (
        len(times) != len(values)
        or not times
        or any(not math.isfinite(value) for value in [*times, *values, target_time])
        or any(right <= left for left, right in zip(times, times[1:]))
    ):
        raise A2FSyncError("curve key samples are invalid")
    right = bisect.bisect_left(times, target_time)
    if right <= 0:
        return float(values[0])
    if right >= len(times):
        return float(values[-1])
    if times[right] == target_time:
        return float(values[right])
    left = right - 1
    alpha = (target_time - times[left]) / (times[right] - times[left])
    return float(values[left]) + alpha * (float(values[right]) - float(values[left]))


def verify_recorded_curve_samples(
    *,
    recorded: list[dict[str, Any]],
    effective_frames: list[dict[str, Any]],
    curve_names: list[str],
    tolerance: float = 1e-4,
) -> dict[str, Any]:
    if not recorded or tolerance < 0 or not math.isfinite(tolerance):
        raise A2FSyncError("recorded curve verification inputs are invalid")
    by_frame = {
        int(frame.get("frame_index", index)): frame
        for index, frame in enumerate(effective_frames)
    }
    maximum_error = 0.0
    comparisons = 0
    for sample in recorded:
        frame_index = int(sample["output_frame"])
        if frame_index not in by_frame:
            raise A2FSyncError("recorded sample frame is outside effective series")
        expected = by_frame[frame_index]
        if abs(float(sample["audio_time_seconds"]) - float(expected["time_seconds"])) > 1e-9:
            raise A2FSyncError("recorded curve sample uses a different audio time")
        for name, actual in sample["curves"].items():
            if name not in curve_names:
                raise A2FSyncError(f"recorded curve is not canonical: {name}")
            expected_value = float(expected["values"][curve_names.index(name)])
            error = abs(float(actual) - expected_value)
            maximum_error = max(maximum_error, error)
            comparisons += 1
            if error > tolerance:
                raise A2FSyncError(
                    f"recorded curve mismatch at frame {frame_index} {name}: "
                    f"{actual} vs {expected_value} (error {error})"
                )
    return {
        "schema_version": 1,
        "valid": True,
        "sample_count": len(recorded),
        "comparison_count": comparisons,
        "maximum_abs_error": maximum_error,
        "tolerance": tolerance,
    }


def capture_timeline_policy(curve_application: str) -> dict[str, str]:
    """Return the single timeline contract consumed by the UE capture helper."""
    if curve_application == "final_render":
        return {
            "curve_key_time_origin": "recorded_capture",
            "sequence_start_offset": "capture_offset",
            "content_sync_correction": "verified_post_render",
        }
    if curve_application == "artifact_only":
        return {
            "curve_key_time_origin": "recorded_capture",
            "sequence_start_offset": "capture_offset",
            "content_sync_correction": "diagnostic_if_correlated",
        }
    raise A2FSyncError(f"unsupported curve application: {curve_application}")


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.shape != right.shape or left.ndim != 1 or left.size < 8:
        raise A2FSyncError("correlation inputs must be equal one-dimensional series")
    left = left - left.mean()
    right = right - right.mean()
    scale = float(np.linalg.norm(left) * np.linalg.norm(right))
    if not math.isfinite(scale) or scale <= 1e-12:
        return 0.0
    return float(np.dot(left, right) / scale)


def _lagged_correlation(
    observed: np.ndarray, source: np.ndarray, lag_frames: int
) -> float:
    # Positive lag means the rendered observation is delayed relative to source.
    if lag_frames > 0:
        return _correlation(observed[lag_frames:], source[:-lag_frames])
    if lag_frames < 0:
        return _correlation(observed[:lag_frames], source[-lag_frames:])
    return _correlation(observed, source)


def estimate_visual_curve_lag(
    frame_features: np.ndarray,
    curve_values: np.ndarray,
    *,
    max_lag_frames: int = 8,
    component_count: int = 5,
) -> dict[str, Any]:
    """Estimate rendered-motion lag using PCA without assuming a face ROI."""
    features = np.asarray(frame_features, dtype=np.float64)
    curve = np.asarray(curve_values, dtype=np.float64)
    if features.ndim < 2:
        raise A2FSyncError("frame features must have a frame and feature dimension")
    features = features.reshape(features.shape[0], -1)
    if features.shape[0] != curve.size or curve.ndim != 1:
        raise A2FSyncError("frame and curve counts must match")
    if features.shape[0] < max(16, 2 * max_lag_frames + 4):
        raise A2FSyncError("not enough frames for content sync estimation")
    if not np.isfinite(features).all() or not np.isfinite(curve).all():
        raise A2FSyncError("sync inputs must be finite")
    if max_lag_frames < 0 or max_lag_frames > features.shape[0] // 4:
        raise A2FSyncError("max_lag_frames is outside the safe range")

    centered = features - features.mean(axis=0, keepdims=True)
    if float(np.linalg.norm(centered)) <= 1e-9 or float(np.ptp(curve)) <= 1e-9:
        raise A2FSyncError("rendered frames or reference curve are static")
    left, singular, _ = np.linalg.svd(centered, full_matrices=False)
    count = min(max(1, component_count), left.shape[1])
    components = left[:, :count] * singular[:count]

    candidates = []
    for component_index in range(count):
        component = components[:, component_index]
        for lag in range(-max_lag_frames, max_lag_frames + 1):
            signed = _lagged_correlation(component, curve, lag)
            candidates.append(
                (abs(signed), signed, lag, component_index)
            )
    score, signed, lag, component_index = max(candidates)
    zero_signed = _lagged_correlation(components[:, component_index], curve, 0)
    explained = singular[component_index] ** 2 / np.square(singular).sum()
    return {
        "schema_version": 1,
        "lag_frames": int(lag),
        "correlation": float(score),
        "signed_correlation": float(signed),
        "zero_lag_correlation": float(abs(zero_signed)),
        "principal_component": int(component_index),
        "principal_component_variance_fraction": float(explained),
        "lag_sign_convention": "positive means rendered avatar is delayed",
    }


def _decode_luma_frames(
    ffmpeg: Path,
    video: Path,
    *,
    frame_count: int,
    width: int = 160,
    height: int = 90,
) -> np.ndarray:
    if frame_count < 16 or frame_count > 100_000:
        raise A2FSyncError("frame_count is outside the safe range")
    result = subprocess.run(
        [
            str(ffmpeg), "-v", "error", "-i", str(video),
            "-vf", f"scale={width}:{height},format=gray",
            "-frames:v", str(frame_count), "-f", "rawvideo",
            "-pix_fmt", "gray", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise A2FSyncError(
            "could not decode avatar video for content sync: "
            + result.stderr.decode("utf-8", errors="replace")[-500:]
        )
    expected = frame_count * width * height
    if len(result.stdout) != expected:
        raise A2FSyncError(
            f"decoded avatar byte count mismatch: {len(result.stdout)} != {expected}"
        )
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(
        frame_count, height, width
    )


def _resampled_curve(
    motion_json: Path, curve_name: str, *, fps: int, frame_count: int
) -> np.ndarray:
    motion_json = Path(motion_json)
    if not motion_json.is_file() or motion_json.stat().st_size > 64 * 1024 * 1024:
        raise A2FSyncError("motion JSON is missing or exceeds 64 MiB")
    document = json.loads(motion_json.read_text(encoding="utf-8"))
    names = document.get("curve_names")
    frames = document.get("frames")
    if not isinstance(names, list) or curve_name not in names:
        raise A2FSyncError(f"motion JSON has no {curve_name} curve")
    if not isinstance(frames, list) or len(frames) < 2:
        raise A2FSyncError("motion JSON has insufficient frames")
    index = names.index(curve_name)
    times = np.asarray([frame["time_seconds"] for frame in frames], dtype=np.float64)
    values = np.asarray([frame["values"][index] for frame in frames], dtype=np.float64)
    if (
        not np.isfinite(times).all()
        or not np.isfinite(values).all()
        or np.any(np.diff(times) <= 0)
    ):
        raise A2FSyncError("motion JSON timecodes or curve values are invalid")
    target = np.arange(frame_count, dtype=np.float64) / float(fps)
    return np.interp(target, times, values)


def verify_avatar_curve_sync(
    *,
    ffmpeg: Path,
    avatar_video: Path,
    motion_json: Path,
    fps: int,
    frame_count: int,
    max_lag_frames: int = 18,
    minimum_confidence: float = 0.75,
    tolerance_frames: int = 1,
    curve_name: str = "JawOpen",
) -> dict[str, Any]:
    """Measure content sync; high-confidence offsets beyond tolerance fail."""
    if fps <= 0:
        raise A2FSyncError("fps must be positive")
    frames = _decode_luma_frames(
        ffmpeg, avatar_video, frame_count=frame_count
    )
    curve_values = _resampled_curve(
        motion_json, curve_name, fps=fps, frame_count=frame_count
    )
    result = estimate_visual_curve_lag(
        frames,
        curve_values,
        max_lag_frames=max_lag_frames,
        component_count=5,
    )
    result.update(
        {
            "curve": curve_name,
            "fps": int(fps),
            "frame_count": int(frame_count),
            "lag_ms": round(1000.0 * result["lag_frames"] / fps, 3),
            "minimum_confidence": float(minimum_confidence),
            "tolerance_frames": int(tolerance_frames),
            "method": f"full-frame grayscale PCA vs resampled A2F {curve_name}",
        }
    )
    if result["correlation"] < minimum_confidence:
        result["status"] = "inconclusive"
        result["reason"] = "rendered motion did not correlate strongly enough"
    elif abs(result["lag_frames"]) <= tolerance_frames:
        result["status"] = "aligned"
    else:
        result["status"] = "misaligned"
    return result


def build_avatar_sync_correction_command(
    *,
    ffmpeg: Path,
    source: Path,
    output: Path,
    lag_frames: int,
    fps: int,
    frame_count: int,
) -> list[str]:
    """Shift rendered video content while preserving its authoritative audio."""
    if lag_frames == 0:
        raise A2FSyncError("zero lag does not require correction")
    if fps <= 0 or frame_count < 1 or abs(lag_frames) >= frame_count // 2:
        raise A2FSyncError("sync correction parameters are outside the safe range")
    duration = abs(lag_frames) / float(fps)
    if lag_frames > 0:
        video_filter = (
            f"[0:v]trim=start_frame={lag_frames},setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={duration:.9f}[v]"
        )
    else:
        video_filter = (
            f"[0:v]tpad=start_mode=clone:start_duration={duration:.9f},"
            f"trim=end_frame={frame_count},setpts=PTS-STARTPTS[v]"
        )
    return [
        str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
        "-i", str(source), "-filter_complex", video_filter,
        "-map", "[v]", "-map", "0:a:0", "-frames:v", str(frame_count),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
        str(output),
    ]


def build_master_frame_map(
    *,
    raw_frames: list[dict[str, Any]],
    effective_frames: list[dict[str, Any]],
    curve_names: list[str],
    fps: int,
    frame_count: int,
    avatar_lag_frames: int,
    top_k: int = 8,
    mannequin_geometry_sha256: list[str] | None = None,
    active_curve_names: list[str] | None = None,
    active_curve_scope: str | None = None,
) -> list[dict[str, Any]]:
    if (
        fps <= 0
        or frame_count < 1
        or len(raw_frames) != frame_count
        or len(effective_frames) != frame_count
        or len(curve_names) != 68
        or not 1 <= top_k <= 68
    ):
        raise A2FSyncError("master frame-map inputs are inconsistent")
    if mannequin_geometry_sha256 is not None and len(
        mannequin_geometry_sha256
    ) != frame_count:
        raise A2FSyncError("mannequin geometry map length mismatch")
    records = []
    active_indices = (
        [curve_names.index(name) for name in active_curve_names]
        if active_curve_names is not None
        else list(range(68))
    )
    if not active_indices:
        raise A2FSyncError("master frame-map active curve scope is empty")
    for index in range(frame_count):
        raw = raw_frames[index]
        effective = effective_frames[index]
        target = index / float(fps)
        if (
            int(raw.get("frame_index", -1)) != index
            or int(effective.get("frame_index", -1)) != index
            or abs(float(raw.get("time_seconds", -1.0)) - target) > 1e-9
            or abs(float(effective.get("time_seconds", -1.0)) - target) > 1e-9
            or len(raw.get("values", [])) != 68
            or len(effective.get("values", [])) != 68
        ):
            raise A2FSyncError("resampled series is not on the master audio clock")
        order = sorted(
            active_indices,
            key=lambda curve_index: (
                -abs(float(effective["values"][curve_index])),
                curve_index,
            ),
        )[:top_k]
        avatar_source = max(0, min(frame_count - 1, index + avatar_lag_frames))
        record = {
            "schema_version": 1,
            "output_frame": index,
            "pts_seconds": target,
            "audio_time_seconds": target,
            "curve_time_seconds": target,
            "panel_source_frame": index,
            "panel_source_time_seconds": target,
            "mannequin_source_frame": index,
            "mannequin_source_time_seconds": target,
            "avatar_source_frame": avatar_source,
            "avatar_source_time_seconds": avatar_source / float(fps),
            "avatar_measured_lag_frames": int(avatar_lag_frames),
            "raw_source_mapping": raw.get("source_mapping"),
            "effective_source_mapping": effective.get("source_mapping"),
            "top_curves": [
                {
                    "name": curve_names[curve_index],
                    "raw": float(raw["values"][curve_index]),
                    "effective": float(effective["values"][curve_index]),
                }
                for curve_index in order
            ],
            "top_curve_scope": (
                active_curve_scope
                or (
                    "custom-render-consumed"
                    if active_curve_names is not None
                    else "all-A2F-68"
                )
            ),
        }
        if mannequin_geometry_sha256 is not None:
            record["mannequin_geometry_sha256"] = mannequin_geometry_sha256[index]
        records.append(record)
    return records


def write_frame_map_jsonl(
    records: list[dict[str, Any]], path: Path
) -> dict[str, Any]:
    if not records:
        raise A2FSyncError("frame map is empty")
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    os.replace(temporary, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "path": str(path),
        "sha256": digest,
        "frame_count": len(records),
        "first_pts_seconds": float(records[0]["pts_seconds"]),
        "last_pts_seconds": float(records[-1]["pts_seconds"]),
        "master_clock": "source-audio-seconds",
        "avatar_mapping": "clamp(output_frame + measured_lag_frames)",
        "panel_mapping": "output_frame at audio_time_seconds",
        "mannequin_mapping": "output_frame at audio_time_seconds",
    }
