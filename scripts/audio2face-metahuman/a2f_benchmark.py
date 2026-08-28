#!/usr/bin/env python3
"""Frame/time-based Audio2Face regression-versus-diffusion benchmark metrics."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any


def _load_motion():
    path = Path(__file__).with_name("a2f_motion.py")
    spec = importlib.util.spec_from_file_location("_a2f_motion_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


motion = _load_motion()


def _curve_metrics(times: list[float], values: list[float]) -> dict[str, float]:
    if not values or len(times) != len(values):
        raise ValueError("times and values must be non-empty and aligned")
    if not all(math.isfinite(value) for value in [*times, *values]):
        raise ValueError("benchmark values must be finite")
    velocities = [
        (values[index] - values[index - 1]) / (times[index] - times[index - 1])
        for index in range(1, len(values))
    ]
    accelerations = [
        (velocities[index] - velocities[index - 1])
        / ((times[index + 1] - times[index - 1]) / 2.0)
        for index in range(1, len(velocities))
    ]
    return {
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "mean": fmean(values),
        "standard_deviation": pstdev(values),
        "velocity_abs_mean_per_second": fmean(map(abs, velocities)) if velocities else 0.0,
        "temporal_second_derivative_abs_mean": fmean(map(abs, accelerations)) if accelerations else 0.0,
        "outside_unit_range_fraction": sum(value < 0.0 or value > 1.0 for value in values) / len(values),
        "upper_saturation_fraction": sum(value >= 0.999 for value in values) / len(values),
    }


def _inferred_fps(times: list[float]) -> float:
    if len(times) < 2:
        return 0.0
    intervals = [right - left for left, right in zip(times, times[1:])]
    if any(interval <= 0.0 for interval in intervals):
        raise ValueError("timecodes must be strictly increasing")
    return 1.0 / fmean(intervals)


def _region_metrics(curves: dict[str, dict[str, float]], names: tuple[str, ...]) -> dict[str, float]:
    members = [curves[name] for name in names]
    return {
        "curve_count": len(members),
        "active_curve_fraction": sum(item["range"] > 0.01 for item in members) / len(members),
        "range_mean": fmean(item["range"] for item in members),
        "standard_deviation_mean": fmean(item["standard_deviation"] for item in members),
        "velocity_abs_mean_per_second": fmean(item["velocity_abs_mean_per_second"] for item in members),
        "temporal_second_derivative_abs_mean": fmean(item["temporal_second_derivative_abs_mean"] for item in members),
        "outside_unit_range_fraction_mean": fmean(item["outside_unit_range_fraction"] for item in members),
        "upper_saturation_fraction_mean": fmean(item["upper_saturation_fraction"] for item in members),
    }


def summarize_motion(series: dict[str, Any]) -> dict[str, Any]:
    if series.get("curve_names") != list(motion.BLENDSHAPE_NAMES):
        raise ValueError("motion series must use canonical NVIDIA A2F-68 order")
    frames = series.get("frames", [])
    if not frames:
        raise ValueError("motion series is empty")
    times = [float(frame["time_seconds"]) for frame in frames]
    curves = {
        name: _curve_metrics(times, [float(frame["values"][index]) for frame in frames])
        for index, name in enumerate(motion.BLENDSHAPE_NAMES)
    }
    return {
        "frame_count": len(frames),
        "first_time_seconds": times[0],
        "last_time_seconds": times[-1],
        "inferred_fps": _inferred_fps(times),
        "curves": curves,
        "regions": {
            name: _region_metrics(curves, members)
            for name, members in motion.REGIONS.items()
        },
    }


def summarize_emotions(series: dict[str, Any]) -> dict[str, dict[str, float]]:
    if series.get("emotion_names") != list(motion.EMOTION_NAMES):
        raise ValueError("emotion series must use canonical NVIDIA A2E-10 order")
    frames = series.get("frames", [])
    if not frames:
        raise ValueError("emotion series is empty")
    times = [float(frame["time_seconds"]) for frame in frames]
    return {
        name: _curve_metrics(times, [float(frame["values"][index]) for frame in frames])
        for index, name in enumerate(motion.EMOTION_NAMES)
    }


def _ratio(candidate: float, baseline: float) -> float | None:
    return candidate / baseline if abs(baseline) > 1e-12 else None


def compare_model_outputs(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    baseline_emotions: dict[str, Any],
    candidate_emotions: dict[str, Any],
    baseline_id: str,
    candidate_id: str,
) -> dict[str, Any]:
    left = summarize_motion(baseline)
    right = summarize_motion(candidate)
    left["emotions"] = summarize_emotions(baseline_emotions)
    right["emotions"] = summarize_emotions(candidate_emotions)
    deltas = {}
    ratio_metrics = (
        "range_mean", "standard_deviation_mean",
        "velocity_abs_mean_per_second", "temporal_second_derivative_abs_mean",
    )
    for region in motion.REGIONS:
        deltas[region] = {
            metric: {
                "absolute": right["regions"][region][metric] - left["regions"][region][metric],
                "ratio": _ratio(right["regions"][region][metric], left["regions"][region][metric]),
            }
            for metric in ratio_metrics
        }
    return {
        "schema_version": 1,
        "baseline_id": baseline_id,
        "candidate_id": candidate_id,
        "baseline": left,
        "candidate": right,
        "region_deltas": deltas,
        "interpretation_boundary": (
            "Metrics measure motion magnitude, activity, bounds, and temporal derivatives; "
            "they do not constitute a perceptual naturalness score."
        ),
    }


def write_benchmark_report(report: dict[str, Any], path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "sha256": digest, "size_bytes": path.stat().st_size}
