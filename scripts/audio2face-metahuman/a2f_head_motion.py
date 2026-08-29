#!/usr/bin/env python3
"""Deterministic local audio-responsive MetaHuman head-motion artifacts.

This module is not an NVIDIA Audio2Face output. It generates bounded local
rotation samples that are baked into run-owned Unreal Engine Body/Face
AnimSequence bone tracks.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any
import wave


class HeadMotionError(ValueError):
    """Raised when head-motion configuration or source audio is invalid."""


PROFILE_VERSION = "subtle-conversational-v1"
HEAD_MOTION_KEYS = {
    "schema_version",
    "enabled",
    "profile",
    "strength",
    "pitch_limit_deg",
    "yaw_limit_deg",
    "roll_limit_deg",
    "smoothing_seconds",
    "silence_threshold_dbfs",
}


def resolve_head_motion_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "enabled": False,
        "profile": "off",
        "strength": 1.0,
        "pitch_limit_deg": 2.5,
        "yaw_limit_deg": 4.0,
        "roll_limit_deg": 1.5,
        "smoothing_seconds": 0.22,
        "silence_threshold_dbfs": -42.0,
    }


def _finite_number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HeadMotionError(f"head_motion.{name} must be a JSON number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HeadMotionError(f"head_motion.{name} must be numeric") from exc
    if not math.isfinite(result) or result < low or result > high:
        raise HeadMotionError(
            f"head_motion.{name} must be finite and in [{low}, {high}]"
        )
    return result


def validate_head_motion_config(document: dict[str, Any] | None) -> dict[str, Any]:
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise HeadMotionError("head_motion must be an object")
    unknown = set(document) - HEAD_MOTION_KEYS
    if unknown:
        raise HeadMotionError(f"head_motion has unknown keys: {sorted(unknown)}")
    result = resolve_head_motion_config()
    if document.get("schema_version", 1) != 1:
        raise HeadMotionError("head_motion.schema_version must be 1")
    enabled = document.get("enabled", result["enabled"])
    if not isinstance(enabled, bool):
        raise HeadMotionError("head_motion.enabled must be boolean")
    profile = document.get(
        "profile", "subtle-conversational" if enabled else result["profile"]
    )
    if profile not in {"off", "subtle-conversational"}:
        raise HeadMotionError("head_motion.profile is unsupported")
    if enabled and profile != "subtle-conversational":
        raise HeadMotionError("enabled head motion requires subtle-conversational")
    if not enabled and profile != "off":
        raise HeadMotionError("disabled head motion requires profile=off")
    result.update(
        {
            "enabled": enabled,
            "profile": profile,
            "strength": _finite_number(
                document.get("strength", result["strength"]), "strength", 0.0, 1.5
            ),
            "pitch_limit_deg": _finite_number(
                document.get("pitch_limit_deg", result["pitch_limit_deg"]),
                "pitch_limit_deg",
                0.0,
                6.0,
            ),
            "yaw_limit_deg": _finite_number(
                document.get("yaw_limit_deg", result["yaw_limit_deg"]),
                "yaw_limit_deg",
                0.0,
                8.0,
            ),
            "roll_limit_deg": _finite_number(
                document.get("roll_limit_deg", result["roll_limit_deg"]),
                "roll_limit_deg",
                0.0,
                4.0,
            ),
            "smoothing_seconds": _finite_number(
                document.get("smoothing_seconds", result["smoothing_seconds"]),
                "smoothing_seconds",
                0.08,
                0.8,
            ),
            "silence_threshold_dbfs": _finite_number(
                document.get(
                    "silence_threshold_dbfs", result["silence_threshold_dbfs"]
                ),
                "silence_threshold_dbfs",
                -60.0,
                -25.0,
            ),
        }
    )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_pcm16_mono(path: Path) -> tuple[list[int], int, float]:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise HeadMotionError("head-motion WAV is missing")
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        width = stream.getsampwidth()
        rate = stream.getframerate()
        count = stream.getnframes()
        payload = stream.readframes(count)
    if channels != 1 or width != 2 or rate <= 0 or count <= 0:
        raise HeadMotionError("head-motion WAV must be non-empty PCM16 mono")
    samples = list(struct.unpack(f"<{count}h", payload))
    return samples, rate, count / float(rate)


def _ema(previous: float, target: float, dt: float, seconds: float) -> float:
    alpha = 1.0 - math.exp(-dt / max(seconds, 1e-6))
    return previous + alpha * (target - previous)


def _metrics(frames: list[dict[str, float]], fps: float) -> dict[str, Any]:
    result: dict[str, Any] = {"schema_version": 1, "frame_count": len(frames)}
    dt = 1.0 / fps
    for axis in ("pitch_deg", "yaw_deg", "roll_deg"):
        values = [float(frame[axis]) for frame in frames]
        velocities = [
            (right - left) / dt for left, right in zip(values, values[1:])
        ]
        jerks = [
            (right - 2.0 * middle + left) / (dt * dt)
            for left, middle, right in zip(values, values[1:], values[2:])
        ]
        result[axis] = {
            "min": min(values, default=0.0),
            "max": max(values, default=0.0),
            "rms": math.sqrt(sum(value * value for value in values) / max(1, len(values))),
            "peak_velocity_deg_per_s": max(map(abs, velocities), default=0.0),
            "peak_second_difference_deg_per_s2": max(map(abs, jerks), default=0.0),
        }
    result["activity"] = {
        "mean": sum(float(frame["activity"]) for frame in frames) / max(1, len(frames)),
        "max": max((float(frame["activity"]) for frame in frames), default=0.0),
    }
    return result


def generate_head_motion_series(
    wav_path: Path,
    config: dict[str, Any],
    fps: float,
    frame_count: int | None = None,
) -> dict[str, Any]:
    config = validate_head_motion_config(config)
    if not math.isfinite(float(fps)) or fps <= 0 or fps > 240:
        raise HeadMotionError("head-motion fps must be in (0, 240]")
    samples, sample_rate, duration = _read_pcm16_mono(Path(wav_path))
    expected = math.ceil(duration * fps) if frame_count is None else int(frame_count)
    if expected < 1 or expected > 100_000:
        raise HeadMotionError("head-motion frame count is outside the safe range")
    dt = 1.0 / float(fps)
    threshold = float(config["silence_threshold_dbfs"])
    speech_reference = -18.0
    activity = 0.0
    pitch = yaw = roll = 0.0
    frames: list[dict[str, Any]] = []
    for index in range(expected):
        start = min(len(samples), int(math.floor(index * sample_rate / fps)))
        end = min(
            len(samples),
            max(start + 1, int(math.ceil((index + 1) * sample_rate / fps))),
        )
        window = samples[start:end]
        rms = math.sqrt(sum(value * value for value in window) / max(1, len(window)))
        dbfs = -120.0 if rms <= 0.0 else 20.0 * math.log10(rms / 32768.0)
        raw_activity = max(
            0.0,
            min(1.0, (dbfs - threshold) / max(1e-6, speech_reference - threshold)),
        )
        tau = 0.08 if raw_activity > activity else 0.35
        activity = _ema(activity, raw_activity, dt, tau)
        time_seconds = index / float(fps)
        remaining = max(0.0, duration - time_seconds)
        end_fade = min(1.0, remaining / 0.30)
        gain = (
            float(config["strength"])
            * activity
            * end_fade
            if config["enabled"]
            else 0.0
        )
        target_pitch = float(config["pitch_limit_deg"]) * gain * (
            0.34 * math.sin(2.0 * math.pi * 0.38 * time_seconds + 0.2)
            + 0.16 * math.sin(2.0 * math.pi * 0.19 * time_seconds + 1.3)
        )
        target_yaw = float(config["yaw_limit_deg"]) * gain * (
            0.58 * math.sin(2.0 * math.pi * 0.22 * time_seconds + 0.6)
            + 0.18 * math.sin(2.0 * math.pi * 0.11 * time_seconds + 1.7)
        )
        target_roll = float(config["roll_limit_deg"]) * gain * (
            0.48 * math.sin(2.0 * math.pi * 0.31 * time_seconds + 2.1)
            + 0.14 * math.sin(2.0 * math.pi * 0.16 * time_seconds + 0.4)
        )
        smooth = float(config["smoothing_seconds"])
        pitch = _ema(pitch, target_pitch, dt, smooth)
        yaw = _ema(yaw, target_yaw, dt, smooth)
        roll = _ema(roll, target_roll, dt, smooth)
        if float(config["strength"]) == 0.0 or not config["enabled"]:
            pitch = yaw = roll = 0.0
        settle = min(1.0, remaining / 0.18)
        frame = {
            "frame_index": index,
            "time_seconds": time_seconds,
            "activity": activity,
            "audio_dbfs": dbfs,
            "pitch_deg": max(-config["pitch_limit_deg"], min(config["pitch_limit_deg"], pitch * settle)),
            "yaw_deg": max(-config["yaw_limit_deg"], min(config["yaw_limit_deg"], yaw * settle)),
            "roll_deg": max(-config["roll_limit_deg"], min(config["roll_limit_deg"], roll * settle)),
        }
        if not all(math.isfinite(float(value)) for value in frame.values()):
            raise HeadMotionError("generated head-motion sample is non-finite")
        frames.append(frame)
    metrics = _metrics(frames, float(fps))
    return {
        "schema_version": 1,
        "source": "local-procedural-audio-responsive",
        "official_nvidia_output": False,
        "profile_version": PROFILE_VERSION,
        "coordinate_space": "local-bone-additive",
        "audio_sha256": _sha256(Path(wav_path).expanduser().resolve()),
        "audio_duration_seconds": duration,
        "sample_rate": sample_rate,
        "fps": float(fps),
        "frame_count": expected,
        "config": config,
        "frames": frames,
        "metrics": metrics,
    }


def compensate_frames_for_video_advance(
    frames: list[dict[str, Any]], video_advance_frames: int
) -> dict[str, Any]:
    """Delay baked motion so a measured final video advance restores audio time.

    Positive content-sync correction trims leading avatar frames. The applied
    bone sequence is delayed by the same amount before rendering. The final
    compensation window is used for a deterministic neutral settle because
    the video correction clones its last available frame.
    """
    if (
        isinstance(video_advance_frames, bool)
        or not isinstance(video_advance_frames, int)
        or video_advance_frames < 0
        or video_advance_frames * 2 >= len(frames)
    ):
        raise HeadMotionError(
            "head-motion video advance must be a non-negative integer below half the frame count"
        )
    if not frames:
        raise HeadMotionError("head-motion compensation requires frames")
    axes = ("pitch_deg", "yaw_deg", "roll_deg")
    applied: list[dict[str, Any]] = []
    for target_index, current in enumerate(frames):
        frame = dict(current)
        if video_advance_frames == 0:
            source_index = target_index
            scale = 1.0
        elif target_index < video_advance_frames:
            source_index = None
            scale = 0.0
        else:
            source_index = target_index - video_advance_frames
            tail_start = len(frames) - video_advance_frames
            if target_index < tail_start:
                scale = 1.0
            elif video_advance_frames == 1:
                scale = 0.0
            else:
                scale = (len(frames) - 1 - target_index) / float(
                    video_advance_frames - 1
                )
        if source_index is None:
            for axis in axes:
                frame[axis] = 0.0
        else:
            source = frames[source_index]
            for axis in axes:
                frame[axis] = float(source[axis]) * scale
        frame["source_frame_index"] = source_index
        frame["render_sync_scale"] = scale
        applied.append(frame)
    return {
        "schema_version": 1,
        "video_advance_frames": video_advance_frames,
        "tail_settle_frames": video_advance_frames,
        "mapping": "raw_frame i uses source i-L; final L frames settle to neutral",
        "frames": applied,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def write_head_motion_artifacts(
    series: dict[str, Any],
    output_dir: Path,
    *,
    video_advance_frames: int = 0,
) -> dict[str, Any]:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_json = output_dir / "head-motion.samples.json"
    sample_csv = output_dir / "head-motion.samples.csv"
    metrics_json = output_dir / "head-motion.metrics.json"
    applied_json = output_dir / "head-motion.applied.samples.json"
    _write_json(sample_json, series)
    compensated = compensate_frames_for_video_advance(
        series["frames"], video_advance_frames
    )
    applied_payload = {
        **series,
        "frames": compensated["frames"],
        "render_sync_compensation": {
            key: value for key, value in compensated.items() if key != "frames"
        },
        "source_samples_sha256": _sha256(sample_json),
    }
    _write_json(applied_json, applied_payload)
    with sample_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "frame_index",
                "time_seconds",
                "activity",
                "audio_dbfs",
                "pitch_deg",
                "yaw_deg",
                "roll_deg",
            ]
        )
        for frame in series["frames"]:
            writer.writerow(
                [
                    int(frame["frame_index"]),
                    f"{float(frame['time_seconds']):.12f}",
                    f"{float(frame['activity']):.12f}",
                    f"{float(frame['audio_dbfs']):.9f}",
                    f"{float(frame['pitch_deg']):.9f}",
                    f"{float(frame['yaw_deg']):.9f}",
                    f"{float(frame['roll_deg']):.9f}",
                ]
            )
    metrics_payload = {
        "schema_version": 1,
        "source": series["source"],
        "official_nvidia_output": False,
        "profile_version": series["profile_version"],
        "fps": series["fps"],
        "frame_count": series["frame_count"],
        "metrics": series["metrics"],
    }
    _write_json(metrics_json, metrics_payload)

    def record(path: Path) -> dict[str, Any]:
        return {
            "path": str(path),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }

    return {
        "schema_version": 1,
        "samples_json": record(sample_json),
        "samples_csv": record(sample_csv),
        "metrics_json": record(metrics_json),
        "applied_samples_json": record(applied_json),
    }
