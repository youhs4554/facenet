#!/usr/bin/env python3
"""Recompose a proven ACE capture after a post-render compositor failure.

This recovery path never re-labels a plain ACE re-inference.  It only accepts a
capture that proves the official ApplyACEAnimation node consumed exactly the
runtime maps stored in the source run's effective motion config.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess


HERE = Path(__file__).resolve().parent
CLI_PATH = HERE / "run-a2f-metahuman.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("a2f_metahuman_cli", CLI_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load canonical A2F CLI")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Strictly recompose a proven ACE-node capture without rerunning UE"
    )
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--avatar-video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path, *, limit: int = 64 * 1024 * 1024):
    if not path.is_file() or path.stat().st_size > limit:
        raise RuntimeError(f"missing or oversized JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    cli = load_cli()
    root = cli.repo_root()
    source = args.source_run.expanduser().resolve()
    avatar_video = args.avatar_video.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    if output.exists():
        raise RuntimeError("output directory already exists")
    output.mkdir(parents=True)

    manifest = read_json(source / "manifest.json", limit=1024 * 1024)
    capture = read_json(source / "capture-status.json", limit=1024 * 1024)
    config = read_json(source / "effective-motion-config.json")
    if manifest.get("a2f_model", {}).get("id") != "v3.0-diffusion":
        raise RuntimeError("source is not an attested v3.0 diffusion run")
    if manifest.get("a2f_model", {}).get("nim_model_id") != "multi_v3.2":
        raise RuntimeError("source NIM model is not multi_v3.2")
    if capture.get("status") != "success" or capture.get("stage") != "capture_complete":
        raise RuntimeError("source capture did not reach capture_complete")
    override_proof = cli.validate_ace_node_override_capture(config, capture)
    identity_name = cli.curve_source_identity_for_motion_config(config)
    if identity_name != "ace-node-overrides":
        raise RuntimeError("source is not a verified ACE-node-override run")

    mux_audio = (source / "input.authoritative.pcm16-mono-48khz.wav").resolve()
    raw_json = (source / "motion-artifacts/blendshapes.raw.json").resolve()
    effective_json = (source / "motion-artifacts/blendshapes.effective.json").resolve()
    emotion_json = (source / "motion-artifacts/emotion.smoothed.json").resolve()
    mannequin = (source / "motion-artifacts/mannequin/mannequin.raw.mp4").resolve()
    mannequin_frames = read_json(
        source / "motion-artifacts/mannequin/raw-frames.json"
    )
    for required in (avatar_video, mux_audio, raw_json, effective_json, emotion_json, mannequin):
        if not required.is_file():
            raise RuntimeError(f"required source artifact is missing: {required}")

    ffmpeg = root / ".tools/ffmpeg/bin/ffmpeg"
    ffprobe = root / ".tools/ffmpeg/bin/ffprobe"
    fps = 30
    frame_count = int(manifest["expected_frames"])
    model = manifest["a2f_model"]
    panel_identity = cli.showcase_identity(
        model_id=model["id"],
        architecture=model["architecture"],
        nim_model_id=model["nim_model_id"],
        curve_source=identity_name,
        layout_id="layout-v3",
    )

    before_sync = cli.verify_avatar_curve_sync(
        ffmpeg=ffmpeg,
        avatar_video=avatar_video,
        motion_json=raw_json,
        fps=fps,
        frame_count=frame_count,
    )
    pre_sync = output / "avatar-pre-sync.mp4"
    corrected = output / "avatar-v30-ace-node-overrides-sync.mp4"
    shutil.copy2(avatar_video, pre_sync)
    if before_sync.get("status") == "misaligned":
        cli.run_logged(
            cli.build_avatar_sync_correction_command(
                ffmpeg=ffmpeg,
                source=pre_sync,
                output=corrected,
                lag_frames=int(before_sync["lag_frames"]),
                fps=fps,
                frame_count=frame_count,
            ),
            output / "ffmpeg-content-sync-correction.log",
            exit_code=cli.ExitCode.MUX_OR_VALIDATION,
            stage="content_sync_correction",
        )
    elif before_sync.get("status") == "aligned":
        shutil.copy2(pre_sync, corrected)
    else:
        raise RuntimeError(f"source sync was inconclusive: {before_sync}")
    after_sync = cli.verify_avatar_curve_sync(
        ffmpeg=ffmpeg,
        avatar_video=corrected,
        motion_json=raw_json,
        fps=fps,
        frame_count=frame_count,
    )
    if after_sync.get("status") != "aligned":
        raise RuntimeError(f"content sync correction did not converge: {after_sync}")
    avatar_probe = cli.verify_comparison_video(
        ffmpeg,
        ffprobe,
        corrected,
        frame_count,
        fps,
        output / "ffmpeg-avatar-decode.log",
    )

    raw = cli.resample_series(read_json(raw_json), fps=fps, frame_count=frame_count)
    effective = cli.resample_series(
        read_json(effective_json), fps=fps, frame_count=frame_count
    )
    emotions = cli.resample_series(
        read_json(emotion_json), fps=fps, frame_count=frame_count
    )
    panel_frames = output / "panel-frames"
    paths = cli.render_compact_motion_frames(
        raw,
        effective,
        emotions,
        panel_frames,
        width=640,
        height=540,
        top_k=8,
        panel_identity=panel_identity,
        active_curve_names=list(cli.final_render_curve_names(config)),
    )
    panel = output / "active-curves-v30-ace-node-overrides-layout-v3.mp4"
    cli.run_logged(
        cli.build_visualization_command(ffmpeg, panel_frames, panel, fps, len(paths)),
        output / "ffmpeg-panel.log",
        exit_code=cli.ExitCode.MUX_OR_VALIDATION,
        stage="readable_motion_panel",
    )
    panel_probe = cli.verify_visualization_video(
        ffmpeg,
        ffprobe,
        panel,
        frame_count,
        fps,
        output / "ffmpeg-panel-decode.log",
    )

    lineage = cli.make_lineage(
        source_run_id=str(manifest["run_id"]),
        input_sha256=str(manifest["input_sha256"]),
        authoritative_audio_sha256=cli.sha256_file(mux_audio),
        model_id=model["id"],
        architecture=model["architecture"],
        nim_model_id=model["nim_model_id"],
        nim_endpoint=str(manifest["nim_endpoint"]),
        curve_source_sha256=cli.sha256_file(raw_json),
        curve_source=identity_name,
        fps=fps,
        frame_count=frame_count,
    )
    lineage_validation = cli.validate_compositor_lineage(
        lineage,
        {role: dict(lineage) for role in ("avatar", "mannequin", "curve_panel", "audio")},
    )
    triptych = output / "sookja-v30-ace-node-quality-layout-v3-triptych.mp4"
    cli.run_logged(
        cli.build_diagnostic_triptych_command(
            ffmpeg=ffmpeg,
            avatar=corrected,
            mannequin=mannequin,
            curves=panel,
            output=triptych,
            fps=fps,
            frame_count=frame_count,
        ),
        output / "ffmpeg-triptych.log",
        exit_code=cli.ExitCode.MUX_OR_VALIDATION,
        stage="diagnostic_triptych",
    )
    triptych_probe = cli.verify_comparison_video(
        ffmpeg,
        ffprobe,
        triptych,
        frame_count,
        fps,
        output / "ffmpeg-triptych-decode.log",
    )
    if (triptych_probe["width"], triptych_probe["height"]) != (1920, 1080):
        raise RuntimeError("triptych output is not 1920x1080")

    contact_sheet = output / "sookja-v30-ace-node-quality-contact-sheet.png"
    completed = subprocess.run(
        [
            str(ffmpeg), "-hide_banner", "-y", "-loglevel", "error",
            "-i", str(triptych),
            "-vf", "select='eq(n,0)+eq(n,46)+eq(n,89)+eq(n,108)',scale=960:540,tile=2x2",
            "-frames:v", "1", str(contact_sheet),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not contact_sheet.is_file():
        raise RuntimeError("contact sheet generation failed: " + completed.stderr[-500:])

    result = {
        "schema_version": 1,
        "status": "success",
        "mode": "bounded-ue-fallback-recomposition",
        "source_run": str(source),
        "source_run_id": manifest["run_id"],
        "source_manifest_status": manifest.get("status"),
        "source_failure_stage": manifest.get("stage"),
        "reason": "source capture/MRQ passed; original run stopped at old strict compositor identity",
        "model": model,
        "input_sha256": manifest["input_sha256"],
        "curve_source": {
            "identity": identity_name,
            "path": str(raw_json),
            "sha256": cli.sha256_file(raw_json),
            "frames": len(read_json(raw_json)["frames"]),
        },
        "ace_node_override_proof": override_proof,
        "content_sync": {"before": before_sync, "after": after_sync},
        "lineage": lineage_validation,
        "avatar": {**avatar_probe, "source_path": str(avatar_video)},
        "panel": panel_probe,
        "mannequin": {
            "path": str(mannequin),
            "sha256": cli.sha256_file(mannequin),
            "semantic_boundary": "Claire reference geometry — pre-MetaHuman retarget",
            "frame_manifest_sha256": cli.sha256_file(
                source / "motion-artifacts/mannequin/raw-frames.json"
            ),
            "sample_geometry_sha256": [
                mannequin_frames["frames"][index]["geometry_sha256"]
                for index in (0, 46, 89, 108)
            ],
        },
        "triptych": triptych_probe,
        "contact_sheet": {
            "path": str(contact_sheet),
            "sha256": cli.sha256_file(contact_sheet),
            "frames": [0, 46, 89, 108],
        },
    }
    cli.atomic_write_json(output / "recomposition-manifest.json", result)
    print(f"SUCCESS {triptych}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
