#!/usr/bin/env python3

"""Official-sample-first Audio2Face-3D/MetaHuman production pipeline."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
import re
import shlex
import signal
import shutil
import subprocess
import sys
import time
import yaml
from enum import IntEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from a2f_avatar_shots import (
    ResumeError,
    ShotConfigError,
    apply_manifest_v2,
    resolve_named_shots,
    validate_resume,
    validate_shot_document,
    validate_unreal_asset_reference,
)
from a2f_lineage import (
    LineageError,
    make_lineage,
    showcase_identity,
    validate_compositor_lineage,
)
from a2f_model_registry import (
    DEFAULT_MODEL_ID,
    ModelProfileError,
    resolve_model_profile,
    validate_model_output_cadence,
)
from a2f_mannequin import (
    basis_provenance,
    build_diagnostic_triptych_command,
    build_mannequin_video_command,
    load_nvidia_mannequin_basis,
    render_mannequin_frames,
)
from a2f_motion import (
    BLENDSHAPE_NAMES,
    apply_motion_enhancement,
    build_effective_nim_config,
    compare_motion_series,
    final_render_curve_names,
    parse_animation_csv,
    parse_emotion_csv,
    resample_series,
    resolve_motion_config,
    validate_motion_config,
    write_motion_series,
)
from a2f_motion_viz import (
    build_hstack_command,
    build_visualization_command,
    render_compact_motion_frames,
    render_motion_frames,
)
from a2f_progress import ProgressReporter
from a2f_sync import (
    A2FSyncError,
    build_master_frame_map,
    build_avatar_sync_correction_command,
    capture_timeline_policy,
    verify_avatar_curve_sync,
    verify_recorded_curve_samples,
    write_frame_map_jsonl,
)


SAMPLES_COMMIT = "a2d0150043be7dc15db2fad8193a78b660e1100f"
CANONICAL_COMMAND = "run-a2f-metahuman.py"
DEFAULT_MAP = "/Game/Maps/TaroA2F/TaroFaceBodyDemo_Repaired"
PRIMARY_SOURCE_URLS = {
    "nvidia_audio2face_3d_hub": "https://github.com/NVIDIA/Audio2Face-3D",
    "nvidia_audio2face_3d_sdk": "https://github.com/NVIDIA/Audio2Face-3D-SDK",
    "nvidia_audio2face_3d_v3_model": "https://huggingface.co/nvidia/Audio2Face-3D-v3.0",
    "nvidia_a2f_nim_support_matrix": "https://docs.nvidia.com/ace/audio2face-3d-microservice/latest/text/support-matrix.html",
    "nvidia_a2f_nim_sample": "https://docs.nvidia.com/ace/audio2face-3d-microservice/2.0/text/interacting/sample-app.html",
    "nvidia_a2f_sample_source": f"https://github.com/NVIDIA/Audio2Face-3D-Samples/blob/{SAMPLES_COMMIT}/scripts/audio2face_3d_microservices_interaction_app/a2f_3d.py",
    "nvidia_ace_unreal_a2f": "https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-audio2face.html",
    "nvidia_ace_support_matrix": "https://docs.nvidia.com/ace/ace-unreal-plugin/latest/ace-unreal-plugin-support-matrix.html",
    "nvidia_kairos_sample": "https://docs.nvidia.com/ace/gaming-avatar/latest/gaming-avatar-unreal-sample-project.html",
    "epic_python_automation_5_6": "https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python?application_version=5.6",
    "epic_take_recorder_5_6": "https://dev.epicgames.com/documentation/en-us/unreal-engine/take-recorder-in-unreal-engine?application_version=5.6",
    "epic_mrq_cli_5_6": "https://dev.epicgames.com/documentation/en-us/unreal-engine/using-command-line-rendering-with-move-render-queue-in-unreal-engine?application_version=5.6",
    "epic_mrq_formats_5_6": "https://dev.epicgames.com/documentation/en-us/unreal-engine/cinematic-rendering-export-formats-in-unreal-engine?application_version=5.6",
    "epic_sequencer_python_5_6": "https://dev.epicgames.com/documentation/en-us/unreal-engine/python-scripting-in-sequencer-in-unreal-engine?application_version=5.6",
    "epic_editor_save_map_5_6": "https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorLoadingAndSavingUtils?application_version=5.6",
    "epic_metahuman": "https://dev.epicgames.com/documentation/en-us/metahuman/metahumans-in-unreal-engine",
    "epic_metahuman_fab": "https://dev.epicgames.com/documentation/en-us/metahuman/buying-metahumans-from-fab",
    "epic_metahuman_creator": "https://dev.epicgames.com/documentation/en-us/metahuman/metahuman-creator-in-unreal-engine",
}


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    PREFLIGHT = 10
    NIM_INFERENCE = 20
    MANUAL_EDITOR_CAPTURE_REQUIRED = 42
    MRQ = 43
    MUX_OR_VALIDATION = 44
    AVATAR_IMPORT_REQUIRED = 45
    AVATAR_ACE_SETUP_REQUIRED = 46
    AVATAR_RESOLUTION_ERROR = 47
    SHOT_CONFIG_INVALID = 48
    INTERRUPTED = 130


class PipelineError(RuntimeError):
    def __init__(self, message: str, exit_code: ExitCode, stage: str):
        super().__init__(message)
        self.exit_code = exit_code
        self.stage = stage


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def safe_name(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    if not result:
        raise ValueError("name must contain at least one letter or number")
    return result[:64]


def validate_cli_limits(args: argparse.Namespace) -> None:
    if not 1 <= args.fps <= 240:
        raise ValueError("fps must be in [1, 240]")
    if not 16 <= args.width <= 8192 or not 16 <= args.height <= 8192:
        raise ValueError("width and height must be in [16, 8192]")
    if args.width * args.height > 33_554_432:
        raise ValueError("render resolution exceeds the supported pixel limit")
    if args.expected_frames is not None and not 1 <= args.expected_frames <= 36_000:
        raise ValueError("expected-frames must be in [1, 36000]")
    if not 0 <= args.start_number <= 1_000_000_000:
        raise ValueError("start-number is outside the supported range")
    if not 0 <= args.graphics_adapter <= 31:
        raise ValueError("graphics-adapter must be in [0, 31]")
    if not 1 <= args.capture_timeout <= 3600 or not 1 <= args.mrq_timeout <= 3600:
        raise ValueError("capture and MRQ timeouts must be in [1, 3600]")


def parse_nim_endpoint(endpoint: str) -> tuple[str, int]:
    if not endpoint or any(ord(character) < 32 for character in endpoint):
        raise ValueError("--nim-url contains an empty value or control characters")
    parsed = urlsplit(endpoint if "://" in endpoint else "//" + endpoint)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise ValueError("--nim-url scheme must be http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("--nim-url must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("--nim-url must be an authority without a path")
    try:
        host, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise ValueError("--nim-url has an invalid port") from exc
    if not host or port is None or not 1 <= port <= 65535:
        raise ValueError("--nim-url requires a host and port")
    return host, port


def is_loopback_nim_endpoint(endpoint: str) -> bool:
    try:
        host, _ = parse_nim_endpoint(endpoint)
    except ValueError:
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_nim_endpoint(model_name: str, requested: str | None) -> str:
    """Keep the legacy endpoint stable and isolate diffusion side-by-side."""
    profile = resolve_model_profile(model_name)
    if requested:
        return requested
    return str(profile["default_endpoint"])


def _resume_model_id(manifest: dict[str, Any]) -> str:
    model = manifest.get("a2f_model")
    if isinstance(model, dict):
        model = model.get("id")
    if not isinstance(model, str):
        inference = manifest.get("official_nvidia_inference") or {}
        profile = inference.get("model_profile") or {}
        model = profile.get("id")
    if not isinstance(model, str):
        raise ResumeError("resume manifest has no model identity")
    resolve_model_profile(model)
    return model


def _resume_endpoint(manifest: dict[str, Any], model_id: str) -> str:
    endpoint = manifest.get("nim_endpoint")
    if isinstance(endpoint, dict):
        endpoint = endpoint.get("url")
    if endpoint is None:
        endpoint = resolve_model_profile(model_id)["default_endpoint"]
    if not isinstance(endpoint, str):
        raise ResumeError("resume manifest has no valid NIM endpoint")
    validate_model_endpoint_binding(model_id, endpoint)
    return endpoint


def resolve_resume_model_selection(
    manifest: dict[str, Any],
    *,
    requested_model: str,
    requested_endpoint: str | None,
    model_was_explicit: bool,
) -> dict[str, str]:
    source_model = _resume_model_id(manifest)
    source_endpoint = _resume_endpoint(manifest, source_model)
    if model_was_explicit and requested_model != source_model:
        raise ResumeError(
            "resume model mismatch; omit --resume to run a new cross-model inference"
        )
    if requested_endpoint is not None and requested_endpoint != source_endpoint:
        raise ResumeError(
            "resume endpoint mismatch; reused inference must keep its source endpoint"
        )
    return {
        "model_id": source_model if not model_was_explicit else requested_model,
        "endpoint": source_endpoint,
        "selection_source": "resume-manifest",
    }


def model_service_failure_hint(model_id: str) -> str:
    if model_id == "v3.0-diffusion":
        return (
            "v3 diffusion service is required; run "
            "scripts/audio2face-metahuman/start-a2f-v3-diffusion.sh; "
            "no automatic v2 fallback is performed"
        )
    return "verify the explicit v2.3 service on 127.0.0.1:52000"


KNOWN_LOCAL_RUNTIMES = {
    52000: {
        "model": "v2.3-regression",
        "container": "audio2face-3d-pretrained",
    },
    52100: {
        "model": "v3.0-diffusion",
        "container": "audio2face-3d-diffusion",
    },
}


def classify_endpoint_attestation(
    model_name: str, endpoint: str
) -> dict[str, Any]:
    resolve_model_profile(model_name)
    host, port = parse_nim_endpoint(endpoint)
    loopback = host.casefold() == "localhost"
    if not loopback:
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
    known = KNOWN_LOCAL_RUNTIMES.get(port) if loopback else None
    if known and known["model"] == model_name:
        return {
            "status": "bound-local-runtime",
            "requested_model": model_name,
            "endpoint": endpoint,
            "container": known["container"],
        }
    return {
        "status": (
            "unattested-custom-endpoint" if loopback else "unattested-remote-endpoint"
        ),
        "requested_model": model_name,
        "endpoint": endpoint,
        "container": None,
    }


def validate_model_endpoint_binding(model_name: str, endpoint: str) -> None:
    _, port = parse_nim_endpoint(endpoint)
    if not is_loopback_nim_endpoint(endpoint):
        return
    known = KNOWN_LOCAL_RUNTIMES.get(port)
    if known and known["model"] != model_name:
        raise ValueError(
            f"--a2f-model {model_name} conflicts with the attested local "
            f"{known['model']} service on port {port}"
        )


def validate_mrq_output_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("MRQ frames directory must not be a symlink")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("MRQ frames directory must be absent or empty")


def build_resume_command(
    *,
    script: Path,
    input_path: Path,
    avatar: str,
    resume: Path,
    config: Path,
    map_path: str,
    shots: list[str],
    shot_config: Path | None,
    a2f_model: str = "v2.3-regression",
    nim_url: str | None = None,
    motion_config: Path | None = None,
    avatar_visual_profile: str = "source",
) -> str:
    argv = [
        str(script),
        str(input_path),
        "--avatar",
        avatar,
        "--resume",
        str(resume),
        "--config",
        str(config),
        "--map",
        map_path,
        "--a2f-model",
        a2f_model,
    ]
    if avatar_visual_profile != "source":
        argv.extend(["--avatar-visual-profile", avatar_visual_profile])
    if nim_url is not None:
        argv.extend(["--nim-url", nim_url])
    if motion_config is not None:
        argv.extend(["--motion-config", str(motion_config)])
    if shot_config is not None:
        argv.extend(["--shot-config", str(shot_config)])
    else:
        for shot in shots:
            argv.extend(["--shot", shot])
    return shlex.join(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_resumed_inference(inference: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(str(inference.get("output_dir", ""))).expanduser().resolve()
    files = inference.get("files")
    required = (
        "animation_frames.csv",
        "a2f_3d_input_emotions.csv",
        "a2f_3d_smoothed_emotion_output.csv",
        "out.wav",
    )
    if not isinstance(files, dict):
        raise ResumeError("resume inference has no file integrity records")
    for name in required:
        path = output_dir / name
        record = files.get(name)
        if (
            not path.is_file()
            or not isinstance(record, dict)
            or record.get("sha256") != sha256_file(path)
            or record.get("size_bytes") != path.stat().st_size
        ):
            raise ResumeError(f"resume inference file failed integrity check: {name}")
    return dict(inference)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_motion_config(
    path: Path | None, audio_duration: float, *, model_id: str
) -> dict[str, Any]:
    if path is None:
        config = resolve_motion_config()
        if model_id == "v3.0-diffusion":
            # Keep native v3 intensity-neutral while identity-baking the exact
            # official curves for strict avatar/panel/mannequin lineage.
            config["curve_application"] = "final_render"
        return config
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.stat().st_size > 1024 * 1024:
        raise PipelineError(
            "motion config must be a file no larger than 1 MiB",
            ExitCode.PREFLIGHT,
            "motion_config",
        )
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(
            f"invalid motion config: {exc}", ExitCode.PREFLIGHT, "motion_config"
        ) from exc
    return validate_motion_config(document, audio_duration=audio_duration)


def uses_ace_node_overrides(motion_config: dict[str, Any]) -> bool:
    """Return whether official ApplyACEAnimation node maps must be configured."""
    runtime = motion_config.get("nvidia_runtime_curve_parameters") or {}
    return bool(runtime.get("multipliers") or runtime.get("offsets"))


def curve_source_identity_for_motion_config(
    motion_config: dict[str, Any],
) -> str:
    if motion_config["curve_application"] == "final_render":
        return "effective-final-render"
    if uses_ace_node_overrides(motion_config):
        return "ace-node-overrides"
    return "raw-ace-reinference"


def requires_content_sync(motion_config: dict[str, Any]) -> bool:
    return curve_source_identity_for_motion_config(motion_config) in {
        "effective-final-render",
        "ace-node-overrides",
    }


def validate_ace_node_override_capture(
    motion_config: dict[str, Any], capture_status: dict[str, Any]
) -> dict[str, Any]:
    """Prove that the run-owned PIE AnimBP consumed the requested ACE maps."""
    if not uses_ace_node_overrides(motion_config):
        raise PipelineError(
            "motion config has no ACE node overrides",
            ExitCode.MUX_OR_VALIDATION,
            "ace_node_override_lineage",
        )
    expected = motion_config["nvidia_runtime_curve_parameters"]
    actual = capture_status.get("ace_runtime_curve_parameters")
    nodes = capture_status.get("ace_blendshape_override_nodes")
    if not isinstance(nodes, int) or isinstance(nodes, bool) or nodes < 1:
        raise PipelineError(
            "capture did not configure an Apply ACE Face Animations node",
            ExitCode.MUX_OR_VALIDATION,
            "ace_node_override_lineage",
        )
    if actual != expected:
        raise PipelineError(
            "captured Apply ACE Face Animations node maps differ from motion config",
            ExitCode.MUX_OR_VALIDATION,
            "ace_node_override_lineage",
        )
    canonical = json.dumps(
        expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "valid": True,
        "configured_node_count": nodes,
        "runtime_curve_parameters_sha256": hashlib.sha256(canonical).hexdigest(),
        "ue_node": "FAnimNode_ApplyACEAnimation",
        "application_scope": "run-owned PIE avatar AnimInstance",
    }


def write_effective_request_config(
    base_path: Path,
    motion_config: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    try:
        base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(
            f"invalid NVIDIA request config: {exc}",
            ExitCode.PREFLIGHT,
            "request_config",
        ) from exc
    if not isinstance(base, dict):
        raise PipelineError(
            "NVIDIA request config must be a mapping",
            ExitCode.PREFLIGHT,
            "request_config",
        )
    # Face/emotion fields are official WAV request parameters. Per-curve runtime
    # maps are also written to the official client request; the UE capture helper
    # mirrors the same maps onto FAnimNode_ApplyACEAnimation. Artifact
    # attack/release and region/curve postprocessing stay separate.
    effective = build_effective_nim_config(
        base, motion_config, include_artifact_postprocess=False
    )
    source_text = base_path.read_text(encoding="utf-8")
    output_path.write_text(
        source_text
        if effective == base
        else yaml.safe_dump(effective, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return {
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "base_path": str(base_path),
        "base_sha256": sha256_file(base_path),
        "runtime_fields": [
            "face_parameters",
            "emotion",
            "nvidia_runtime_curve_parameters",
        ],
        "artifact_only_fields": [
            "artifact_postprocess.attack",
            "artifact_postprocess.release",
            "artifact_postprocess.region_gains",
            "artifact_postprocess.curve_operations",
        ],
    }


def verify_visualization_video(
    ffmpeg: Path,
    ffprobe: Path,
    path: Path,
    expected_frames: int,
    fps: int,
    log_path: Path,
) -> dict[str, Any]:
    probe = capture_json(
        [
            str(ffprobe), "-v", "error", "-count_frames",
            "-show_entries", "stream=codec_type,codec_name,nb_read_frames,r_frame_rate,width,height,duration",
            "-of", "json", str(path),
        ],
        stage="motion_visualization_probe",
    )
    videos = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"]
    frame_rate = videos[0].get("r_frame_rate", "0/1") if videos else "0/1"
    numerator, denominator = (int(value) for value in frame_rate.split("/", 1))
    actual_fps = numerator / denominator if denominator else 0.0
    if (
        len(videos) != 1
        or int(videos[0].get("nb_read_frames") or 0) != expected_frames
        or abs(actual_fps - fps) > 1e-6
        or videos[0].get("codec_name") != "h264"
    ):
        raise PipelineError(
            "motion visualization frame count mismatch",
            ExitCode.MUX_OR_VALIDATION,
            "motion_visualization_probe",
        )
    run_logged(
        [str(ffmpeg), "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
        log_path,
        exit_code=ExitCode.MUX_OR_VALIDATION,
        stage="motion_visualization_decode",
    )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "codec": videos[0].get("codec_name"),
        "width": int(videos[0].get("width") or 0),
        "height": int(videos[0].get("height") or 0),
        "fps": fps,
        "frame_count": expected_frames,
        "decode_pass": True,
        "audio": False,
    }


def verify_comparison_video(
    ffmpeg: Path,
    ffprobe: Path,
    path: Path,
    expected_frames: int,
    fps: int,
    log_path: Path,
) -> dict[str, Any]:
    probe = capture_json(
        [
            str(ffprobe), "-v", "error", "-count_frames",
            "-show_entries",
            "stream=codec_type,codec_name,nb_read_frames,r_frame_rate,width,height,duration,start_time,sample_rate,channels",
            "-of", "json", str(path),
        ],
        stage="motion_comparison_probe",
    )
    videos = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"]
    audios = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
    if (
        len(videos) != 1
        or len(audios) != 1
        or int(videos[0].get("nb_read_frames") or 0) != expected_frames
        or videos[0].get("codec_name") != "h264"
        or audios[0].get("codec_name") != "aac"
    ):
        raise PipelineError(
            "blendshape comparison requires one video, one audio, and exact frames",
            ExitCode.MUX_OR_VALIDATION,
            "motion_comparison_probe",
        )
    run_logged(
        [
            str(ffmpeg), "-v", "error", "-i", str(path),
            "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-",
        ],
        log_path,
        exit_code=ExitCode.MUX_OR_VALIDATION,
        stage="motion_comparison_decode",
    )
    start_delta_ms = 1000.0 * abs(
        float(videos[0].get("start_time") or 0.0)
        - float(audios[0].get("start_time") or 0.0)
    )
    frame_rate = videos[0].get("r_frame_rate", "0/1")
    numerator, denominator = (int(value) for value in frame_rate.split("/", 1))
    actual_fps = numerator / denominator if denominator else 0.0
    if abs(actual_fps - fps) > 1e-6 or start_delta_ms > (1000.0 / fps):
        raise PipelineError(
            "blendshape comparison fps or A/V start alignment mismatch",
            ExitCode.MUX_OR_VALIDATION,
            "motion_comparison_probe",
        )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "video_codec": videos[0].get("codec_name"),
        "audio_codec": audios[0].get("codec_name"),
        "width": int(videos[0].get("width") or 0),
        "height": int(videos[0].get("height") or 0),
        "fps": fps,
        "frame_count": expected_frames,
        "audio_sample_rate": int(audios[0].get("sample_rate") or 0),
        "audio_channels": int(audios[0].get("channels") or 0),
        "av_start_delta_ms": round(start_delta_ms, 3),
        "decode_pass": True,
    }


def export_motion_artifacts(
    *,
    official_output: Path,
    output_dir: Path,
    motion_config: dict[str, Any],
    ffmpeg: Path,
    ffprobe: Path,
    fps: int,
    expected_frames: int,
    mannequin_skin_path: Path,
    mannequin_tongue_path: Path,
    mannequin_topology_path: Path,
    panel_identity: dict[str, str],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = parse_animation_csv(
        official_output / "animation_frames.csv", source_name="nvidia-nim-solver-output"
    )
    emotion_input = parse_emotion_csv(
        official_output / "a2f_3d_input_emotions.csv", source_name="nvidia-request-emotion"
    )
    emotion_smoothed = parse_emotion_csv(
        official_output / "a2f_3d_smoothed_emotion_output.csv",
        source_name="nvidia-a2e-smoothed",
        timebase_hz=16000.0,
    )
    effective = apply_motion_enhancement(raw, motion_config)
    records = {
        "blendshapes_raw": write_motion_series(
            raw, output_dir / "blendshapes.raw.json", output_dir / "blendshapes.raw.csv"
        ),
        "blendshapes_effective": write_motion_series(
            effective,
            output_dir / "blendshapes.effective.json",
            output_dir / "blendshapes.effective.csv",
        ),
        "emotion_input": write_motion_series(
            emotion_input,
            output_dir / "emotion.input.json",
            output_dir / "emotion.input.csv",
        ),
        "emotion_smoothed": write_motion_series(
            emotion_smoothed,
            output_dir / "emotion.smoothed.json",
            output_dir / "emotion.smoothed.csv",
        ),
    }
    metrics = compare_motion_series(raw, effective)
    atomic_write_json(output_dir / "motion-comparison-metrics.json", metrics)
    atomic_write_json(output_dir / "effective-motion-config.json", motion_config)
    visual_raw = resample_series(raw, fps=fps, frame_count=expected_frames)
    visual_effective = resample_series(
        effective, fps=fps, frame_count=expected_frames
    )
    visual_emotions = resample_series(
        emotion_smoothed, fps=fps, frame_count=expected_frames
    )
    frame_paths = render_motion_frames(
        visual_raw,
        visual_effective,
        visual_emotions,
        output_dir / "visualization-frames",
        width=960,
        height=1080,
        top_k=12,
    )
    visualization = output_dir / "blendshape-visualization.mp4"
    run_logged(
        build_visualization_command(
            ffmpeg, output_dir / "visualization-frames", visualization, fps, len(frame_paths)
        ),
        output_dir / "ffmpeg-visualization.log",
        exit_code=ExitCode.MUX_OR_VALIDATION,
        stage="motion_visualization",
    )
    visualization_record = verify_visualization_video(
        ffmpeg, ffprobe, visualization, len(frame_paths), fps,
        output_dir / "ffmpeg-visualization-decode.log",
    )
    compact_frame_paths = render_compact_motion_frames(
        visual_raw,
        visual_effective,
        visual_emotions,
        output_dir / "readable-panel-frames",
        width=640,
        height=540,
        top_k=8,
        panel_identity=panel_identity,
        active_curve_names=(
            list(final_render_curve_names(motion_config))
            if (
                motion_config["curve_application"] == "final_render"
                or uses_ace_node_overrides(motion_config)
            )
            else None
        ),
    )
    readable_panel = output_dir / (
        f"readable-motion-panel-{panel_identity['filename_suffix']}.mp4"
    )
    run_logged(
        build_visualization_command(
            ffmpeg,
            output_dir / "readable-panel-frames",
            readable_panel,
            fps,
            len(compact_frame_paths),
        ),
        output_dir / "ffmpeg-readable-panel.log",
        exit_code=ExitCode.MUX_OR_VALIDATION,
        stage="readable_motion_panel",
    )
    readable_panel_record = verify_visualization_video(
        ffmpeg,
        ffprobe,
        readable_panel,
        len(compact_frame_paths),
        fps,
        output_dir / "ffmpeg-readable-panel-decode.log",
    )
    readable_panel_record.update(
        {
            "layout": "triptych-compact-v3",
            "minimum_font_px": 16,
            "displayed_curve_count": 8,
            "displayed_emotion_count": 0,
            "sort": "current_effective_value_descending",
            "panel_title": panel_identity["panel_title"],
            "panel_model": panel_identity["panel_model"],
            "panel_source": panel_identity["panel_source"],
            "top_curve_scope": (
                "ACE2.5-consumed-52"
                if (
                    motion_config["curve_application"] == "final_render"
                    or uses_ace_node_overrides(motion_config)
                )
                else "all-A2F-68"
            ),
        }
    )
    basis = load_nvidia_mannequin_basis(
        mannequin_skin_path,
        mannequin_tongue_path,
        topology_path=mannequin_topology_path,
    )
    mannequin_root = output_dir / "mannequin"
    mannequin_records = {}
    for source_label, series in (
        ("raw", visual_raw),
        ("effective", visual_effective),
    ):
        frames_dir = mannequin_root / f"{source_label}-frames"
        frame_record = render_mannequin_frames(
            series,
            basis,
            frames_dir,
            width=640,
            height=540,
            source_label=source_label,
        )
        frame_manifest = mannequin_root / f"{source_label}-frames.json"
        atomic_write_json(frame_manifest, frame_record)
        video_path = mannequin_root / f"mannequin.{source_label}.mp4"
        run_logged(
            build_mannequin_video_command(
                ffmpeg=ffmpeg,
                frames_dir=frames_dir,
                output=video_path,
                fps=fps,
                frame_count=expected_frames,
            ),
            mannequin_root / f"ffmpeg-mannequin-{source_label}.log",
            exit_code=ExitCode.MUX_OR_VALIDATION,
            stage="mannequin_visualization",
        )
        video_record = verify_visualization_video(
            ffmpeg,
            ffprobe,
            video_path,
            expected_frames,
            fps,
            mannequin_root / f"ffmpeg-mannequin-{source_label}-decode.log",
        )
        sample_indices = sorted({0, expected_frames // 2, expected_frames - 1})
        mannequin_records[source_label] = {
            "video": video_record,
            "frames": {
                "path": str(frame_manifest),
                "sha256": sha256_file(frame_manifest),
                "count": expected_frames,
                "sample_geometry_sha256": [
                    frame_record["frames"][index]["geometry_sha256"]
                    for index in sample_indices
                ],
                "sample_frame_sha256": [
                    frame_record["frames"][index]["sha256"]
                    for index in sample_indices
                ],
            },
        }
    selected_mannequin = (
        "effective"
        if motion_config["curve_application"] == "final_render"
        else "raw"
    )
    result = {
        "schema_version": 1,
        "curve_schema": "NVIDIA-A2F-68",
        "emotion_schema": "NVIDIA-A2E-10",
        "raw_provenance": "official NVIDIA NIM solver output after request-time face/emotion parameters",
        "effective_provenance": "deterministic local artifact postprocess; original raw values retained",
        "records": records,
        "metrics": {
            "path": str(output_dir / "motion-comparison-metrics.json"),
            "sha256": sha256_file(output_dir / "motion-comparison-metrics.json"),
        },
        "effective_config": {
            "path": str(output_dir / "effective-motion-config.json"),
            "sha256": sha256_file(output_dir / "effective-motion-config.json"),
        },
        "visualization": visualization_record,
        "readable_panel": readable_panel_record,
        "showcase_identity": panel_identity,
        "visualization_resampling": visual_raw["resampling"],
        "mannequin": {
            "schema_version": 1,
            "basis": basis_provenance(basis),
            "raw": mannequin_records["raw"],
            "effective": mannequin_records["effective"],
            "selected_for_avatar_comparison": selected_mannequin,
            "semantic_boundary": (
                "NVIDIA Claire official blendshape basis driven by the actual "
                "A2F-68 artifact; not the selected avatar mesh or a recolored render"
            ),
        },
    }
    atomic_write_json(output_dir / "artifact-manifest.json", result)
    result["artifact_manifest"] = {
        "path": str(output_dir / "artifact-manifest.json"),
        "sha256": sha256_file(output_dir / "artifact-manifest.json"),
    }
    return result


def run_logged(
    command: list[str],
    log_path: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    exit_code: ExitCode,
    stage: str,
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise PipelineError(
            f"command failed with exit {completed.returncode}; see {log_path}",
            exit_code,
            stage,
        )
    return completed.stdout


def capture_json(command: list[str], *, stage: str) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PipelineError(
            completed.stderr.strip(), ExitCode.MUX_OR_VALIDATION, stage
        )
    return json.loads(completed.stdout)


def build_inference_command(
    *, python: Path, client: Path, audio: Path, config: Path, url: str
) -> list[str]:
    return [
        str(python),
        str(client),
        "run_inference",
        str(audio),
        str(config),
        "-u",
        url,
    ]


def build_mrq_command(
    *,
    editor_cmd: Path,
    project: Path,
    map_path: str,
    sequence: str,
    log: Path,
    graphics_adapter: int,
) -> list[str]:
    validate_unreal_asset_reference(map_path)
    validate_unreal_asset_reference(sequence)
    return [
        str(editor_cmd),
        str(project),
        map_path,
        "-game",
        f"-LevelSequence={sequence}",
        "-MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelinePythonHostExecutor",
        "-ExecutorPythonClass=/Engine/PythonTypes.A2FMetaHumanMoviePipelineExecutor",
        "-vulkan",
        "-RenderOffscreen",
        "-Unattended",
        "-NoSplash",
        "-NoP4",
        "-notexturestreaming",
        f"-graphicsadapter={graphics_adapter}",
        f"-abslog={log}",
    ]


def build_capture_command(
    *,
    editor: Path,
    project: Path,
    map_path: str,
    log: Path,
    graphics_adapter: int,
    inference_mode: str = "low-latency",
) -> list[str]:
    validate_unreal_asset_reference(map_path)
    return [
        str(editor),
        str(project),
        map_path,
        "-vulkan",
        "-RenderOffscreen",
        "-Multiprocess",
        "-Unattended",
        "-TAKERECORDERISHEADLESS",
        "-NoSplash",
        "-NoP4",
        f"-graphicsadapter={graphics_adapter}",
        f"-A2FDemoMode={inference_mode}",
        f"-abslog={log}",
        "-ExecCmds=r.CEFGPUAcceleration 0",
    ]


def vnc_session_environment() -> dict[str, str]:
    allowed_names = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "DISPLAY",
        "XAUTHORITY",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_DIRS",
        "DBUS_SESSION_BUS_ADDRESS",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "NVIDIA_DRIVER_CAPABILITIES",
        "VK_ICD_FILENAMES",
        "VK_LAYER_PATH",
        "__GLX_VENDOR_LIBRARY_NAME",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in allowed_names or key.startswith("LC_")
    }
    for process_name in ("xfce4-session", "xfce4-panel"):
        found = subprocess.run(
            ["pgrep", "-n", process_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if found.returncode != 0 or not found.stdout.strip():
            continue
        environ_path = Path("/proc") / found.stdout.strip() / "environ"
        try:
            values = environ_path.read_bytes().split(b"\0")
        except OSError:
            continue
        for item in values:
            if b"=" not in item:
                continue
            key, value = item.split(b"=", 1)
            key_text = key.decode("utf-8", errors="ignore")
            if key_text in {
                "DISPLAY",
                "XAUTHORITY",
                "XDG_RUNTIME_DIR",
                "DBUS_SESSION_BUS_ADDRESS",
            }:
                environment[key_text] = value.decode("utf-8", errors="ignore")
        break
    environment.setdefault("DISPLAY", ":1")
    environment.setdefault("XAUTHORITY", "/home/aim/.Xauthority")
    environment.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    environment["SDL_VIDEODRIVER"] = "x11"
    environment["SDL_AUDIODRIVER"] = "pulseaudio"
    environment.setdefault(
        "PULSE_SERVER",
        f"unix:{environment['XDG_RUNTIME_DIR']}/pulse/native",
    )
    return environment


def run_capture_process(
    *,
    command: list[str],
    environment: dict[str, str],
    config_path: Path,
    status_path: Path,
    console_log: Path,
    timeout_seconds: int,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    env = dict(environment)
    env["A2F_METAHUMAN_CAPTURE_CONFIG"] = str(config_path)
    with console_log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
    deadline = time.monotonic() + timeout_seconds
    last_status_stage = None
    try:
        while time.monotonic() < deadline:
            if status_path.is_file():
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    status = {}
                status_stage = status.get("stage")
                if progress is not None and status_stage != last_status_stage:
                    last_status_stage = status_stage
                    if status_stage:
                        progress.update(detail=str(status_stage))
                if status.get("status") == "success":
                    return status
                if status.get("status") == "manual_action_required":
                    stage = str(status.get("stage", "avatar_import_required"))
                    code = (
                        ExitCode.AVATAR_IMPORT_REQUIRED
                        if stage == "avatar_import_required"
                        else ExitCode.AVATAR_ACE_SETUP_REQUIRED
                    )
                    raise PipelineError(
                        status.get("error", "MetaHuman manual setup is required"),
                        code,
                        stage,
                    )
                if status.get("status") == "failure":
                    stage = str(status.get("stage", "capture"))
                    raise PipelineError(
                        status.get("error", "Take Recorder capture failed"),
                        (
                            ExitCode.AVATAR_RESOLUTION_ERROR
                            if stage.startswith("avatar")
                            else ExitCode.MANUAL_EDITOR_CAPTURE_REQUIRED
                        ),
                        stage,
                    )
            result = process.poll()
            if result is not None:
                raise PipelineError(
                    f"capture UnrealEditor exited early with {result}; see {console_log}",
                    ExitCode.MANUAL_EDITOR_CAPTURE_REQUIRED,
                    "capture",
                )
            if progress is not None:
                progress.update(detail=str(last_status_stage or "starting Unreal"))
            time.sleep(1)
        raise PipelineError(
            f"capture timed out after {timeout_seconds}s",
            ExitCode.MANUAL_EDITOR_CAPTURE_REQUIRED,
            "capture",
        )
    finally:
        stop_process_group(process)


def process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    proc_root = Path("/proc")
    readable_member = False
    for stat_path in proc_root.glob("[0-9]*/stat"):
        try:
            fields = stat_path.read_text(encoding="utf-8").rsplit(") ", 1)[1].split()
            state, member_pgid = fields[0], int(fields[2])
        except (OSError, IndexError, ValueError):
            continue
        if member_pgid == pgid:
            readable_member = True
            if state != "Z":
                return True
    return not readable_member


def stop_process_group(
    process: subprocess.Popen[Any], *, grace_seconds: float = 20.0
) -> None:
    pgid = process.pid
    if process_group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace_seconds
        while process_group_exists(pgid) and time.monotonic() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        if process_group_exists(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if process.poll() is None:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.wait()


def run_mrq_process(
    *,
    command: list[str],
    environment: dict[str, str],
    config_path: Path,
    console_log: Path,
    timeout_seconds: int,
    frames_dir: Path | None = None,
    expected_frames: int | None = None,
    progress: ProgressReporter | None = None,
) -> None:
    env = dict(environment)
    env["A2F_METAHUMAN_MRQ_CONFIG"] = str(config_path)
    console_log.parent.mkdir(parents=True, exist_ok=True)
    with console_log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
    deadline = time.monotonic() + timeout_seconds
    result = None
    try:
        while time.monotonic() < deadline:
            result = process.poll()
            current_frames = None
            if frames_dir is not None and frames_dir.is_dir():
                current_frames = sum(1 for _ in frames_dir.glob("frame.*.png"))
            if progress is not None:
                progress.update(
                    current=current_frames,
                    total=expected_frames,
                    detail=(
                        f"frame {current_frames}/{expected_frames}"
                        if current_frames is not None and expected_frames
                        else "rendering"
                    ),
                )
            if result is not None:
                break
            time.sleep(0.5)
        if result is None:
            raise PipelineError(
                f"MRQ timed out after {timeout_seconds}s",
                ExitCode.MRQ,
                "official_mrq_executor",
            )
    finally:
        stop_process_group(process)
    if result != 0:
        raise PipelineError(
            f"MRQ exited with {result}; see {console_log}",
            ExitCode.MRQ,
            "official_mrq_executor",
        )


def validate_animation_csv(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "timeCode" not in reader.fieldnames:
            raise PipelineError(
                "official animation CSV has no timeCode column",
                ExitCode.NIM_INFERENCE,
                "official_output_validation",
            )
        weights = [name for name in reader.fieldnames if name.startswith("blendShapes.")]
        if not weights:
            raise PipelineError(
                "official animation CSV has no blendshape columns",
                ExitCode.NIM_INFERENCE,
                "official_output_validation",
            )
        rows = list(reader)
    if not rows:
        raise PipelineError(
            "official animation CSV is empty",
            ExitCode.NIM_INFERENCE,
            "official_output_validation",
        )
    times: list[float] = []
    minima = {name: math.inf for name in weights}
    maxima = {name: -math.inf for name in weights}
    for row in rows:
        timestamp = float(row["timeCode"])
        if not math.isfinite(timestamp):
            raise PipelineError(
                "non-finite animation timestamp",
                ExitCode.NIM_INFERENCE,
                "official_output_validation",
            )
        times.append(timestamp)
        for name in weights:
            value = float(row[name])
            if not math.isfinite(value):
                raise PipelineError(
                    f"non-finite blendshape value in {name}",
                    ExitCode.NIM_INFERENCE,
                    "official_output_validation",
                )
            minima[name] = min(minima[name], value)
            maxima[name] = max(maxima[name], value)
    if any(current < previous for previous, current in zip(times, times[1:])):
        raise PipelineError(
            "animation timeCode is not monotonic",
            ExitCode.NIM_INFERENCE,
            "official_output_validation",
        )
    maximum_delta = max(maxima[name] - minima[name] for name in weights)
    if maximum_delta <= 1e-6:
        raise PipelineError(
            "all official blendshape columns are static",
            ExitCode.NIM_INFERENCE,
            "official_output_validation",
        )
    return {
        "frames": len(rows),
        "blendshape_columns": len(weights),
        "first_timecode": times[0],
        "last_timecode": times[-1],
        "monotonic_timecode": True,
        "finite_values": True,
        "max_weight_delta": maximum_delta,
    }


def probe_audio(ffprobe: Path, audio: Path) -> dict[str, Any]:
    data = capture_json(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,sample_rate,channels,bits_per_sample,duration",
            "-of",
            "json",
            str(audio),
        ],
        stage="audio_probe",
    )
    streams = [item for item in data.get("streams", []) if item.get("codec_type") == "audio"]
    if not streams:
        raise PipelineError("no audio stream", ExitCode.PREFLIGHT, "audio_probe")
    stream = streams[0]
    duration = float(data.get("format", {}).get("duration") or stream.get("duration") or 0)
    if duration <= 0:
        raise PipelineError("zero-duration audio", ExitCode.PREFLIGHT, "audio_probe")
    return {
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "bits_per_sample": int(stream.get("bits_per_sample") or 0),
        "duration_seconds": duration,
        "size_bytes": int(data.get("format", {}).get("size") or audio.stat().st_size),
    }


def collect_versions(root: Path, config: Path) -> dict[str, Any]:
    samples = root / ".tools/audio2face3d/Audio2Face-3D-Samples"
    ace_descriptor = root / ".tools/audio2face-metahuman/ACEPlugin/NV_ACE_Reference/NV_ACE_Reference.uplugin"
    ue_descriptor = root / ".tools/audio2face-metahuman/UE_5.6/Engine/Build/Build.version"
    taro_version = root / ".tools/audio2face-metahuman/KairosSample/Content/MetaHumans/Taro/VersionInfo.txt"
    ace = json.loads(ace_descriptor.read_text(encoding="utf-8"))
    ue = json.loads(ue_descriptor.read_text(encoding="utf-8"))
    taro = json.loads(taro_version.read_text(encoding="utf-8"))
    git_commit = subprocess.run(
        ["git", "-C", str(samples), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    ).stdout.strip()
    image = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "nvcr.io/nim/nvidia/audio2face-3d:2.0",
            "--format",
            "{{index .RepoDigests 0}}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    ).stdout.strip()
    return {
        "audio2face_3d_nim": "2.0",
        "audio2face_3d_nim_image": image,
        "audio2face_3d_samples_tag": "v2.0",
        "audio2face_3d_samples_commit": git_commit,
        "nvidia_ace_unreal_plugin": ace["VersionName"],
        "unreal_engine": f"{ue['MajorVersion']}.{ue['MinorVersion']}.{ue['PatchVersion']}",
        "unreal_changelist": ue["Changelist"],
        "metahuman_taro": taro["MetaHumanVersion"],
        "official_claire_config_sha256": sha256_file(config),
    }


def collect_a2f_runtime_evidence(
    root: Path, model_name: str, endpoint: str
) -> dict[str, Any]:
    attestation = classify_endpoint_attestation(model_name, endpoint)
    if attestation["status"] != "bound-local-runtime":
        return {
            "schema_version": 2,
            "attestation": attestation,
            "container": None,
            "container_status": "not-inspected",
            "endpoint": endpoint,
            "details": {
                "requested_model": model_name,
                "observed_runtime": "unattested",
                "reason": (
                    "custom/remote endpoint protocol output does not attest the "
                    "served model; local engine hashes are intentionally omitted"
                ),
            },
            "artifacts": [],
        }
    if model_name == "v3.0-diffusion":
        container = "audio2face-3d-diffusion"
        artifact_paths = [
            root / ".tools/audio2face3d/v3/nim-custom-engines/multi_v3.2.trt",
            root / ".tools/audio2face3d/v3/nim-custom-engines/a2e.trt",
            root / ".tools/audio2face3d/v3/nim-custom-configs/diffusion-claire-single-stream.yaml",
            root / ".tools/audio2face3d/v3/nim-custom-configs/deployment-single-stream.yaml",
            root / ".tools/audio2face3d/v3/models/Audio2Face-3D-v3.0-b741327/network.onnx",
        ]
        details = {
            "inference_type": "diffusion",
            "model_id": "multi_v3.2",
            "identity": "claire",
            "constant_noise": True,
            "a2f_engine": "NGC A10G FP16 bs38 v5",
            "a2e_engine": "official NIM ONNX rebuilt for one stream on RTX A4500",
        }
    else:
        container = "audio2face-3d-pretrained"
        artifact_paths = [
            root / ".tools/audio2face3d/nim-cache/claire_v2.3.1.trt",
            root / ".tools/audio2face3d/nim-cache/a2e.trt",
            root / ".tools/audio2face3d/nim-configs/claire_stylization_config.yaml",
        ]
        details = {
            "inference_type": "regression",
            "model_id": "claire_v2.3.1",
            "identity": "claire",
        }
    status = subprocess.run(
        ["docker", "inspect", container, "--format", "{{.State.Status}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    ).stdout.strip()
    return {
        "schema_version": 2,
        "attestation": attestation,
        "container": container,
        "container_status": status or "not-found",
        "endpoint": endpoint,
        "details": details,
        "artifacts": [
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in artifact_paths
            if path.is_file()
        ],
    }


def frame_inventory(
    frames_dir: Path, pattern: str, expected: int, start_number: int
) -> dict[str, Any]:
    if "%04d" not in pattern:
        raise PipelineError(
            "frame pattern must contain %04d",
            ExitCode.MUX_OR_VALIDATION,
            "frames",
        )
    prefix, suffix = pattern.split("%04d", 1)
    regex = re.compile(rf"^{re.escape(prefix)}(\d{{4}}){re.escape(suffix)}$")
    found = []
    for path in frames_dir.iterdir() if frames_dir.is_dir() else []:
        match = regex.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    found.sort()
    numbers = [number for number, _ in found]
    expected_numbers = list(range(start_number, start_number + expected))
    if numbers != expected_numbers:
        raise PipelineError(
            f"expected contiguous frames {start_number}..{start_number + expected - 1}, found {len(found)}",
            ExitCode.MUX_OR_VALIDATION,
            "frames",
        )
    indices = sorted({0, expected // 2, expected - 1})
    hashes = [sha256_file(found[index][1]) for index in indices]
    if expected > 1 and len(set(hashes)) < 2:
        raise PipelineError(
            "sampled frames are identical",
            ExitCode.MUX_OR_VALIDATION,
            "frames",
        )
    return {
        "count": len(found),
        "first_number": numbers[0],
        "last_number": numbers[-1],
        "sample_sha256": hashes,
        "unique_sample_hashes": len(set(hashes)),
    }


def parse_volume_output(output: str) -> dict[str, float]:
    mean = re.search(r"mean_volume:\s+(-?(?:inf|\d+(?:\.\d+)?)) dB", output)
    maximum = re.search(r"max_volume:\s+(-?(?:inf|\d+(?:\.\d+)?)) dB", output)
    if not mean or not maximum or maximum.group(1) == "-inf":
        raise PipelineError(
            "audio is missing or silent",
            ExitCode.MUX_OR_VALIDATION,
            "audio_level",
        )
    maximum_dbfs = float(maximum.group(1))
    if maximum_dbfs < -80.0:
        raise PipelineError(
            f"audio peak {maximum_dbfs:.1f} dBFS is effectively silent",
            ExitCode.MUX_OR_VALIDATION,
            "audio_level",
        )
    return {
        "mean_dbfs": float(mean.group(1)),
        "max_dbfs": maximum_dbfs,
    }


def finalize(
    *,
    ffmpeg: Path,
    ffprobe: Path,
    source_audio: Path,
    frames_dir: Path,
    pattern: str,
    expected_frames: int,
    start_number: int,
    fps: int,
    width: int,
    height: int,
    output_dir: Path,
    stem: str,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    if progress is not None:
        progress.start("encode_mux", "H.264 encode + authoritative AAC mux")
    inventory = frame_inventory(frames_dir, pattern, expected_frames, start_number)
    video_only = output_dir / f"{stem}.video-only.mp4"
    final_mp4 = output_dir / f"{stem}.mp4"
    run_logged(
        [
            str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
            "-framerate", str(fps), "-start_number", str(start_number),
            "-i", str(frames_dir / pattern), "-frames:v", str(expected_frames),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video_only),
        ],
        output_dir / "ffmpeg-video.log",
        exit_code=ExitCode.MUX_OR_VALIDATION,
        stage="video_encode",
    )
    run_logged(
        [
            str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
            "-i", str(video_only), "-i", str(source_audio),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "1",
            "-movflags", "+faststart", str(final_mp4),
        ],
        output_dir / "ffmpeg-mux.log",
        exit_code=ExitCode.MUX_OR_VALIDATION,
        stage="mux",
    )
    if progress is not None:
        progress.complete(f"{expected_frames} frames + AAC")
        progress.start("verification", "ffprobe, A/V sync, audio, full decode")
    probe = capture_json(
        [
            str(ffprobe), "-v", "error",
            "-show_entries",
            "format=duration,size,start_time:stream=codec_type,codec_name,profile,width,height,r_frame_rate,sample_rate,channels,start_time,duration,nb_frames",
            "-of", "json", str(final_mp4),
        ],
        stage="final_probe",
    )
    videos = [item for item in probe["streams"] if item["codec_type"] == "video"]
    audios = [item for item in probe["streams"] if item["codec_type"] == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise PipelineError(
            "final MP4 does not have one video and one audio stream",
            ExitCode.MUX_OR_VALIDATION,
            "final_probe",
        )
    video, audio = videos[0], audios[0]
    if video["codec_name"] != "h264" or audio["codec_name"] != "aac":
        raise PipelineError(
            "final codecs are not H.264/AAC",
            ExitCode.MUX_OR_VALIDATION,
            "final_probe",
        )
    if int(video.get("nb_frames") or 0) != expected_frames:
        raise PipelineError(
            "encoded frame count mismatch",
            ExitCode.MUX_OR_VALIDATION,
            "final_probe",
        )
    if (int(video["width"]), int(video["height"])) != (width, height):
        raise PipelineError(
            "encoded resolution mismatch",
            ExitCode.MUX_OR_VALIDATION,
            "final_probe",
        )
    start_delta_ms = abs(float(video.get("start_time") or 0) - float(audio.get("start_time") or 0)) * 1000
    duration_delta_ms = abs(float(video["duration"]) - float(audio["duration"])) * 1000
    if start_delta_ms > 34 or duration_delta_ms > (1000 / fps + 25):
        raise PipelineError(
            f"A/V sync outside tolerance: start={start_delta_ms:.3f}ms duration={duration_delta_ms:.3f}ms",
            ExitCode.MUX_OR_VALIDATION,
            "final_probe",
        )
    run_logged(
        [str(ffmpeg), "-v", "error", "-i", str(final_mp4), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        output_dir / "ffmpeg-decode.log",
        exit_code=ExitCode.MUX_OR_VALIDATION,
        stage="decode",
    )
    volume = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostats",
            "-i",
            str(final_mp4),
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    (output_dir / "ffmpeg-volume.log").write_text(volume.stdout, encoding="utf-8")
    if volume.returncode != 0:
        raise PipelineError(
            "volumedetect failed",
            ExitCode.MUX_OR_VALIDATION,
            "audio_level",
        )
    audio_levels = parse_volume_output(volume.stdout)
    astats = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostats",
            "-i",
            str(final_mp4),
            "-map",
            "0:a:0",
            "-af",
            "astats=metadata=1:reset=0",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    (output_dir / "ffmpeg-astats.log").write_text(astats.stdout, encoding="utf-8")
    if astats.returncode != 0 or "Number of samples:" not in astats.stdout:
        raise PipelineError(
            "astats failed",
            ExitCode.MUX_OR_VALIDATION,
            "audio_level",
        )
    result = {
        "final_mp4": str(final_mp4.resolve()),
        "sha256": sha256_file(final_mp4),
        "size_bytes": final_mp4.stat().st_size,
        "frames": inventory,
        "video_codec": video["codec_name"],
        "audio_codec": audio["codec_name"],
        "video_frames": int(video["nb_frames"]),
        "video_duration_seconds": float(video["duration"]),
        "audio_duration_seconds": float(audio["duration"]),
        "audio_sample_rate": int(audio["sample_rate"]),
        "audio_channels": int(audio["channels"]),
        "av_start_delta_ms": round(start_delta_ms, 3),
        "duration_delta_ms": round(duration_delta_ms, 3),
        "audio_mean_dbfs": audio_levels["mean_dbfs"],
        "audio_max_dbfs": audio_levels["max_dbfs"],
        "decode_pass": True,
        "audio_non_silent": True,
    }
    atomic_write_json(output_dir / "ffprobe.json", probe)
    atomic_write_json(output_dir / "verification.json", result)
    if progress is not None:
        progress.complete(
            f"H.264/AAC frames={expected_frames} A/V={start_delta_ms:0.1f}ms"
        )
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = repo_root()
    sample_app = root / ".tools/audio2face3d/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app"
    parser = argparse.ArgumentParser(
        prog=CANONICAL_COMMAND,
        description=(
            "Run NVIDIA's official A2F client, UE 5.6 TakeRecorderSubsystem "
            "capture, Epic MRQ Python executor, and verified FFmpeg mux. "
            "The canonical default is v3.0 diffusion on 127.0.0.1:52100."
        ),
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--output-root", type=Path, default=root / ".tools/audio2face3d/official-cli-runs")
    parser.add_argument(
        "--a2f-model",
        choices=("v2.3-regression", "v3.0-diffusion"),
        default=None,
        help=(
            "model profile (default: v3.0-diffusion; use "
            "v2.3-regression explicitly for the legacy 52000 path)"
        ),
    )
    parser.add_argument("--nim-url")
    parser.add_argument("--allow-remote-nim", action="store_true")
    parser.add_argument("--config", type=Path, default=sample_app / "config/config_claire.yml")
    parser.add_argument("--motion-config", type=Path)
    parser.add_argument("--avatar", default="Taro")
    parser.add_argument(
        "--avatar-visual-profile",
        choices=("source", "face-focused-vulkan-safe"),
        default="source",
        help=(
            "run-owned avatar presentation; the Vulkan-safe profile preserves "
            "Face/Body/grooms, replaces only Torso instance materials, and hides "
            "Legs/Feet without changing source MetaHuman assets"
        ),
    )
    shot_group = parser.add_mutually_exclusive_group()
    shot_group.add_argument("--shot", action="append", default=[])
    shot_group.add_argument("--shot-config", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--level-sequence")
    parser.add_argument("--map", default=DEFAULT_MAP)
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--frame-pattern", default="frame.%04d.png")
    parser.add_argument("--start-number", type=int, default=0)
    parser.add_argument("--expected-frames", type=int)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--graphics-adapter", type=int, default=0)
    parser.add_argument("--capture-timeout", type=int, default=420)
    parser.add_argument("--mrq-timeout", type=int, default=420)
    parser.add_argument("--inference-only", action="store_true")
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--final-name")
    parser.add_argument(
        "--progress", choices=("auto", "always", "never"), default="auto"
    )
    args = parser.parse_args(argv)
    args.a2f_model_explicit = args.a2f_model is not None
    if args.a2f_model is None:
        args.a2f_model = DEFAULT_MODEL_ID
    return args


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    args = parse_args(argv)
    root = repo_root()
    input_path = args.input.expanduser().resolve()
    early_resume_manifest = None
    early_resume_manifest_path = None
    if args.resume is not None:
        early_resume_path = args.resume.expanduser().resolve()
        early_resume_manifest_path = (
            early_resume_path / "manifest.json"
            if early_resume_path.is_dir()
            else early_resume_path
        )
        try:
            if early_resume_manifest_path.stat().st_size > 1024 * 1024:
                raise ResumeError("resume manifest exceeds 1 MiB")
            early_resume_manifest = json.loads(
                early_resume_manifest_path.read_text(encoding="utf-8")
            )
            selection = resolve_resume_model_selection(
                early_resume_manifest,
                requested_model=args.a2f_model,
                requested_endpoint=args.nim_url,
                model_was_explicit=args.a2f_model_explicit,
            )
            args.a2f_model = selection["model_id"]
            args.nim_url = selection["endpoint"]
            args.model_selection_source = selection["selection_source"]
        except (OSError, json.JSONDecodeError, ResumeError) as exc:
            print(
                f"FAILED stage=resume_model exit=10 error={exc}", file=sys.stderr
            )
            return int(ExitCode.PREFLIGHT)
    else:
        args.model_selection_source = (
            "explicit-cli" if args.a2f_model_explicit else "canonical-default"
        )
    args.nim_url = resolve_nim_endpoint(args.a2f_model, args.nim_url)
    if args.shot_config is not None:
        shot_config_path = args.shot_config.expanduser().resolve()
        if (
            not shot_config_path.is_file()
            or shot_config_path.stat().st_size > 1024 * 1024
        ):
            print(
                "FAILED stage=shot_config exit=48 error=shot config must be a file no larger than 1 MiB",
                file=sys.stderr,
            )
            return int(ExitCode.SHOT_CONFIG_INVALID)
        try:
            shots = validate_shot_document(
                json.loads(shot_config_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, ShotConfigError) as exc:
            print(
                f"FAILED stage=shot_config exit=48 error={exc}", file=sys.stderr
            )
            return int(ExitCode.SHOT_CONFIG_INVALID)
        shot_request = {"mode": "config", "path": str(shot_config_path)}
    else:
        try:
            shots = resolve_named_shots(args.shot)
        except ShotConfigError as exc:
            print(
                f"FAILED stage=shot_config exit=48 error={exc}", file=sys.stderr
            )
            return int(ExitCode.SHOT_CONFIG_INVALID)
        shot_request = {
            "mode": "named",
            "requested": args.shot or ["close-up-front"],
        }
    try:
        validate_cli_limits(args)
        validate_unreal_asset_reference(args.map)
        if args.level_sequence:
            validate_unreal_asset_reference(args.level_sequence)
        validate_model_endpoint_binding(args.a2f_model, args.nim_url)
        if not is_loopback_nim_endpoint(args.nim_url) and not args.allow_remote_nim:
            raise ValueError("non-loopback --nim-url requires --allow-remote-nim")
    except ValueError as exc:
        print(f"FAILED stage=arguments exit=2 error={exc}", file=sys.stderr)
        return int(ExitCode.USAGE)
    label = safe_name(args.name or input_path.stem)
    run_id = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{label}"
    lineage_source_run_id = (
        str(early_resume_manifest.get("run_id"))
        if early_resume_manifest is not None
        and early_resume_manifest.get("run_id")
        else run_id
    )
    run_dir = args.output_root.expanduser().resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    progress = ProgressReporter(
        mode=args.progress,
        event_path=run_dir / "progress-events.jsonl",
        stage_count=7 + 4 * len(shots),
    )
    progress.begin_run(
        run_id=run_id,
        model=args.a2f_model,
        endpoint=args.nim_url,
        avatar=args.avatar,
        shots=[shot["id"] for shot in shots],
        output_dir=run_dir,
    )
    model_profile = resolve_model_profile(args.a2f_model)
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "run_id": run_id,
        "status": "running",
        "stage": "preflight",
        "input": str(input_path),
        "avatar_request": args.avatar,
        "avatar_visual_profile_request": args.avatar_visual_profile,
        "shot_request": shot_request,
        "shots": shots,
        "run_dir": str(run_dir),
        "canonical_command": CANONICAL_COMMAND,
        "progress": {
            "mode": args.progress,
            "events": str(run_dir / "progress-events.jsonl"),
        },
        "a2f_model": model_profile,
        "model_selection": {
            "source": args.model_selection_source,
            "explicit": bool(args.a2f_model_explicit),
            "default_model": DEFAULT_MODEL_ID,
            "automatic_fallback": False,
        },
        "nim_endpoint": {
            "url": args.nim_url,
            "loopback": is_loopback_nim_endpoint(args.nim_url),
            "remote_opt_in": bool(args.allow_remote_nim),
        },
        "primary_sources": PRIMARY_SOURCE_URLS,
        "ecc_skills": [
            "ecc:orch-change-feature",
            "ecc:click-path-audit",
            "ecc:tdd-workflow",
            "ecc:make-interfaces-feel-better",
            "ecc:verification-loop",
            "ecc:documentation-lookup",
            "ecc:source-command-update-docs",
        ],
        "context7": {
            "requested": True,
            "available": False,
            "reason": "Context7 resource is installed, but resolve-library-id/query-docs tools are not exposed in this session; official NVIDIA/Epic URLs and installed official source were used.",
        },
        "official_support_boundary": {
            "official_surfaces": [
                "NVIDIA A2F-3D v2.0 interaction sample",
                "UACEBlueprintLibrary::AnimateCharacterFromWavFile (internally async on game thread in installed ACE 2.5)",
                "UE 5.6 TakeRecorderSubsystem + completion delegates",
                "Epic MoviePipelinePythonHostExecutor + ExecutorPythonClass",
                "FFmpeg mux and validation",
            ],
            "manual_bootstrap": "One-time project setup: Epic/Fab MetaHuman import, ACE Face_AnimBP/ACE Audio Curve Source readiness, base map, Takes/MovieRenderPipeline/Python plugins, and a working VNC PulseAudio session.",
        },
    }
    atomic_write_json(manifest_path, manifest)

    ffmpeg = root / ".tools/ffmpeg/bin/ffmpeg"
    ffprobe = root / ".tools/ffmpeg/bin/ffprobe"
    sample_app = root / ".tools/audio2face3d/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app"
    official_python = sample_app / ".venv/bin/python"
    official_client = sample_app / "a2f_3d.py"
    editor = root / ".tools/audio2face-metahuman/UE_5.6/Engine/Binaries/Linux/UnrealEditor"
    editor_cmd = root / ".tools/audio2face-metahuman/UE_5.6/Engine/Binaries/Linux/UnrealEditor-Cmd"
    if not editor_cmd.exists():
        editor_cmd = root / ".tools/audio2face-metahuman/UE_5.6/Engine/Binaries/Linux/UnrealEditor"
    project = root / ".tools/audio2face-metahuman/KairosSample/KairosSample.uproject"
    init_unreal = root / ".tools/audio2face-metahuman/KairosSample/Content/Python/init_unreal.py"
    capture_module = root / ".tools/audio2face-metahuman/KairosSample/Content/Python/a2f_metahuman_capture.py"
    mrq_module = root / ".tools/audio2face-metahuman/KairosSample/Content/Python/a2f_metahuman_movie_pipeline_executor.py"
    mannequin_dataset_dir = (
        root
        / ".tools/audio2face3d/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire"
    )
    mannequin_skin_path = mannequin_dataset_dir / "bs_data/bs_skin.npz"
    mannequin_tongue_path = mannequin_dataset_dir / "bs_data/bs_tongue.npz"
    mannequin_topology_path = (
        mannequin_dataset_dir / "geom/fullface/claire_lowres_topology.json"
    )
    config = args.config.expanduser().resolve()
    motion_artifacts = None

    try:
        progress.start("preflight", "Validate paths, config, input, and resume")
        required = [input_path, ffmpeg, ffprobe]
        if not args.finalize_only:
            required.extend(
                [
                    official_python,
                    official_client,
                    config,
                    mannequin_skin_path,
                    mannequin_tongue_path,
                    mannequin_topology_path,
                ]
            )
        if not args.finalize_only and not args.inference_only:
            required.extend([editor, editor_cmd, project, init_unreal, capture_module, mrq_module])
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise PipelineError(f"missing required files: {missing}", ExitCode.PREFLIGHT, "preflight")
        source_probe = probe_audio(ffprobe, input_path)
        if input_path.stat().st_size > 2 * 1024 * 1024 * 1024:
            raise PipelineError("input audio exceeds 2 GiB", ExitCode.PREFLIGHT, "preflight")
        if source_probe["duration_seconds"] > 600.0:
            raise PipelineError("input audio exceeds 10 minutes", ExitCode.PREFLIGHT, "preflight")
        input_hash = sha256_file(input_path)
        motion_config = load_motion_config(
            args.motion_config,
            source_probe["duration_seconds"],
            model_id=args.a2f_model,
        )
        curve_source_identity = curve_source_identity_for_motion_config(
            motion_config
        )
        panel_identity = showcase_identity(
            model_id=model_profile["id"],
            architecture=model_profile["architecture"],
            nim_model_id=model_profile["nim_model_id"],
            curve_source=curve_source_identity,
            layout_id="layout-v3",
        )
        atomic_write_json(run_dir / "effective-motion-config.json", motion_config)
        request_config = config
        request_config_record = None
        if not args.finalize_only:
            request_config = run_dir / "effective-nvidia-request.yml"
            request_config_record = write_effective_request_config(
                config, motion_config, request_config
            )
        config_hash = sha256_file(request_config)
        resumed_inference = None
        if args.resume is not None:
            resume_manifest_path = early_resume_manifest_path
            try:
                if resume_manifest_path is None or early_resume_manifest is None:
                    raise ResumeError("resume manifest was not preflighted")
                resume_manifest = early_resume_manifest
                resumed_inference = verify_resumed_inference(
                    validate_resume(
                        resume_manifest,
                        input_sha256=input_hash,
                        config_sha256=config_hash,
                    )
                )
            except (OSError, json.JSONDecodeError, ResumeError) as exc:
                raise PipelineError(str(exc), ExitCode.PREFLIGHT, "resume") from exc
            manifest["resumed_from"] = str(resume_manifest_path)
        progress.complete(
            f"audio={source_probe['duration_seconds']:0.3f}s config={motion_config['mode']}"
        )
        nim_audio = run_dir / "input.nim.pcm16-mono-16khz.wav"
        mux_audio = run_dir / "input.authoritative.pcm16-mono-48khz.wav"
        progress.start("audio_normalize", "Normalize PCM16 mono audio")
        for path, rate in ((nim_audio, 16000), (mux_audio, 48000)):
            run_logged(
                [str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning", "-i", str(input_path), "-vn", "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(path)],
                run_dir / f"ffmpeg-normalize-{rate}.log",
                exit_code=ExitCode.PREFLIGHT,
                stage="normalize",
            )
        progress.complete("16 kHz NIM + 48 kHz authoritative mux")
        expected_frames = args.expected_frames or math.ceil(source_probe["duration_seconds"] * args.fps)
        if not 1 <= expected_frames <= 36_000:
            raise PipelineError(
                "computed frame count is outside [1, 36000]",
                ExitCode.PREFLIGHT,
                "preflight",
            )
        manifest.update({
            "input_sha256": input_hash,
            "input_probe": source_probe,
            "nim_audio": str(nim_audio),
            "mux_audio": str(mux_audio),
            "expected_frames": expected_frames,
            "versions": collect_versions(root, request_config) if not args.finalize_only else None,
            "a2f_runtime_evidence": collect_a2f_runtime_evidence(
                root, args.a2f_model, args.nim_url
            ) if not args.finalize_only else None,
            "motion": {
                "schema_version": 1,
                "mode": motion_config["mode"],
                "curve_application": motion_config["curve_application"],
                "effective_config": str(run_dir / "effective-motion-config.json"),
                "effective_config_sha256": sha256_file(run_dir / "effective-motion-config.json"),
                "nvidia_request_config": request_config_record,
                "client_request_config_compatibility": {
                    "role": model_profile["client_config_role"],
                    "filename": model_profile["client_request_config"],
                    "selected_model": model_profile["id"],
                    "service_model_selection": (
                        "attested by NIM endpoint/runtime, not this shared request header"
                    ),
                },
                "ace_runtime_boundary": {
                    "direct_ace_runtime": [
                        "constant emotion",
                        "overall emotion strength",
                        "face parameters",
                        (
                            "per-curve multiplier/offset maps on official "
                            "FAnimNode_ApplyACEAnimation"
                        ),
                    ],
                    "final_render_bake": [
                        "timecoded emotion", "attack/release", "per-region gain",
                        "per-curve gain/bias/clamp for ACE 2.5 ARKit 52"
                    ],
                    "extended_tongue": (
                        "diagnostic artifact only: installed ACE 2.5 source stream "
                        "does not expose the 16 extended tongue curves"
                    ),
                    "post_bake_warning": (
                        "float curves added after Take Recorder do not re-evaluate "
                        "the already baked MetaHuman bone pose"
                    ),
                },
            },
        })
        atomic_write_json(manifest_path, manifest)

        progress.start("nim_health", "Official NVIDIA NIM health")
        if args.finalize_only:
            progress.complete("skipped by --finalize-only")
            progress.start("nim_inference", "Official NVIDIA inference")
            progress.complete("skipped by --finalize-only")
            progress.start("motion_artifacts", "Export blendshape/emotion artifacts")
            progress.complete("skipped by --finalize-only")
        else:
            work_dir = run_dir / "official-nvidia-client"
            if resumed_inference is not None:
                progress.complete("reused verified inference boundary")
                progress.start("nim_inference", "Official NVIDIA inference")
                official_verification = dict(resumed_inference)
                official_verification["reused"] = True
                atomic_write_json(
                    run_dir / "official-inference-verification.json",
                    official_verification,
                )
                progress.complete("reused hash-verified outputs")
            else:
                work_dir.mkdir()
                health_output = run_logged(
                    [str(official_python), str(official_client), "health_check", "--url", args.nim_url],
                    run_dir / "nvidia-health.log",
                    cwd=work_dir,
                    exit_code=ExitCode.NIM_INFERENCE,
                    stage="nvidia_health",
                )
                if "ONLINE" not in health_output:
                    raise PipelineError("official NVIDIA health client did not report ONLINE", ExitCode.NIM_INFERENCE, "nvidia_health")
                progress.complete("ONLINE")
                progress.start("nim_inference", "Official NVIDIA inference")
                inference_output = run_logged(
                    build_inference_command(python=official_python, client=official_client, audio=nim_audio, config=request_config, url=args.nim_url),
                    run_dir / "nvidia-inference.log",
                    cwd=work_dir,
                    exit_code=ExitCode.NIM_INFERENCE,
                    stage="nvidia_inference",
                )
                if "Status code: SUCCESS" not in inference_output:
                    raise PipelineError("official NVIDIA client did not return SUCCESS", ExitCode.NIM_INFERENCE, "nvidia_inference")
                official_output = work_dir / "output_000001"
                required_outputs = [
                    official_output / "animation_frames.csv",
                    official_output / "a2f_3d_input_emotions.csv",
                    official_output / "a2f_3d_smoothed_emotion_output.csv",
                    official_output / "out.wav",
                ]
                missing_outputs = [str(path) for path in required_outputs if not path.is_file()]
                if missing_outputs:
                    raise PipelineError(f"official NVIDIA outputs missing: {missing_outputs}", ExitCode.NIM_INFERENCE, "official_output_validation")
                official_verification = {
                    "animation": validate_animation_csv(required_outputs[0]),
                    "returned_audio": probe_audio(ffprobe, required_outputs[3]),
                    "output_dir": str(official_output),
                    "files": {path.name: {"sha256": sha256_file(path), "size_bytes": path.stat().st_size} for path in required_outputs},
                    "entry_point": str(official_client),
                    "entry_point_sha256": sha256_file(official_client),
                    "config": str(request_config),
                    "model_profile": model_profile,
                    "reused": False,
                }
                atomic_write_json(
                    run_dir / "official-inference-verification.json",
                    official_verification,
                )
                progress.complete(
                    f"frames={official_verification['animation']['frames']} curves={official_verification['animation']['blendshape_columns']}"
                )
            manifest["official_nvidia_inference"] = official_verification
            try:
                animation_evidence = official_verification["animation"]
                official_verification["model_cadence"] = (
                    validate_model_output_cadence(
                        args.a2f_model,
                        frames=int(animation_evidence["frames"]),
                        first_timecode=float(animation_evidence["first_timecode"]),
                        last_timecode=float(animation_evidence["last_timecode"]),
                        output_frames=expected_frames,
                    )
                )
            except (KeyError, TypeError, ValueError, ModelProfileError) as error:
                raise PipelineError(
                    f"model output cadence/identity validation failed: {error}",
                    ExitCode.NIM_INFERENCE,
                    "model_identity",
                ) from error
            atomic_write_json(
                run_dir / "official-inference-verification.json",
                official_verification,
            )
            progress.start("motion_artifacts", "Export blendshape/emotion artifacts")
            motion_artifacts = export_motion_artifacts(
                official_output=Path(official_verification["output_dir"]),
                output_dir=run_dir / "motion-artifacts",
                motion_config=motion_config,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                fps=args.fps,
                expected_frames=expected_frames,
                mannequin_skin_path=mannequin_skin_path,
                mannequin_tongue_path=mannequin_tongue_path,
                mannequin_topology_path=mannequin_topology_path,
                panel_identity=panel_identity,
            )
            selected_curve_record = motion_artifacts["records"][
                "blendshapes_effective"
                if motion_config["curve_application"] == "final_render"
                else "blendshapes_raw"
            ]["json"]
            compositor_lineage = make_lineage(
                source_run_id=lineage_source_run_id,
                input_sha256=input_hash,
                authoritative_audio_sha256=sha256_file(mux_audio),
                model_id=model_profile["id"],
                architecture=model_profile["architecture"],
                nim_model_id=model_profile["nim_model_id"],
                nim_endpoint=args.nim_url,
                curve_source_sha256=selected_curve_record["sha256"],
                curve_source=curve_source_identity,
                fps=args.fps,
                frame_count=expected_frames,
            )
            motion_artifacts["lineage"] = compositor_lineage
            motion_artifacts["mannequin"]["lineage"] = compositor_lineage
            motion_artifacts["readable_panel"]["lineage"] = compositor_lineage
            artifact_manifest_path = Path(
                motion_artifacts["artifact_manifest"]["path"]
            )
            artifact_payload = dict(motion_artifacts)
            artifact_payload.pop("artifact_manifest", None)
            atomic_write_json(artifact_manifest_path, artifact_payload)
            motion_artifacts["artifact_manifest"] = {
                "path": str(artifact_manifest_path),
                "sha256": sha256_file(artifact_manifest_path),
            }
            manifest["motion_artifacts"] = motion_artifacts
            manifest["showcase_identity"] = panel_identity
            manifest["compositor_lineage"] = compositor_lineage
            atomic_write_json(manifest_path, manifest)
            progress.complete(
                f"raw={motion_artifacts['records']['blendshapes_raw']['frames']} visualization={expected_frames}"
            )

        if args.inference_only:
            manifest.update({
                "status": "manual_action_required",
                "stage": "inference_only_complete",
                "exit_code": int(ExitCode.MANUAL_EDITOR_CAPTURE_REQUIRED),
                "manual_action": {
                    "audio_to_load_in_kairos": str(mux_audio),
                    "avatar_request": args.avatar,
                    "map": args.map,
                    "next_command": "Run again without --inference-only to use the TakeRecorderSubsystem/MRQ hybrid pipeline.",
                },
            })
            atomic_write_json(manifest_path, manifest)
            progress.manual(
                "inference-only boundary complete",
                manifest=manifest_path,
                resume="Run again without --inference-only",
            )
            print(f"INFERENCE_ONLY_COMPLETE run={run_dir}")
            print(f"Official inference PASS: {manifest['official_nvidia_inference']['output_dir']}")
            return int(ExitCode.MANUAL_EDITOR_CAPTURE_REQUIRED)

        environment = vnc_session_environment()
        if len(shots) > 1 and args.frames_dir is not None:
            raise PipelineError(
                "--frames-dir is only supported for a single shot",
                ExitCode.USAGE,
                "arguments",
            )
        progress.start("capture", "MetaHuman readiness + ACE/Take Recorder capture")
        avatar_lineage = None
        if args.finalize_only:
            if args.frames_dir is None:
                raise PipelineError(
                    "--frames-dir is required with --finalize-only",
                    ExitCode.USAGE,
                    "arguments",
                )
            render_map = args.map
            captured_shots = [
                {
                    "id": shots[0]["id"],
                    "preset": shots[0].get("preset"),
                    "camera": shots[0]["camera"],
                    "level_sequence": args.level_sequence,
                }
            ]
            avatar_manifest = {"requested": args.avatar, "resolution_method": "not-run"}
            progress.complete("skipped by --finalize-only")
        elif args.level_sequence:
            if len(shots) != 1:
                raise PipelineError(
                    "--level-sequence can only be used with one shot",
                    ExitCode.USAGE,
                    "arguments",
                )
            render_map = args.map
            captured_shots = [
                {
                    "id": shots[0]["id"],
                    "preset": shots[0].get("preset"),
                    "camera": shots[0]["camera"],
                    "level_sequence": args.level_sequence,
                }
            ]
            avatar_manifest = {"requested": args.avatar, "resolution_method": "caller-sequence"}
            manifest["capture"] = {
                "status": "skipped",
                "reason": "caller supplied an existing LevelSequence",
            }
            progress.complete("caller-supplied LevelSequence")
        else:
            manifest["stage"] = "take_recorder_capture"
            capture_status_path = run_dir / "capture-status.json"
            asset_token = run_id.replace("-", "_")
            capture_config = {
                "schema_version": 1,
                "run_id": run_id,
                "slate": f"A2FMetaHuman_{asset_token}",
                "audio_path": str(mux_audio),
                "audio_duration_seconds": source_probe["duration_seconds"],
                "expected_frames": expected_frames,
                "fps": args.fps,
                "status_path": str(capture_status_path),
                "asset_root": f"/Game/Cinematics/A2FMetaHumanCLI/{asset_token}",
                "avatar_selector": args.avatar,
                "avatar_visual_profile": args.avatar_visual_profile,
                "shots": shots,
                "map_path": args.map,
                "nim_endpoint": args.nim_url,
                "a2f_model": args.a2f_model,
                "ace_runtime_parameters": {
                    "face_parameters": motion_config["face_parameters"],
                    "emotion": motion_config["emotion"],
                    "curve_parameters": motion_config[
                        "nvidia_runtime_curve_parameters"
                    ],
                },
                "curve_application": motion_config["curve_application"],
                "timeline_policy": capture_timeline_policy(
                    motion_config["curve_application"]
                ),
                "effective_motion_json": motion_artifacts["records"][
                    "blendshapes_effective"
                ]["json"]["path"],
                "final_render_profile": motion_config["final_render_profile"],
                "final_render_curve_names": list(
                    final_render_curve_names(motion_config)
                ),
                "lineage": compositor_lineage,
                "diagnostic_curve_names": (
                    [
                        "JawOpen",
                        "MouthClose",
                        "MouthFunnel",
                        "MouthRollLower",
                        "MouthRollUpper",
                        "MouthLowerDownLeft",
                        "MouthLowerDownRight",
                        "MouthUpperUpLeft",
                        "MouthUpperUpRight",
                        "MouthSmileLeft",
                        "MouthSmileRight",
                        "MouthFrownLeft",
                        "MouthFrownRight",
                    ]
                    if requires_content_sync(motion_config)
                    else []
                ),
                "diagnostic_frame_indices": (
                    sorted(
                        {
                            index
                            for index in (0, 30, 46, 75, 83, 86, expected_frames - 1)
                            if 0 <= index < expected_frames
                        }
                    )
                    if requires_content_sync(motion_config)
                    else []
                ),
            }
            capture_config_path = run_dir / "capture-config.json"
            atomic_write_json(capture_config_path, capture_config)
            capture_command = build_capture_command(
                editor=editor,
                project=project,
                map_path=args.map,
                log=run_dir / "capture-ue.log",
                graphics_adapter=args.graphics_adapter,
                inference_mode=(
                    "low-latency"
                    if source_probe["duration_seconds"] <= 10.0
                    else "realtime"
                ),
            )
            atomic_write_json(
                run_dir / "capture-command.json", {"argv": capture_command}
            )
            atomic_write_json(manifest_path, manifest)
            capture_status = run_capture_process(
                command=capture_command,
                environment=environment,
                config_path=capture_config_path,
                status_path=capture_status_path,
                console_log=run_dir / "capture-console.log",
                timeout_seconds=args.capture_timeout,
                progress=progress,
            )
            manifest["capture"] = capture_status
            if capture_status.get("lineage") != compositor_lineage:
                raise PipelineError(
                    "ACE capture lineage does not match the requested model/run",
                    ExitCode.MUX_OR_VALIDATION,
                    "capture_lineage",
                )
            avatar_lineage = capture_status["lineage"]
            if uses_ace_node_overrides(motion_config):
                capture_status["ace_node_override_lineage"] = (
                    validate_ace_node_override_capture(
                        motion_config, capture_status
                    )
                )
                atomic_write_json(capture_status_path, capture_status)
                manifest["capture"] = capture_status
            if motion_config["curve_application"] == "final_render":
                authoritative_effective = resample_series(
                    json.loads(
                        Path(
                            motion_artifacts["records"]["blendshapes_effective"][
                                "json"
                            ]["path"]
                        ).read_text(encoding="utf-8")
                    ),
                    fps=args.fps,
                    frame_count=expected_frames,
                )
                try:
                    capture_status["recorded_curve_preservation"] = (
                        verify_recorded_curve_samples(
                            recorded=capture_status.get(
                                "aligned_curve_samples", []
                            ),
                            effective_frames=authoritative_effective["frames"],
                            curve_names=list(BLENDSHAPE_NAMES),
                            tolerance=1e-4,
                        )
                    )
                except A2FSyncError as error:
                    raise PipelineError(
                        f"recorded AnimSequence did not preserve authoritative curves: {error}",
                        ExitCode.MUX_OR_VALIDATION,
                        "recorded_curve_preservation",
                    ) from error
                atomic_write_json(capture_status_path, capture_status)
                manifest["capture"] = capture_status
            avatar_manifest = capture_status["avatar"]
            captured_shots = capture_status["shots"]
            render_map = capture_status.get("map_path", args.map)
            atomic_write_json(manifest_path, manifest)
            progress.complete(
                f"avatar={avatar_manifest.get('asset_name', args.avatar)} "
                f"curve_mode={capture_status.get('curve_application', {}).get('mode', 'captured')}"
            )

        single_shot = len(captured_shots) == 1
        legacy_default = (
            single_shot
            and captured_shots[0]["id"] == "close-up-front"
            and args.avatar in {"Taro", "BP_Taro", "/Game/MetaHumans/Taro/BP_Taro", "/Game/MetaHumans/Taro/BP_Taro.BP_Taro"}
        )
        shot_results = []
        for shot in captured_shots:
            shot_dir = run_dir if single_shot else run_dir / "shots" / shot["id"]
            shot_dir.mkdir(parents=True, exist_ok=True)
            frames_dir = (
                args.frames_dir.expanduser().resolve()
                if single_shot and args.frames_dir is not None
                else shot_dir / "frames"
            )
            progress.start(
                "mrq",
                f"MRQ shot {shot['id']}",
                current=0,
                total=expected_frames,
            )
            if not args.finalize_only:
                try:
                    validate_mrq_output_directory(
                        args.frames_dir.expanduser()
                        if single_shot and args.frames_dir is not None
                        else frames_dir
                    )
                except ValueError as exc:
                    raise PipelineError(str(exc), ExitCode.USAGE, "frames_dir") from exc
                manifest["stage"] = f"mrq:{shot['id']}"
                mrq_config = {
                    "schema_version": 1,
                    "run_id": run_id,
                    "shot_id": shot["id"],
                    "level_sequence": shot["level_sequence"],
                    "map_path": render_map,
                    "frames_dir": str(frames_dir),
                    "fps": args.fps,
                    "width": args.width,
                    "height": args.height,
                    "official_executor_base": "unreal.MoviePipelinePythonHostExecutor",
                    "official_example": "/Engine/Plugins/MovieScene/MovieRenderPipeline/Content/Python/MoviePipelineExampleRuntimeExecutor.py",
                }
                mrq_config_path = shot_dir / "mrq-config.json"
                atomic_write_json(mrq_config_path, mrq_config)
                command = build_mrq_command(
                    editor_cmd=editor_cmd,
                    project=project,
                    map_path=render_map,
                    sequence=shot["level_sequence"],
                    log=shot_dir / "mrq.log",
                    graphics_adapter=args.graphics_adapter,
                )
                atomic_write_json(shot_dir / "mrq-command.json", {"argv": command})
                atomic_write_json(manifest_path, manifest)
                run_mrq_process(
                    command=command,
                    environment=environment,
                    config_path=mrq_config_path,
                    console_log=shot_dir / "mrq-console.log",
                    timeout_seconds=args.mrq_timeout,
                    frames_dir=frames_dir,
                    expected_frames=expected_frames,
                    progress=progress,
                )
                progress.complete(f"{expected_frames}/{expected_frames} frames")
            else:
                progress.complete("reused caller-provided frames")
            manifest["stage"] = f"mux:{shot['id']}"
            atomic_write_json(manifest_path, manifest)
            if args.final_name and single_shot:
                stem = safe_name(args.final_name)
            elif legacy_default:
                stem = safe_name(
                    f"taro-a2f-{label}-{panel_identity['model_token']}-final"
                )
            else:
                avatar_slug = safe_name(
                    str(avatar_manifest.get("asset_name") or args.avatar).removeprefix("BP_")
                )
                stem = safe_name(
                    f"a2f-{avatar_slug}-{label}-{shot['id']}-"
                    f"{panel_identity['model_token']}-final"
                )
            verification = finalize(
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                source_audio=mux_audio,
                frames_dir=frames_dir,
                pattern=args.frame_pattern,
                expected_frames=expected_frames,
                start_number=args.start_number,
                fps=args.fps,
                width=args.width,
                height=args.height,
                output_dir=shot_dir,
                stem=stem,
                progress=progress,
            )
            if motion_artifacts is not None and requires_content_sync(
                motion_config
            ):
                progress.update(detail="content sync: avatar motion vs A2F JawOpen")
                sync_source = (
                    "blendshapes_effective"
                    if motion_config["curve_application"] == "final_render"
                    else "blendshapes_raw"
                )
                try:
                    content_sync = verify_avatar_curve_sync(
                        ffmpeg=ffmpeg,
                        avatar_video=Path(verification["final_mp4"]),
                        motion_json=Path(
                            motion_artifacts["records"][sync_source]["json"]["path"]
                        ),
                        fps=args.fps,
                        frame_count=expected_frames,
                    )
                except A2FSyncError as error:
                    content_sync = {
                        "schema_version": 1,
                        "status": "inconclusive",
                        "reason": str(error),
                    }
                if content_sync["status"] == "misaligned":
                    unsynced_path = shot_dir / f"{stem}-pre-sync.mp4"
                    corrected_path = shot_dir / f"{stem}-sync-corrected.mp4"
                    shutil.copy2(verification["final_mp4"], unsynced_path)
                    run_logged(
                        build_avatar_sync_correction_command(
                            ffmpeg=ffmpeg,
                            source=unsynced_path,
                            output=corrected_path,
                            lag_frames=content_sync["lag_frames"],
                            fps=args.fps,
                            frame_count=expected_frames,
                        ),
                        shot_dir / "ffmpeg-content-sync-correction.log",
                        exit_code=ExitCode.MUX_OR_VALIDATION,
                        stage="content_sync_correction",
                    )
                    corrected_sync = verify_avatar_curve_sync(
                        ffmpeg=ffmpeg,
                        avatar_video=corrected_path,
                        motion_json=Path(
                            motion_artifacts["records"][sync_source]["json"]["path"]
                        ),
                        fps=args.fps,
                        frame_count=expected_frames,
                    )
                    if corrected_sync["status"] != "aligned":
                        raise PipelineError(
                            "automatic avatar content-sync correction did not converge: "
                            f"before={content_sync['lag_frames']} frames, "
                            f"after={corrected_sync['lag_frames']} frames, "
                            f"correlation={corrected_sync['correlation']:.3f}",
                            ExitCode.MUX_OR_VALIDATION,
                            "content_sync",
                        )
                    Path(corrected_path).replace(verification["final_mp4"])
                    corrected_probe = verify_comparison_video(
                        ffmpeg,
                        ffprobe,
                        Path(verification["final_mp4"]),
                        expected_frames,
                        args.fps,
                        shot_dir / "ffmpeg-content-sync-corrected-decode.log",
                    )
                    verification.update(
                        {
                            "sha256": corrected_probe["sha256"],
                            "size_bytes": Path(
                                verification["final_mp4"]
                            ).stat().st_size,
                            "video_codec": corrected_probe["video_codec"],
                            "audio_codec": corrected_probe["audio_codec"],
                            "video_frames": corrected_probe["frame_count"],
                            "av_start_delta_ms": corrected_probe[
                                "av_start_delta_ms"
                            ],
                            "decode_pass": corrected_probe["decode_pass"],
                            "content_sync": corrected_sync,
                            "content_sync_correction": {
                                "applied": True,
                                "lag_frames": content_sync["lag_frames"],
                                "lag_ms": content_sync["lag_ms"],
                                "pre_sync_mp4": str(unsynced_path.resolve()),
                                "pre_sync_sha256": sha256_file(unsynced_path),
                                "method": "verified video-frame shift; audio unchanged",
                            },
                        }
                    )
                else:
                    verification["content_sync"] = content_sync
                    verification["content_sync_correction"] = {"applied": False}
                if verification["content_sync"]["status"] != "aligned":
                    raise PipelineError(
                        "trusted curve source content sync is not conclusive and aligned: "
                        f"{verification['content_sync'].get('reason', 'unknown')}",
                        ExitCode.MUX_OR_VALIDATION,
                        "content_sync",
                    )
                atomic_write_json(
                    shot_dir / "content-sync.json", verification["content_sync"]
                )
                atomic_write_json(shot_dir / "verification.json", verification)
            result = dict(shot)
            result["frames_dir"] = str(frames_dir)
            result["final_mp4"] = verification["final_mp4"]
            result["verification"] = verification
            progress.start("hstack", f"Diagnostic panels for shot {shot['id']}")
            if motion_artifacts is not None:
                selected_source = motion_artifacts["mannequin"][
                    "selected_for_avatar_comparison"
                ]
                raw_series = resample_series(
                    json.loads(
                        Path(
                            motion_artifacts["records"]["blendshapes_raw"][
                                "json"
                            ]["path"]
                        ).read_text(encoding="utf-8")
                    ),
                    fps=args.fps,
                    frame_count=expected_frames,
                )
                effective_series = resample_series(
                    json.loads(
                        Path(
                            motion_artifacts["records"]["blendshapes_effective"][
                                "json"
                            ]["path"]
                        ).read_text(encoding="utf-8")
                    ),
                    fps=args.fps,
                    frame_count=expected_frames,
                )
                mannequin_frame_manifest = json.loads(
                    Path(
                        motion_artifacts["mannequin"][selected_source]["frames"][
                            "path"
                        ]
                    ).read_text(encoding="utf-8")
                )
                avatar_lag_frames = int(
                    verification.get("content_sync_correction", {}).get(
                        "lag_frames", 0
                    )
                    if verification.get("content_sync_correction", {}).get(
                        "applied", False
                    )
                    else 0
                )
                frame_map_records = build_master_frame_map(
                    raw_frames=raw_series["frames"],
                    effective_frames=effective_series["frames"],
                    curve_names=list(BLENDSHAPE_NAMES),
                    fps=args.fps,
                    frame_count=expected_frames,
                    avatar_lag_frames=avatar_lag_frames,
                    top_k=8,
                    mannequin_geometry_sha256=[
                        frame["geometry_sha256"]
                        for frame in mannequin_frame_manifest["frames"]
                    ],
                    active_curve_names=list(final_render_curve_names(motion_config)),
                    active_curve_scope=(
                        "A2F-pose-asset-baked-68"
                        if motion_config["final_render_profile"]
                        == "pose-asset-extended"
                        else "ACE2.5-consumed-52"
                    ),
                )
                frame_map_record = write_frame_map_jsonl(
                    frame_map_records,
                    shot_dir
                    / (
                        f"{stem}-{panel_identity['filename_suffix']}-"
                        "frame-map.jsonl"
                    ),
                )
                frame_map_record["lineage"] = compositor_lineage
                frame_map_record["avatar_content_sync"] = verification.get(
                    "content_sync"
                )
                frame_map_record["avatar_correction"] = verification.get(
                    "content_sync_correction"
                )
                frame_map_record["composition_pts"] = {
                    "avatar": "settb=AVTB,setpts=N/(fps*TB)",
                    "mannequin": "settb=AVTB,setpts=N/(fps*TB)",
                    "curve_panel": "settb=AVTB,setpts=N/(fps*TB)",
                    "audio": "authoritative source starts at 0",
                }
                verification["master_clock_frame_map"] = frame_map_record
                atomic_write_json(shot_dir / "verification.json", verification)
                result["master_clock_frame_map"] = frame_map_record
                try:
                    lineage_validation = validate_compositor_lineage(
                        compositor_lineage,
                        {
                            "avatar": avatar_lineage or {},
                            "mannequin": motion_artifacts["mannequin"][
                                "lineage"
                            ],
                            "curve_panel": motion_artifacts["readable_panel"][
                                "lineage"
                            ],
                            "audio": compositor_lineage,
                        },
                    )
                except (KeyError, LineageError) as error:
                    raise PipelineError(
                        f"compositor lineage rejected mixed artifacts: {error}",
                        ExitCode.MUX_OR_VALIDATION,
                        "compositor_lineage",
                    ) from error
                result["compositor_lineage"] = lineage_validation
                comparison = shot_dir / f"{stem}-blendshape-comparison.mp4"
                run_logged(
                    build_hstack_command(
                        ffmpeg=ffmpeg,
                        avatar=Path(verification["final_mp4"]),
                        visualization=Path(
                            motion_artifacts["visualization"]["path"]
                        ),
                        output=comparison,
                        fps=args.fps,
                        frame_count=expected_frames,
                    ),
                    shot_dir / "ffmpeg-blendshape-comparison.log",
                    exit_code=ExitCode.MUX_OR_VALIDATION,
                    stage="blendshape_comparison",
                )
                result["blendshape_comparison"] = verify_comparison_video(
                    ffmpeg,
                    ffprobe,
                    comparison,
                    expected_frames,
                    args.fps,
                    shot_dir / "ffmpeg-blendshape-comparison-decode.log",
                )
                mannequin_video = Path(
                    motion_artifacts["mannequin"][selected_source]["video"]["path"]
                )
                triptych = shot_dir / (
                    f"{stem}-{panel_identity['filename_suffix']}-triptych.mp4"
                )
                run_logged(
                    build_diagnostic_triptych_command(
                        ffmpeg=ffmpeg,
                        avatar=Path(verification["final_mp4"]),
                        mannequin=mannequin_video,
                    curves=Path(motion_artifacts["readable_panel"]["path"]),
                        output=triptych,
                        fps=args.fps,
                        frame_count=expected_frames,
                    ),
                    shot_dir / "ffmpeg-diagnostic-triptych.log",
                    exit_code=ExitCode.MUX_OR_VALIDATION,
                    stage="diagnostic_triptych",
                )
                triptych_verification = verify_comparison_video(
                    ffmpeg,
                    ffprobe,
                    triptych,
                    expected_frames,
                    args.fps,
                    shot_dir / "ffmpeg-diagnostic-triptych-decode.log",
                )
                if (
                    triptych_verification["width"],
                    triptych_verification["height"],
                ) != (1920, 1080):
                    raise PipelineError(
                        "diagnostic triptych is not 1920x1080",
                        ExitCode.MUX_OR_VALIDATION,
                        "diagnostic_triptych",
                    )
                triptych_verification["mannequin_source"] = selected_source
                triptych_verification["master_clock_frame_map"] = frame_map_record
                triptych_verification["framesync_drop_duplicate_expected"] = 0
                result["diagnostic_triptych"] = triptych_verification
                progress.complete(
                    f"avatar + mannequin({selected_source}) + curves 1920x1080"
                )
            else:
                result["strict_compositor"] = {
                    "status": "skipped",
                    "reason": (
                        "no motion artifacts"
                        if motion_artifacts is None
                        else "artifact_only ACE re-inference has no captured curve SHA"
                    ),
                    "avatar_mp4_preserved": True,
                }
                progress.complete(
                    "skipped strict triptych: "
                    + result["strict_compositor"]["reason"]
                )
            result["status"] = "success"
            shot_results.append(result)

        manifest = apply_manifest_v2(
            manifest, avatar=avatar_manifest, shots=shot_results
        )
        manifest.update({"status": "success", "stage": "complete", "exit_code": 0})
        atomic_write_json(manifest_path, manifest)
        progress_outputs = [Path(item["final_mp4"]) for item in shot_results]
        if motion_artifacts is not None:
            progress_outputs.extend(
                [
                    Path(motion_artifacts["visualization"]["path"]),
                    Path(motion_artifacts["mannequin"]["raw"]["video"]["path"]),
                    Path(
                        motion_artifacts["mannequin"]["effective"]["video"]["path"]
                    ),
                ]
            )
        for item in shot_results:
            if item.get("blendshape_comparison"):
                progress_outputs.append(Path(item["blendshape_comparison"]["path"]))
            if item.get("diagnostic_triptych"):
                progress_outputs.append(Path(item["diagnostic_triptych"]["path"]))
        progress.finish(outputs=progress_outputs, manifest=manifest_path)
        print("SUCCESS " + " ".join(item["final_mp4"] for item in shot_results))
        return 0
    except (PipelineError, ValueError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            error = PipelineError(
                "interrupted by user", ExitCode.INTERRUPTED, "interrupted"
            )
        elif isinstance(exc, PipelineError):
            error = exc
        else:
            error = PipelineError(str(exc), ExitCode.USAGE, "arguments")
        if (
            args.a2f_model == "v3.0-diffusion"
            and error.stage in {"nvidia_health", "nvidia_inference"}
        ):
            error = PipelineError(
                f"{error}; {model_service_failure_hint(args.a2f_model)}",
                error.exit_code,
                error.stage,
            )
        manual = error.exit_code in {
            ExitCode.AVATAR_IMPORT_REQUIRED,
            ExitCode.AVATAR_ACE_SETUP_REQUIRED,
        }
        capture_status_path = run_dir / "capture-status.json"
        if capture_status_path.is_file():
            try:
                manifest["capture"] = json.loads(
                    capture_status_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                pass
        manifest.update(
            {
                "status": "manual_action_required" if manual else "failure",
                "stage": error.stage,
                "exit_code": int(error.exit_code),
                "error": str(error),
            }
        )
        if manual:
            resume_command = build_resume_command(
                script=Path(__file__).resolve(),
                input_path=input_path,
                avatar=args.avatar,
                resume=run_dir,
                config=config,
                map_path=args.map,
                shots=args.shot,
                shot_config=(
                    args.shot_config.expanduser().resolve()
                    if args.shot_config is not None
                    else None
                ),
                a2f_model=args.a2f_model,
                nim_url=args.nim_url,
                motion_config=(
                    args.motion_config.expanduser().resolve()
                    if args.motion_config is not None
                    else None
                ),
                avatar_visual_profile=args.avatar_visual_profile,
            )
            manifest["manual_action"] = {
                "requested_avatar": args.avatar,
                "expected_import_root": "/Game/MetaHumans",
                "authentication_boundary": "Use the Unreal Editor Fab, MetaHuman Creator, or in-editor Bridge UI. Do not provide credentials to this CLI.",
                "resume_command": resume_command,
                "official_docs": {
                    "fab": "https://dev.epicgames.com/documentation/metahuman/buying-metahumans-from-fab?lang=en-US",
                    "creator": "https://dev.epicgames.com/documentation/metahuman/metahuman-creator-in-unreal-engine",
                    "ace": PRIMARY_SOURCE_URLS["nvidia_ace_unreal_a2f"],
                },
            }
        atomic_write_json(manifest_path, manifest)
        if manual:
            progress.manual(
                str(error),
                manifest=manifest_path,
                resume=manifest.get("manual_action", {}).get("resume_command"),
            )
        else:
            stage_log = {
                "capture": run_dir / "capture-console.log",
                "official_mrq_executor": run_dir / "mrq-console.log",
                "nvidia_health": run_dir / "nvidia-health.log",
                "nvidia_inference": run_dir / "nvidia-inference.log",
            }.get(error.stage)
            progress.fail(str(error), manifest=manifest_path, log=stage_log)
        print(f"FAILED stage={error.stage} exit={int(error.exit_code)} error={error}", file=sys.stderr)
        return int(error.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
