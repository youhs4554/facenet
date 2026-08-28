#!/usr/bin/env python3

"""DIAGNOSTIC r1-r4 prototype; use run-a2f-taro-official.py for production."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from enum import IntEnum
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    PREFLIGHT = 10
    NIM = 20
    UE_STARTUP = 30
    A2F_INFERENCE = 31
    TAKE_CAPTURE = 32
    MRQ_RENDER = 33
    MUX = 40
    VALIDATION = 41
    INTERRUPTED = 50


class PipelineError(RuntimeError):
    def __init__(self, message: str, exit_code: ExitCode, stage: str):
        super().__init__(message)
        self.exit_code = exit_code
        self.stage = stage


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if not normalized:
        raise ValueError("name must contain at least one letter or number")
    return normalized[:64]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_rate(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def build_ue_command(
    *,
    editor: Path,
    project: Path,
    map_path: str,
    bootstrap: Path,
    ue_log: Path,
    graphics_adapter: int,
    inference_mode: str,
) -> list[str]:
    return [
        str(editor),
        str(project),
        map_path,
        "-vulkan",
        "-RenderOffscreen",
        "-Multiprocess",
        "-Unattended",
        "-NoSplash",
        "-NoP4",
        f"-graphicsadapter={graphics_adapter}",
        f"-A2FDemoMode={inference_mode}",
        "-A2FCLIAutomation",
        f"-abslog={ue_log}",
        "-ExecCmds=r.CEFGPUAcceleration 0",
    ]


def run_logged(
    command: list[str],
    log_path: Path,
    *,
    env: dict[str, str] | None = None,
    exit_code: ExitCode,
    stage: str,
) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_stream:
        completed = subprocess.run(
            command,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            check=False,
        )
    if completed.returncode != 0:
        raise PipelineError(
            f"command failed with exit {completed.returncode}; see {log_path}",
            exit_code,
            stage,
        )
    return completed


def capture_json(
    command: list[str], *, exit_code: ExitCode, stage: str
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PipelineError(
            completed.stderr.strip() or f"command failed: {' '.join(command)}",
            exit_code,
            stage,
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"invalid JSON from {' '.join(command)}: {exc}", exit_code, stage
        ) from exc


def probe_audio(ffprobe: Path, audio_path: Path) -> dict[str, Any]:
    probe = capture_json(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_type,codec_name,sample_rate,channels,duration",
            "-of",
            "json",
            str(audio_path),
        ],
        exit_code=ExitCode.PREFLIGHT,
        stage="input_probe",
    )
    streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise PipelineError("input has no audio stream", ExitCode.PREFLIGHT, "input_probe")
    duration = float(probe.get("format", {}).get("duration") or streams[0].get("duration") or 0)
    if duration <= 0:
        raise PipelineError("input duration is zero", ExitCode.PREFLIGHT, "input_probe")
    return {
        "duration_seconds": duration,
        "codec": streams[0].get("codec_name"),
        "sample_rate": int(streams[0].get("sample_rate") or 0),
        "channels": int(streams[0].get("channels") or 0),
        "size_bytes": int(probe.get("format", {}).get("size") or audio_path.stat().st_size),
    }


def validate_final_probe(
    probe: dict[str, Any],
    *,
    expected_frames: int,
    fps: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    videos = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    audios = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise PipelineError(
            "final MP4 must contain exactly one video and one audio stream",
            ExitCode.VALIDATION,
            "ffprobe",
        )
    video, audio = videos[0], audios[0]
    if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
        raise PipelineError(
            "final codecs must be H.264 video and AAC audio",
            ExitCode.VALIDATION,
            "ffprobe",
        )
    if int(video.get("width") or 0) != width or int(video.get("height") or 0) != height:
        raise PipelineError(
            f"unexpected resolution {video.get('width')}x{video.get('height')}",
            ExitCode.VALIDATION,
            "ffprobe",
        )
    if abs(parse_rate(video.get("r_frame_rate", "0/1")) - fps) > 0.001:
        raise PipelineError("unexpected video frame rate", ExitCode.VALIDATION, "ffprobe")
    if int(video.get("nb_frames") or 0) != expected_frames:
        raise PipelineError(
            f"expected {expected_frames} encoded frames, got {video.get('nb_frames')}",
            ExitCode.VALIDATION,
            "ffprobe",
        )
    if int(audio.get("sample_rate") or 0) != 48000 or int(audio.get("channels") or 0) != 1:
        raise PipelineError(
            "final audio must be 48 kHz mono",
            ExitCode.VALIDATION,
            "ffprobe",
        )
    video_start = float(video.get("start_time") or 0)
    audio_start = float(audio.get("start_time") or 0)
    video_duration = float(video.get("duration") or 0)
    audio_duration = float(audio.get("duration") or 0)
    start_delta_ms = abs(video_start - audio_start) * 1000
    duration_delta_ms = abs(video_duration - audio_duration) * 1000
    if start_delta_ms > 34:
        raise PipelineError(
            f"A/V start delta {start_delta_ms:.3f} ms exceeds one 30 fps frame",
            ExitCode.VALIDATION,
            "ffprobe",
        )
    if duration_delta_ms > (1000 / fps + 25):
        raise PipelineError(
            f"A/V duration delta {duration_delta_ms:.3f} ms is too large",
            ExitCode.VALIDATION,
            "ffprobe",
        )
    return {
        "video_codec": video["codec_name"],
        "video_profile": video.get("profile"),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": parse_rate(video["r_frame_rate"]),
        "video_frames": int(video["nb_frames"]),
        "video_duration_seconds": video_duration,
        "audio_codec": audio["codec_name"],
        "audio_sample_rate": int(audio["sample_rate"]),
        "audio_channels": int(audio["channels"]),
        "audio_duration_seconds": audio_duration,
        "av_start_delta_ms": round(start_delta_ms, 3),
        "duration_delta_ms": round(duration_delta_ms, 3),
    }


def inventory_frames(
    frames_dir: Path, frame_pattern: str, *, expected_frames: int
) -> dict[str, Any]:
    if "%04d" not in frame_pattern:
        raise PipelineError(
            "frame pattern must contain %04d", ExitCode.VALIDATION, "frames"
        )
    prefix, suffix = frame_pattern.split("%04d", 1)
    regex = re.compile(rf"^{re.escape(prefix)}(\d{{4}}){re.escape(suffix)}$")
    numbered: list[tuple[int, Path]] = []
    for path in frames_dir.iterdir() if frames_dir.is_dir() else []:
        match = regex.match(path.name)
        if match:
            numbered.append((int(match.group(1)), path))
    numbered.sort()
    numbers = [number for number, _ in numbered]
    expected_numbers = list(range(expected_frames))
    if numbers != expected_numbers:
        raise PipelineError(
            f"MRQ frames are not contiguous 0..{expected_frames - 1}; found {len(numbers)}",
            ExitCode.VALIDATION,
            "frames",
        )
    sample_indices = sorted({0, expected_frames // 2, expected_frames - 1})
    sample_hashes = [sha256_file(numbered[index][1]) for index in sample_indices]
    if expected_frames > 1 and len(set(sample_hashes)) < 2:
        raise PipelineError(
            "sampled MRQ frames are identical; facial motion was not demonstrated",
            ExitCode.VALIDATION,
            "frames",
        )
    return {
        "count": len(numbered),
        "first_number": numbers[0],
        "last_number": numbers[-1],
        "sample_numbers": sample_indices,
        "sample_sha256": sample_hashes,
        "unique_sample_hashes": len(set(sample_hashes)),
    }


def nim_ready(url: str, timeout: float = 3.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and payload.get("status") == "ready"
    except (OSError, URLError, json.JSONDecodeError):
        return False


def wait_for_nim(url: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if nim_ready(url):
            return True
        time.sleep(2)
    return False


def setup_logging(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("a2f-taro-cli")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def ue_failure_code(stage: str) -> ExitCode:
    if stage in {"a2f_request", "animation_wait"}:
        return ExitCode.A2F_INFERENCE
    if stage in {"take_setup", "take_record", "take_save", "sequence"}:
        return ExitCode.TAKE_CAPTURE
    if stage in {"mrq_setup", "mrq_render"}:
        return ExitCode.MRQ_RENDER
    return ExitCode.UE_STARTUP


def run_dedicated_ue(
    *,
    command: list[str],
    config_path: Path,
    status_path: Path,
    console_log: Path,
    timeout_seconds: int,
    environment: dict[str, str],
    logger: logging.Logger,
) -> dict[str, Any]:
    console_log.parent.mkdir(parents=True, exist_ok=True)
    env = dict(environment)
    env["A2F_CLI_RUN_CONFIG"] = str(config_path)
    with console_log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
    logger.info("Dedicated UnrealEditor PID %s started", process.pid)
    deadline = time.monotonic() + timeout_seconds
    last_stage = None
    try:
        while time.monotonic() < deadline:
            if status_path.is_file():
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    status = {}
                stage = status.get("stage")
                if stage and stage != last_stage:
                    logger.info("UE stage: %s", stage)
                    last_stage = stage
                if status.get("status") == "success":
                    logger.info("UE pipeline completed successfully")
                    return status
                if status.get("status") == "failure":
                    raise PipelineError(
                        status.get("error", "UE pipeline failed"),
                        ue_failure_code(str(stage)),
                        str(stage),
                    )
            return_code = process.poll()
            if return_code is not None:
                raise PipelineError(
                    f"dedicated UnrealEditor exited early with {return_code}; see {console_log}",
                    ue_failure_code(str(last_stage or "ue_startup")),
                    str(last_stage or "ue_startup"),
                )
            time.sleep(1)
        raise PipelineError(
            f"dedicated UnrealEditor exceeded {timeout_seconds}s timeout",
            ue_failure_code(str(last_stage or "ue_startup")),
            str(last_stage or "ue_timeout"),
        )
    finally:
        if process.poll() is None:
            logger.info("Stopping dedicated UnrealEditor process group %s only", process.pid)
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                logger.warning("Dedicated UnrealEditor did not exit after SIGTERM; leaving it for inspection")


def finalize_mp4(
    *,
    ffmpeg: Path,
    ffprobe: Path,
    normalized_audio: Path,
    frames_dir: Path,
    frame_pattern: str,
    expected_frames: int,
    fps: int,
    width: int,
    height: int,
    output_dir: Path,
    final_stem: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_inventory = inventory_frames(
        frames_dir, frame_pattern, expected_frames=expected_frames
    )
    video_only = output_dir / f"{final_stem}.video-only.mp4"
    final = output_dir / f"{final_stem}.mp4"
    run_logged(
        [
            str(ffmpeg),
            "-hide_banner",
            "-y",
            "-loglevel",
            "warning",
            "-framerate",
            str(fps),
            "-start_number",
            "0",
            "-i",
            str(frames_dir / frame_pattern),
            "-frames:v",
            str(expected_frames),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video_only),
        ],
        output_dir / "ffmpeg-video.log",
        exit_code=ExitCode.MUX,
        stage="video_encode",
    )
    run_logged(
        [
            str(ffmpeg),
            "-hide_banner",
            "-y",
            "-loglevel",
            "warning",
            "-i",
            str(video_only),
            "-i",
            str(normalized_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(final),
        ],
        output_dir / "ffmpeg-mux.log",
        exit_code=ExitCode.MUX,
        stage="audio_mux",
    )
    probe = capture_json(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=filename,start_time,duration,size,bit_rate:stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,sample_rate,channels,channel_layout,start_time,duration,nb_frames,bit_rate",
            "-of",
            "json",
            str(final),
        ],
        exit_code=ExitCode.VALIDATION,
        stage="ffprobe",
    )
    atomic_write_json(output_dir / "ffprobe.json", probe)
    av = validate_final_probe(
        probe,
        expected_frames=expected_frames,
        fps=fps,
        width=width,
        height=height,
    )
    run_logged(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-i",
            str(final),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        output_dir / "ffmpeg-decode.log",
        exit_code=ExitCode.VALIDATION,
        stage="decode",
    )
    volume_command = [
        str(ffmpeg),
        "-hide_banner",
        "-nostats",
        "-i",
        str(final),
        "-map",
        "0:a:0",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    volume = subprocess.run(
        volume_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    (output_dir / "ffmpeg-volume.log").write_text(volume.stdout, encoding="utf-8")
    max_match = re.search(r"max_volume:\s+(-?(?:inf|\d+(?:\.\d+)?)) dB", volume.stdout)
    mean_match = re.search(r"mean_volume:\s+(-?(?:inf|\d+(?:\.\d+)?)) dB", volume.stdout)
    if volume.returncode != 0 or not max_match or max_match.group(1) == "-inf":
        raise PipelineError(
            "final audio is missing or silent", ExitCode.VALIDATION, "audio_level"
        )
    maximum_db = float(max_match.group(1))
    if maximum_db < -80:
        raise PipelineError(
            f"final audio peak {maximum_db:.1f} dBFS is effectively silent",
            ExitCode.VALIDATION,
            "audio_level",
        )
    result = {
        "final_mp4": str(final.resolve()),
        "video_only_mp4": str(video_only.resolve()),
        "sha256": sha256_file(final),
        "size_bytes": final.stat().st_size,
        "frames": frame_inventory,
        "streams": av,
        "audio_mean_dbfs": float(mean_match.group(1)) if mean_match and mean_match.group(1) != "-inf" else None,
        "audio_max_dbfs": maximum_db,
    }
    atomic_write_json(output_dir / "verification.json", result)
    (output_dir / "final.sha256").write_text(
        f"{result['sha256']}  {final.name}\n", encoding="utf-8"
    )
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser(
        description="Run Audio2Face-3D + UE 5.6 MetaHuman Taro to a verified MP4."
    )
    parser.add_argument("input", type=Path, help="arbitrary input audio file")
    parser.add_argument("--name", help="safe run/output name")
    parser.add_argument(
        "--output-root", type=Path, default=root / ".tools/audio2face3d/cli-runs"
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--graphics-adapter", type=int, default=0)
    parser.add_argument("--ue-timeout", type=int, default=600)
    parser.add_argument("--nim-wait", type=int, default=120)
    parser.add_argument("--start-nim", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--frame-pattern", default="frame.%04d.png")
    parser.add_argument("--expected-frames", type=int)
    parser.add_argument("--final-name")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    input_path = args.input.expanduser().resolve()
    run_label = safe_name(args.name or input_path.stem)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp}-{run_label}"
    run_dir = args.output_root.expanduser().resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    logger = setup_logging(run_dir / "orchestrator.log")
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "running",
        "stage": "preflight",
        "started_at": utc_now(),
        "input": str(input_path),
        "run_dir": str(run_dir),
        "dry_run": bool(args.dry_run),
        "finalize_only": bool(args.finalize_only),
    }
    atomic_write_json(manifest_path, manifest)

    ffmpeg = root / ".tools/ffmpeg/bin/ffmpeg"
    ffprobe = root / ".tools/ffmpeg/bin/ffprobe"
    editor = root / ".tools/audio2face-metahuman/UE_5.6/Engine/Binaries/Linux/UnrealEditor"
    project = root / ".tools/audio2face-metahuman/KairosSample/KairosSample.uproject"
    bootstrap = root / ".tools/audio2face-metahuman/KairosSample/Scripts/ue_a2f_cli_pipeline.py"
    demo_map = "/Game/Maps/TaroA2F/TaroFaceBodyDemo"
    health_url = "http://127.0.0.1:8000/v1/health/ready"

    try:
        logger.info("Run %s started", run_id)
        required = [ffmpeg, ffprobe, input_path]
        if not args.finalize_only:
            required.extend([editor, project, bootstrap])
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise PipelineError(
                f"required files are missing: {missing}", ExitCode.PREFLIGHT, "preflight"
            )
        audio = probe_audio(ffprobe, input_path)
        expected_frames = args.expected_frames or math.ceil(audio["duration_seconds"] * args.fps)
        normalized_audio = run_dir / "input.normalized.wav"
        run_logged(
            [
                str(ffmpeg),
                "-hide_banner",
                "-y",
                "-loglevel",
                "warning",
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(normalized_audio),
            ],
            run_dir / "ffmpeg-normalize.log",
            exit_code=ExitCode.PREFLIGHT,
            stage="normalize",
        )
        normalized = probe_audio(ffprobe, normalized_audio)
        manifest.update(
            {
                "input_probe": audio,
                "normalized_audio": str(normalized_audio),
                "normalized_probe": normalized,
                "input_sha256": sha256_file(input_path),
                "expected_frames": expected_frames,
                "fps": args.fps,
                "resolution": [args.width, args.height],
            }
        )
        atomic_write_json(manifest_path, manifest)

        if args.dry_run:
            manifest.update(
                {
                    "status": "success",
                    "stage": "dry_run_complete",
                    "finished_at": utc_now(),
                }
            )
            atomic_write_json(manifest_path, manifest)
            logger.info("Dry-run preflight completed: %s", run_dir)
            return int(ExitCode.SUCCESS)

        if args.finalize_only:
            if args.frames_dir is None:
                raise PipelineError(
                    "--frames-dir is required with --finalize-only",
                    ExitCode.USAGE,
                    "arguments",
                )
            frames_dir = args.frames_dir.expanduser().resolve()
            ue_status = None
        else:
            manifest["stage"] = "nim"
            atomic_write_json(manifest_path, manifest)
            if not nim_ready(health_url):
                if not args.start_nim:
                    raise PipelineError(
                        f"NIM is not ready at {health_url}", ExitCode.NIM, "nim"
                    )
                logger.info("Starting audio2face-3d-pretrained container")
                started = subprocess.run(
                    ["docker", "start", "audio2face-3d-pretrained"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                if started.returncode != 0:
                    raise PipelineError(started.stderr.strip(), ExitCode.NIM, "nim")
                if not wait_for_nim(health_url, args.nim_wait):
                    raise PipelineError("NIM readiness timed out", ExitCode.NIM, "nim")
            logger.info("NIM health is ready")

            inference_mode = "low-latency" if normalized["duration_seconds"] <= 10 else "realtime"
            frames_dir = run_dir / "frames"
            ue_config = {
                "schema_version": 1,
                "run_id": run_id,
                "slate": f"A2FCLI_{run_id.replace('-', '_')}",
                "audio_path": str(normalized_audio),
                "audio_duration_seconds": normalized["duration_seconds"],
                "expected_frames": expected_frames,
                "fps": args.fps,
                "width": args.width,
                "height": args.height,
                "frames_dir": str(frames_dir),
                "frame_pattern": "frame.{frame_number}",
                "status_path": str(run_dir / "ue-status.json"),
                "asset_root": f"/Game/Cinematics/A2FCLI/{run_id.replace('-', '_')}",
                "map_path": demo_map,
            }
            ue_config_path = run_dir / "ue-config.json"
            atomic_write_json(ue_config_path, ue_config)
            ue_command = build_ue_command(
                editor=editor,
                project=project,
                map_path=demo_map,
                bootstrap=bootstrap,
                ue_log=run_dir / "ue.log",
                graphics_adapter=args.graphics_adapter,
                inference_mode=inference_mode,
            )
            atomic_write_json(run_dir / "ue-command.json", {"argv": ue_command})
            manifest.update(
                {
                    "stage": "ue",
                    "nim_health": "ready",
                    "inference_mode": inference_mode,
                    "ue_command_file": str(run_dir / "ue-command.json"),
                }
            )
            atomic_write_json(manifest_path, manifest)
            environment = os.environ.copy()
            environment.setdefault("DISPLAY", ":1")
            environment.setdefault("XAUTHORITY", "/home/aim/.Xauthority")
            environment.setdefault("SDL_VIDEODRIVER", "x11")
            environment.setdefault("SDL_AUDIODRIVER", "pulseaudio")
            ue_status = run_dedicated_ue(
                command=ue_command,
                config_path=ue_config_path,
                status_path=run_dir / "ue-status.json",
                console_log=run_dir / "ue-console.log",
                timeout_seconds=args.ue_timeout,
                environment=environment,
                logger=logger,
            )
            manifest["ue"] = ue_status
            atomic_write_json(manifest_path, manifest)

        manifest["stage"] = "mux_and_validate"
        atomic_write_json(manifest_path, manifest)
        final_stem = safe_name(args.final_name or f"taro-a2f-{run_label}-final")
        verification = finalize_mp4(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            normalized_audio=normalized_audio,
            frames_dir=frames_dir,
            frame_pattern=args.frame_pattern,
            expected_frames=expected_frames,
            fps=args.fps,
            width=args.width,
            height=args.height,
            output_dir=run_dir,
            final_stem=final_stem,
        )
        manifest.update(
            {
                "status": "success",
                "stage": "complete",
                "finished_at": utc_now(),
                "exit_code": int(ExitCode.SUCCESS),
                "verification": verification,
            }
        )
        atomic_write_json(manifest_path, manifest)
        logger.info("SUCCESS final=%s", verification["final_mp4"])
        return int(ExitCode.SUCCESS)
    except KeyboardInterrupt:
        error = PipelineError("interrupted", ExitCode.INTERRUPTED, "interrupted")
    except ValueError as exc:
        error = PipelineError(str(exc), ExitCode.USAGE, "arguments")
    except PipelineError as exc:
        error = exc
    except Exception as exc:
        logger.exception("Unexpected pipeline failure")
        error = PipelineError(str(exc), ExitCode.PREFLIGHT, "unexpected")

    manifest.update(
        {
            "status": "failure",
            "stage": error.stage,
            "error": str(error),
            "exit_code": int(error.exit_code),
            "finished_at": utc_now(),
        }
    )
    atomic_write_json(manifest_path, manifest)
    logger.error("FAILED stage=%s exit=%s error=%s", error.stage, error.exit_code, error)
    return int(error.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
