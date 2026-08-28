#!/usr/bin/env python3
"""Validate direct SDK tensors and compare SDK solver weights with NIM curves."""

import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np


ROOT = Path(os.environ.get("A2F_SDK_OUTPUT_DIR", "/output"))
MODEL = Path(os.environ.get("A2F_SDK_MODEL_DIR", "/models"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamps(path):
    rows = list(csv.DictReader(path.open()))
    values = [int(row["timestamp_current"]) for row in rows]
    if not values or any(right <= left for left, right in zip(values, values[1:])):
        raise RuntimeError(f"non-monotonic timestamps: {path}")
    return rows, values


def read_f32(path, frames, width):
    values = np.fromfile(path, dtype=np.float32)
    if values.size != frames * width or not np.isfinite(values).all():
        raise RuntimeError(f"invalid tensor file: {path}")
    return values.reshape(frames, width)


def align_timecodes(sdk_seconds, nim_seconds, tolerance_seconds=0.009):
    if not sdk_seconds or not nim_seconds:
        raise RuntimeError("time alignment requires non-empty SDK and NIM timelines")
    nim = np.asarray(nim_seconds, dtype=np.float64)
    nearest_indices = []
    deltas = []
    for value in sdk_seconds:
        index = int(np.argmin(np.abs(nim - value)))
        nearest_indices.append(index)
        deltas.append(float(nim[index] - value))
    maximum = max(abs(value) for value in deltas)
    start_delta = float(nim_seconds[0] - sdk_seconds[0])
    end_delta = float(nim_seconds[-1] - sdk_seconds[-1])
    within = all(
        abs(value) <= tolerance_seconds
        for value in (maximum, start_delta, end_delta)
    )
    return {
        "status": "within_tolerance" if within else "outside_tolerance",
        "tolerance_seconds": tolerance_seconds,
        "maximum_abs_delta_seconds": maximum,
        "window_start_delta_seconds": start_delta,
        "window_end_delta_seconds": end_delta,
        "nearest_indices": nearest_indices,
        "signed_deltas_seconds": deltas,
    }


def parse_request_adjustments(path):
    multipliers = {}
    offsets = {}
    section = None
    subsection = None
    clamp = False
    for raw_line in path.read_text().splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        if indent == 0:
            section = stripped.removesuffix(":")
            subsection = None
            continue
        if section != "blendshape_parameters":
            continue
        key, _, value = stripped.partition(":")
        value = value.strip()
        if indent == 2 and not value:
            subsection = key
        elif indent == 2 and key == "enable_clamping_bs_weight":
            clamp = value.casefold() == "true"
        elif indent == 4 and subsection in {"multipliers", "offsets"}:
            target = multipliers if subsection == "multipliers" else offsets
            target[key.casefold()] = float(value)
    return {"multipliers": multipliers, "offsets": offsets, "clamp": clamp}


def apply_request_adjustments(weights, names, config):
    adjusted = np.asarray(weights, dtype=np.float32).copy()
    for index, name in enumerate(names):
        key = name.casefold()
        adjusted[:, index] = (
            adjusted[:, index] * config["multipliers"].get(key, 1.0)
            + config["offsets"].get(key, 0.0)
        )
    if config.get("clamp", False):
        np.clip(adjusted, 0.0, 1.0, out=adjusted)
    return adjusted


def error_metrics(values, reference):
    error = values - reference
    return {
        "mean_abs_error": float(np.abs(error).mean()),
        "root_mean_square_error": float(np.sqrt(np.square(error).mean())),
        "maximum_abs_error": float(np.abs(error).max()),
    }


def main():
    geometry_meta = json.loads((ROOT / "geometry/geometry-metadata.json").read_text())
    weights_meta = json.loads((ROOT / "weights/weights-metadata.json").read_text())
    geometry_rows, geometry_ts = timestamps(ROOT / "geometry/timestamps.csv")
    weight_rows, weight_ts = timestamps(ROOT / "weights/weights-timestamps.csv")
    frames = geometry_meta["frame_count"]
    if frames != len(geometry_rows) or weights_meta["frame_count"] != len(weight_rows):
        raise RuntimeError("metadata frame count mismatch")
    skin = read_f32(ROOT / "geometry/skin.f32", frames, geometry_meta["skin_size"])
    tongue = read_f32(ROOT / "geometry/tongue.f32", frames, geometry_meta["tongue_size"])
    jaw = read_f32(ROOT / "geometry/jaw.f32", frames, geometry_meta["jaw_size"])
    eyes = read_f32(ROOT / "geometry/eyes.f32", frames, geometry_meta["eyes_size"])
    weights = read_f32(
        ROOT / "weights/weights.f32", weights_meta["frame_count"], weights_meta["weight_count"]
    )
    skin_basis = np.load(MODEL / "bs_skin_Claire.npz")
    tongue_basis = np.load(MODEL / "bs_tongue_Claire.npz")
    skin_names = [value.decode() for value in skin_basis["poseNames"]][1:]
    tongue_names = [value.decode() for value in tongue_basis["poseNames"]][1:]
    names = skin_names + tongue_names
    if len(names) != weights.shape[1]:
        raise RuntimeError("official solver weight count does not match basis names")

    nim_path = Path("/nim/animation_frames.csv")
    nim_rows = list(csv.DictReader(nim_path.open()))
    nim_names = [name for name in nim_rows[0] if name.startswith("blendShapes.")]
    nim_index = {name.split(".", 1)[1].casefold(): name for name in nim_names}
    sdk_seconds = [timestamp / 16000.0 for timestamp in weight_ts]
    nim_seconds = [float(row["timeCode"]) for row in nim_rows]
    time_alignment = align_timecodes(sdk_seconds, nim_seconds)
    if time_alignment["status"] != "within_tolerance":
        raise RuntimeError(f"SDK/NIM time alignment is outside tolerance: {time_alignment}")
    aligned = []
    for index in time_alignment["nearest_indices"]:
        nearest = nim_rows[index]
        aligned.append([float(nearest[nim_index[name.casefold()]]) for name in names])
    aligned = np.asarray(aligned, dtype=np.float32)
    request_path = Path("/input/request.yml")
    request_adjustments = parse_request_adjustments(request_path)
    request_adjusted_weights = apply_request_adjustments(
        weights, names, request_adjustments
    )
    raw_error_metrics = error_metrics(weights, aligned)
    adjusted_error_metrics = error_metrics(request_adjusted_weights, aligned)

    deltas = np.stack([skin_basis[name] for name in skin_names], axis=0)
    common_frames = min(frames, weights.shape[0])
    reconstructed = skin_basis["neutral"][None, :, :] + np.einsum(
        "fw,wvc->fvc", weights[:common_frames, : len(skin_names)], deltas
    )
    direct = skin[:common_frames].reshape(common_frames, -1, 3)
    reconstruction_error = direct - reconstructed

    ply_dir = ROOT / "ply"; ply_dir.mkdir(exist_ok=True)
    representative_output_frames = (0, 83, 86)
    representative = sorted({
        int(np.argmin(np.abs(np.asarray(geometry_ts, dtype=np.float64) / 16000.0 - output_frame / 30.0)))
        for output_frame in representative_output_frames
    })
    ply_records = []
    for frame in representative:
        path = ply_dir / f"skin-frame-{frame:04d}.ply"
        vertices = direct[frame]
        with path.open("w") as stream:
            stream.write("ply\nformat ascii 1.0\n")
            stream.write(f"element vertex {len(vertices)}\nproperty float x\nproperty float y\nproperty float z\nend_header\n")
            np.savetxt(stream, vertices, fmt="%.7g")
        ply_records.append({
            "source_frame": frame,
            "source_time_seconds": geometry_ts[frame] / 16000.0,
            "corresponding_output_frame_30fps": int(round(geometry_ts[frame] / 16000.0 * 30.0)),
            "path": str(path),
            "sha256": digest(path),
        })

    report = {
        "schema_version": 1,
        "status": "pass",
        "lineage": {
            "sdk_commit": "1ca0f02535ed774f5dbcd724a31cd486368dc783",
            "model_revision": "Audio2Face-3D-v3.0-b741327/multi_v3.2",
            "container_image_digest": os.environ.get("A2F_SDK_IMAGE_DIGEST"),
            "input_audio": {"path": "/input/test.wav", "sha256": digest(Path("/input/test.wav"))},
            "emotion_input": {"path": "/input/emotions.csv", "sha256": digest(Path("/input/emotions.csv"))},
            "request_config": {"path": str(request_path), "sha256": digest(request_path)},
            "nim_animation_frames": {"path": str(nim_path), "sha256": digest(nim_path)},
            "model_files": {
                name: {"sha256": digest(MODEL / name)}
                for name in ("network.onnx", "trt_info.json", "model.json")
            },
            "engine_manifest": json.loads((MODEL / "engine-manifest.json").read_text()),
        },
        "geometry": {
            "frames": frames,
            "skin_shape": list(direct.shape),
            "tongue_shape": [frames, geometry_meta["tongue_size"] // 3, 3],
            "jaw_shape": list(jaw.shape),
            "eyes_shape": list(eyes.shape),
            "finite": True,
            "timestamps_monotonic": True,
        },
        "sdk_solver_vs_nim": {
            "status": "measured",
            "within_tolerance": None,
            "acceptance_threshold": None,
            "interpretation": "Diagnostic comparison; NVIDIA publishes no equality tolerance for independent stateful executions.",
            "frames": int(weights.shape[0]),
            "weights": int(weights.shape[1]),
            "time_alignment": time_alignment,
            "comparison_layer": "official SDK solver plus request-time multiplier/offset vs NIM client output",
            "request_adjustments": request_adjustments,
            **adjusted_error_metrics,
        },
        "sdk_solver_raw_vs_nim_client_output": {
            "status": "measured",
            "within_tolerance": None,
            "acceptance_threshold": None,
            "comparison_layer": "official SDK solver before request-time multiplier/offset vs NIM client output",
            "frames": int(weights.shape[0]),
            "weights": int(weights.shape[1]),
            "time_alignment": time_alignment,
            **raw_error_metrics,
        },
        "direct_geometry_vs_solver_reconstruction": {
            "status": "measured",
            "within_tolerance": None,
            "acceptance_threshold": None,
            "frames": common_frames,
            "vertices": int(direct.shape[1]),
            "mean_euclidean_error": float(np.linalg.norm(reconstruction_error, axis=2).mean()),
            "root_mean_square_coordinate_error": float(np.sqrt(np.square(reconstruction_error).mean())),
            "maximum_euclidean_error": float(np.linalg.norm(reconstruction_error, axis=2).max()),
            "semantic_boundary": "Official high-resolution Claire solver basis; not the low-resolution 68-curve video mannequin topology.",
        },
        "inspectable_geometry": ply_records,
        "files": {
            str(path.relative_to(ROOT)): {"sha256": digest(path), "size_bytes": path.stat().st_size}
            for path in ROOT.rglob("*") if path.is_file() and path.name != "verification.json"
        },
    }
    output = ROOT / "verification.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
