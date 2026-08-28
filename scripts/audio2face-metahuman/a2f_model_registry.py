#!/usr/bin/env python3
"""Pinned official Audio2Face model identities and reproducible preflight."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


class ModelProfileError(ValueError):
    pass


A2F_SDK_COMMIT = "1ca0f02535ed774f5dbcd724a31cd486368dc783"
A2F_V3_MODEL_REVISION = "b74132732fd9a9d29b237bec193ded64c9745e91"
A2F_68_NAMES = (
    "EyeBlinkLeft", "EyeLookDownLeft", "EyeLookInLeft", "EyeLookOutLeft",
    "EyeLookUpLeft", "EyeSquintLeft", "EyeWideLeft", "EyeBlinkRight",
    "EyeLookDownRight", "EyeLookInRight", "EyeLookOutRight", "EyeLookUpRight",
    "EyeSquintRight", "EyeWideRight", "JawForward", "JawLeft", "JawRight",
    "JawOpen", "MouthClose", "MouthFunnel", "MouthPucker", "MouthLeft",
    "MouthRight", "MouthSmileLeft", "MouthSmileRight", "MouthFrownLeft",
    "MouthFrownRight", "MouthDimpleLeft", "MouthDimpleRight", "MouthStretchLeft",
    "MouthStretchRight", "MouthRollLower", "MouthRollUpper", "MouthShrugLower",
    "MouthShrugUpper", "MouthPressLeft", "MouthPressRight", "MouthLowerDownLeft",
    "MouthLowerDownRight", "MouthUpperUpLeft", "MouthUpperUpRight", "BrowDownLeft",
    "BrowDownRight", "BrowInnerUp", "BrowOuterUpLeft", "BrowOuterUpRight",
    "CheekPuff", "CheekSquintLeft", "CheekSquintRight", "NoseSneerLeft",
    "NoseSneerRight", "TongueOut", "TongueTipUp", "TongueTipDown",
    "TongueTipLeft", "TongueTipRight", "TongueRollUp", "TongueRollDown",
    "TongueRollLeft", "TongueRollRight", "TongueUp", "TongueDown", "TongueLeft",
    "TongueRight", "TongueIn", "TongueStretch", "TongueWide", "TongueNarrow",
)

_PROFILES = {
    "v2.3-regression": {
        "id": "v2.3-regression",
        "architecture": "regression",
        "runtime": "nim-2.0-remote",
        "model": "claire-v2.3.1",
        "nim_model_id": "claire_v2.3.1",
        "license": "NVIDIA Open Model License",
        "default_endpoint": "127.0.0.1:52000",
        "client_request_config": "config_claire.yml",
        "client_config_role": "shared-claire-request-header",
    },
    "v3.0-diffusion": {
        "id": "v3.0-diffusion",
        "architecture": "transformer-diffusion",
        # NIM 2.0 is the installed Linux/UE RemoteA2F production path. The
        # public SDK remains the offline fallback for non-UE integrations.
        "runtime": "nim-2.0-remote",
        "offline_fallback_runtime": "a2f-sdk-local-offline",
        "model": "Audio2Face-3D-v3.0",
        "nim_model_id": "multi_v3.2",
        "nim_profile": "f4c212c297315b9ab8462dd5da103f676a9a735a788010439d8171a81e303559",
        "sdk_commit": A2F_SDK_COMMIT,
        "model_revision": A2F_V3_MODEL_REVISION,
        "license": "NVIDIA Open Model License",
        "identities": ["claire", "james", "mark"],
        "default_endpoint": "127.0.0.1:52100",
        "client_request_config": "config_claire.yml",
        "client_config_role": "shared-claire-request-header",
    },
}

DEFAULT_MODEL_ID = "v3.0-diffusion"


def resolve_model_profile(name: str | None) -> dict[str, Any]:
    key = name or DEFAULT_MODEL_ID
    try:
        return dict(_PROFILES[key])
    except KeyError as exc:
        raise ModelProfileError(f"unknown Audio2Face model profile: {key}") from exc


def validate_model_output_cadence(
    model_id: str,
    *,
    frames: int,
    first_timecode: float,
    last_timecode: float,
    output_frames: int,
) -> dict[str, Any]:
    resolve_model_profile(model_id)
    duration = float(last_timecode) - float(first_timecode)
    if frames < 2 or output_frames < 1 or not math.isfinite(duration) or duration <= 0:
        raise ModelProfileError("model output cadence inputs are invalid")
    source_fps = (frames - 1) / duration
    if model_id == "v3.0-diffusion":
        if not 50.0 <= source_fps <= 70.0 or frames < 1.8 * output_frames:
            raise ModelProfileError(
                "v3.0 diffusion output does not have the expected ~60fps cadence; "
                "refusing possible v2 relabel/fallback"
            )
        cadence = "diffusion-approximately-60fps"
    else:
        if not 25.0 <= source_fps <= 35.0 or abs(frames - output_frames) > 2:
            raise ModelProfileError("v2.3 regression output cadence is not 30fps")
        cadence = "regression-30fps"
    return {
        "model_id": model_id,
        "cadence": cadence,
        "frames": int(frames),
        "source_fps": source_fps,
        "output_frames": int(output_frames),
        "resampling_required": frames != output_frames,
    }


def _version_pair(value: str) -> tuple[int, int]:
    pieces = value.strip().split(".")
    try:
        return int(pieces[0]), int(pieces[1])
    except (IndexError, ValueError) as exc:
        raise ModelProfileError(f"invalid version: {value}") from exc


def evaluate_v3_preflight(
    compute_capability: float,
    cuda_version: str,
    tensorrt_version: str,
    model_present: bool,
    sdk_runner_present: bool,
) -> dict[str, Any]:
    reasons = []
    if not math.isfinite(compute_capability) or compute_capability < 6.0:
        reasons.append("GPU compute capability is outside the official model-card range")
    cuda = _version_pair(cuda_version)
    if cuda < (12, 8) or cuda >= (13, 0):
        reasons.append("CUDA must be >=12.8 and <13 for the pinned SDK")
    tensorrt = _version_pair(tensorrt_version)
    if tensorrt < (10, 13) or tensorrt >= (11, 0):
        reasons.append("TensorRT must be >=10.13 and <11 for the pinned SDK")
    if not model_present:
        reasons.append("pinned v3 model artifacts are absent")
    if not sdk_runner_present:
        reasons.append("pinned SDK exporter is absent")
    return {
        "supported": not reasons,
        "reasons": reasons,
        "observed": {
            "compute_capability": compute_capability,
            "cuda_version": cuda_version,
            "tensorrt_version": tensorrt_version,
            "model_present": model_present,
            "sdk_runner_present": sdk_runner_present,
        },
    }


def build_v3_runner_command(
    runner: Path,
    audio: Path,
    model: Path,
    output_dir: Path,
    identity: int,
    emotion_csv: Path | None,
    device: int,
) -> list[str]:
    if identity not in (0, 1, 2) or device < 0:
        raise ModelProfileError("identity must be 0..2 and device must be non-negative")
    command = [
        str(runner), "--architecture", "diffusion", "--audio", str(audio),
        "--model", str(model), "--output-dir", str(output_dir),
        "--identity", str(identity), "--device", str(device),
    ]
    if emotion_csv is not None:
        command.extend(["--emotion-csv", str(emotion_csv)])
    return command


def validate_v3_blendshape_csv(path: Path) -> dict[str, Any]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ModelProfileError("empty blendshape CSV") from exc
        if header != ["frame_index", "time_seconds", *A2F_68_NAMES]:
            raise ModelProfileError("v3 blendshape CSV does not use canonical 68 schema")
        previous = -math.inf
        frames = 0
        for row in reader:
            if len(row) != 70:
                raise ModelProfileError("v3 blendshape row width mismatch")
            try:
                frame = int(row[0])
                timestamp = float(row[1])
                values = [float(value) for value in row[2:]]
            except ValueError as exc:
                raise ModelProfileError("v3 blendshape CSV contains non-numeric data") from exc
            if frame != frames or not math.isfinite(timestamp) or timestamp <= previous:
                if frames == 0 and timestamp == 0.0 and frame == 0:
                    pass
                else:
                    raise ModelProfileError("v3 blendshape frame/time order is invalid")
            if not all(math.isfinite(value) for value in values):
                raise ModelProfileError("v3 blendshape CSV contains non-finite values")
            previous = timestamp
            frames += 1
    if not frames:
        raise ModelProfileError("v3 blendshape CSV contains no frames")
    return {"frames": frames, "curves": 68, "finite": True, "monotonic": True}
