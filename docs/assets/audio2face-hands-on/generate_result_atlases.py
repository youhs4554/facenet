#!/usr/bin/env python3
"""Generate evidence-backed emotion and face-control atlases for the tutorial."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
WORK = ROOT / ".tools/audio2face3d/tutorial-emotion-atlas"
CLI_PATH = ROOT / "scripts/audio2face-metahuman/run-a2f-metahuman.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = load(CLI_PATH, "a2f_cli_for_atlas")
motion = load(ROOT / "scripts/audio2face-metahuman/a2f_motion.py", "a2f_motion_for_atlas")
mannequin = load(ROOT / "scripts/audio2face-metahuman/a2f_mannequin.py", "a2f_mannequin_for_atlas")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int, bold: bool = False):
    path = Path("/home/aim/.local/share/fonts/NanumGothic-Bold.ttf" if bold else "/home/aim/.local/share/fonts/NanumGothic-Regular.ttf")
    return ImageFont.truetype(str(path), size=size)


def run_emotion_case(case: str, config_path: Path | None, audio: Path) -> dict:
    case_dir = WORK / case
    output = case_dir / "output_000001"
    case_dir.mkdir(parents=True, exist_ok=True)
    if config_path is None:
        config = motion.resolve_motion_config()
    else:
        config = motion.validate_motion_config(
            json.loads(config_path.read_text(encoding="utf-8")),
            audio_duration=3.627,
        )
    request = case_dir / "effective-request.yml"
    cli.write_effective_request_config(
        ROOT / ".tools/audio2face3d/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app/config/config_claire.yml",
        config,
        request,
    )
    animation_csv = output / "animation_frames.csv"
    if not animation_csv.is_file():
        command = cli.build_inference_command(
            python=ROOT / ".tools/audio2face3d/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app/.venv/bin/python",
            client=ROOT / ".tools/audio2face3d/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app/a2f_3d.py",
            audio=audio,
            config=request,
            url="127.0.0.1:52100",
        )
        completed = subprocess.run(
            command,
            cwd=case_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        (case_dir / "inference.log").write_text(completed.stdout, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(f"emotion case {case} failed: {completed.stdout[-500:]}")
    series = motion.parse_animation_csv(animation_csv, source_name=f"tutorial-{case}")
    emotion_series = motion.parse_emotion_csv(
        output / "a2f_3d_smoothed_emotion_output.csv",
        source_name=f"tutorial-{case}-smoothed-emotion",
        timebase_hz=16000.0,
    )
    target_time = 2.8
    selected = min(series["frames"], key=lambda frame: abs(frame["time_seconds"] - target_time))
    emotion_selected = min(
        emotion_series["frames"],
        key=lambda frame: abs(frame["time_seconds"] - target_time),
    )
    return {
        "case": case,
        "config": config,
        "request_path": str(request),
        "request_sha256": sha256(request),
        "animation_path": str(animation_csv),
        "animation_sha256": sha256(animation_csv),
        "series": series,
        "selected": selected,
        "emotion_selected": emotion_selected,
    }


def emotion_atlas():
    completed_run = ROOT / ".tools/audio2face3d/tutorial-runs/20260828-072206-hands-on-inference-complete"
    audio = completed_run / "input.nim.pcm16-mono-16khz.wav"
    configs = HERE / "configs"
    cases = [
        ("neutral", None),
        ("joy-0.7", configs / "motion-emotion-joy-v1.json"),
        ("sadness-0.7", configs / "motion-emotion-sadness-v1.json"),
        ("anger-0.7", configs / "motion-emotion-anger-v1.json"),
        ("joy-to-sadness", configs / "motion-emotion-timecoded-v1.json"),
    ]
    records = [run_emotion_case(name, path, audio) for name, path in cases]
    basis = mannequin.load_nvidia_mannequin_basis(
        ROOT / ".tools/audio2face3d/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire/bs_data/bs_skin.npz",
        ROOT / ".tools/audio2face3d/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire/bs_data/bs_tongue.npz",
        topology_path=ROOT / ".tools/audio2face3d/datasets/Audio2Face-3D-Dataset-v1.0.0-claire/data/claire/geom/fullface/claire_lowres_topology.json",
    )
    atlas = Image.new("RGB", (1920, 1080), (8, 14, 24))
    draw = ImageDraw.Draw(atlas)
    draw.text((35, 20), "Official v3 emotion conditioning — same audio, t≈2.8 s", font=font(32, True), fill=(245, 248, 255))
    draw.text((35, 62), "Claire reference geometry; inference result only, not final MetaHuman visual equivalence", font=font(20), fill=(160, 178, 202))
    positions = [(0, 100), (640, 100), (1280, 100), (320, 590), (960, 590)]
    public_records = []
    for record, (x, y) in zip(records, positions):
        frame = record["selected"]
        image, metadata = mannequin.render_mannequin_frame(
            basis,
            frame["values"],
            width=640,
            height=470,
            frame_index=int(frame["frame_index"]),
            time_seconds=float(frame["time_seconds"]),
            source_label=record["case"],
        )
        atlas.paste(image, (x, y))
        values = frame["values"]
        top = sorted(
            zip(motion.BLENDSHAPE_NAMES, values),
            key=lambda item: (-abs(float(item[1])), motion.BLENDSHAPE_NAMES.index(item[0])),
        )[:3]
        public_records.append(
            {
                "case": record["case"],
                "request_sha256": record["request_sha256"],
                "animation_sha256": record["animation_sha256"],
                "selected_frame": int(frame["frame_index"]),
                "selected_time_seconds": float(frame["time_seconds"]),
                "geometry_sha256": metadata["geometry_sha256"],
                "top_curves": [{"name": name, "value": float(value)} for name, value in top],
                "smoothed_emotions": {
                    name: float(value)
                    for name, value in zip(
                        motion.EMOTION_NAMES,
                        record["emotion_selected"]["values"],
                    )
                    if abs(float(value)) >= 0.01
                },
            }
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "07-emotion-conditioning-atlas.png"
    atlas.save(path, optimize=False)
    provenance = {
        "schema_version": 1,
        "model": "v3.0-diffusion",
        "nim_model": "multi_v3.2",
        "endpoint": "127.0.0.1:52100",
        "input_audio_sha256": sha256(audio),
        "semantic_boundary": "Official inference/Claire reference comparison; final MetaHuman emotion render was not rerun for this atlas.",
        "cases": public_records,
        "atlas": {"path": str(path), "sha256": sha256(path)},
    }
    (RESULTS / "07-emotion-conditioning-atlas.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def face_parameter_atlas():
    ffmpeg = ROOT / ".tools/ffmpeg/bin/ffmpeg"
    sources = [
        (
            "V3 NATIVE",
            ROOT / ".tools/audio2face3d/official-cli-runs/20260827-164026-default-v30-identity-r2/taro-a2f-default-v30-identity-r2-v30-diffusion-final.mp4",
            ["runtime defaults", "identity final bake", "no extra gain"],
        ),
        (
            "DYNAMIC-SAFE",
            ROOT / ".tools/audio2face3d/official-cli-runs/20260827-165227-v30-dynamic-final-r3/taro-a2f-v30-dynamic-final-r3-v30-diffusion-final.mp4",
            ["lower 1.5 · upper 1.3", "jaw region 1.15", "attack 0.82 · release 0.58"],
        ),
        (
            "ACE NODE QUALITY",
            ROOT / ".tools/audio2face3d/quality-review/20260828-sookja-v30-ace-node-quality-v3-recomposed/avatar-v30-ace-node-overrides-sync.mp4",
            ["blinkStrength 2.0", "EyeBlink ×8", "EyeWide ×0.8"],
        ),
    ]
    canvas = Image.new("RGB", (1920, 760), (8, 14, 24))
    draw = ImageDraw.Draw(canvas)
    draw.text((35, 18), "Face and motion controls — verified rendered examples", font=font(32, True), fill=(245, 248, 255))
    draw.text((35, 58), "Different avatars/configs are labeled; use each comparison only for the stated control effect", font=font(18), fill=(160, 178, 202))
    temp = WORK / "face-parameter-frames"
    temp.mkdir(parents=True, exist_ok=True)
    public = []
    for index, (label, video, notes) in enumerate(sources):
        frame = temp / f"frame-{index}.png"
        completed = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-y", "-loglevel", "error", "-i", str(video), "-vf", "select=eq(n\\,89)", "-frames:v", "1", str(frame)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-500:])
        image = Image.open(frame).convert("RGB").resize((640, 360), Image.Resampling.LANCZOS)
        x = index * 640
        canvas.paste(image, (x, 100))
        draw.text((x + 24, 480), label, font=font(25, True), fill=(245, 248, 255))
        for row, note in enumerate(notes):
            draw.text((x + 24, 525 + row * 35), f"• {note}", font=font(20), fill=(184, 203, 226))
        public.append({"label": label, "video": str(video), "video_sha256": sha256(video), "notes": notes})
    draw.text((35, 690), "Boundary: intensity metrics do not by themselves prove perceptual naturalness; extended tongue/head remain separate limitations.", font=font(18), fill=(232, 174, 86))
    path = RESULTS / "09-face-parameter-atlas.png"
    canvas.save(path, optimize=False)
    (RESULTS / "09-face-parameter-atlas.json").write_text(
        json.dumps({"schema_version": 1, "frame_index": 89, "sources": public, "atlas_sha256": sha256(path)}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def emotion_metahuman_render_atlas():
    ffmpeg = ROOT / ".tools/ffmpeg/bin/ffmpeg"
    cases = [
        (
            "NEUTRAL / AUTO EMOTION",
            "20260828-085258-hands-on-default-v30",
            ROOT / ".tools/audio2face3d/official-cli-runs/20260828-085258-hands-on-default-v30/taro-a2f-hands-on-default-v30-v30-diffusion-final.mp4",
            None,
        ),
        (
            "CONSTANT JOY 0.7",
            "20260828-101400-hands-on-emotion-joy-render-v1",
            ROOT / ".tools/audio2face3d/official-cli-runs/20260828-101400-hands-on-emotion-joy-render-v1/taro-a2f-hands-on-emotion-joy-render-v1-v30-diffusion-final.mp4",
            ROOT / ".tools/audio2face3d/official-cli-runs/20260828-101400-hands-on-emotion-joy-render-v1/effective-motion-config.json",
        ),
    ]
    frame_indices = [30, 60, 89]
    temp = WORK / "metahuman-emotion-render-frames"
    temp.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (1920, 900), (8, 14, 24))
    draw = ImageDraw.Draw(canvas)
    draw.text((28, 18), "Rendered MetaHuman emotion evidence — same Taro, audio, camera and render", font=font(28, True), fill=(245, 248, 255))
    records = []
    for row, (label, run_id, video, config) in enumerate(cases):
        for column, frame_index in enumerate(frame_indices):
            frame = temp / f"{row}-{frame_index}.png"
            completed = subprocess.run(
                [str(ffmpeg), "-hide_banner", "-y", "-loglevel", "error", "-i", str(video), "-vf", f"select=eq(n\\,{frame_index})", "-frames:v", "1", str(frame)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr[-500:])
            image = Image.open(frame).convert("RGB").resize((640, 360), Image.Resampling.LANCZOS)
            canvas.paste(image, (column * 640, 90 + row * 405))
            draw.text((column * 640 + 18, 102 + row * 405), f"{label} · F{frame_index:04d}", font=font(20, True), fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        records.append({
            "label": label,
            "run_id": run_id,
            "video": str(video),
            "video_sha256": sha256(video),
            "config": str(config) if config else None,
            "config_sha256": sha256(config) if config else None,
            "frames": frame_indices,
        })
    draw.text((28, 868), "Actual UE 5.6 / ACE 2.5 / Taro render frames; no generated pixels", font=font(17), fill=(160, 178, 202))
    path = RESULTS / "07-emotion-metahuman-render.png"
    canvas.save(path, optimize=False)
    (RESULTS / "07-emotion-metahuman-render.json").write_text(
        json.dumps({"schema_version": 1, "comparison_contract": "same avatar/audio/shot/render; constant emotion is the only requested control difference", "sources": records, "atlas_sha256": sha256(path)}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main():
    emotion_atlas()
    emotion_metahuman_render_atlas()
    face_parameter_atlas()


if __name__ == "__main__":
    main()
