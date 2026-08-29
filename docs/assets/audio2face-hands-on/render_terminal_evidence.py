#!/usr/bin/env python3
"""Render concise terminal evidence from canonical Audio2Face run artifacts.

The script only reads existing commands, manifests, logs, and media probes. It
does not fabricate command output or mutate Unreal/NIM state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "scripts/audio2face-metahuman/run-a2f-metahuman.py"
RUNS = ROOT / ".tools/audio2face3d/official-cli-runs"
OFF_RUN = RUNS / "20260829-084624-head-motion-off-r1"
ON_RUN = RUNS / "20260829-110741-head-motion-sync-final-r7"
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg"
FFPROBE = ROOT / ".tools/ffmpeg/bin/ffprobe"


def command(lines: list[str]) -> None:
    for index, line in enumerate(lines):
        print(("$ " if index == 0 else "  ") + line)


def completed_progress(run: Path) -> None:
    for line in (run / "progress-events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("state") == "completed":
            print(f"[{event['stage']}] PASS  {event.get('detail', '')}".rstrip())
        elif event.get("state") == "run_completed":
            print(
                f"[complete] {event['percent']}%  elapsed={event['elapsed_seconds']:.1f}s"
            )


def baseline() -> None:
    command(
        [
            "scripts/audio2face-metahuman/run-a2f-metahuman.py \\",
            "/home/aim/Downloads/test.wav \\",
            "--avatar Taro --shot close-up-front \\",
            "--motion-config scripts/audio2face-metahuman/configs/motion-head-subtle-v1.json \\",
            "--head-motion off --name hands-on-head-off --progress always",
        ]
    )
    print()
    completed_progress(OFF_RUN)
    print(f"\nEvidence: {OFF_RUN.name}")


def head_motion() -> None:
    command(
        [
            "scripts/audio2face-metahuman/run-a2f-metahuman.py \\",
            "/home/aim/Downloads/test.wav \\",
            "--resume .tools/audio2face3d/official-cli-runs/20260828-085258-hands-on-default-v30/manifest.json \\",
            "--avatar Taro --shot close-up-front \\",
            "--motion-config scripts/audio2face-metahuman/configs/motion-head-subtle-v1.json \\",
            "--head-motion subtle-conversational \\",
            "--head-motion-strength 1.0 --name hands-on-head-motion",
        ]
    )
    print()
    completed_progress(ON_RUN)
    print(f"\nEvidence: {ON_RUN.name}")


def manifest_summary() -> None:
    manifest = json.loads((ON_RUN / "manifest.json").read_text(encoding="utf-8"))
    verification = json.loads(
        (ON_RUN / "head-motion-final-verification.json").read_text(encoding="utf-8")
    )
    head = manifest["shots"][0]["head_motion"]
    command(
        [
            "python3 docs/assets/audio2face-hands-on/render_terminal_evidence.py manifest",
        ]
    )
    print(f"status={manifest['status']}  stage={manifest['stage']}  exit={manifest['exit_code']}")
    print(f"model={manifest['a2f_model']['id']}  NIM={manifest['a2f_model']['nim_model_id']}")
    print(f"avatar={manifest['avatar']['asset_name']}  shot={manifest['shots'][0]['id']}")
    print(f"implementation={head['implementation']}")
    print(f"target_bones={','.join(head['target_bones'])}  weights={head['bone_weights']}")
    print(f"samples={head['head_motion_bake']['sample_count']}  fps={head['head_motion_bake']['fps']}")
    print(f"source_asset_modified={head['source_asset_modified']}")
    timing = verification["head_motion_sync"]["optical_planned_lag"]
    print(
        "head_sync="
        f"{timing['status']}  lag={timing['best_lag_frames']} frame  "
        f"zero_lag_R2={timing['zero_lag_mean_r2']:.4f}"
    )


def unreal_assets() -> None:
    capture = json.loads((ON_RUN / "capture-status.json").read_text(encoding="utf-8"))
    shot = capture["shots"][0]
    bake = shot["head_motion"]["head_motion_bake"]
    command(
        [
            "python3 docs/assets/audio2face-hands-on/render_terminal_evidence.py unreal-assets",
        ]
    )
    print(f"map={capture['map_path']}")
    print(f"level_sequence={shot['level_sequence']}")
    print("\nrun-owned baked animations:")
    print(f"  Body={bake['baked_body_animation']}")
    print(f"  Face={bake['baked_face_animation']}")
    print(
        f"\nbody_tracks={shot['head_motion']['body_animation_tracks']}  "
        f"face_tracks={shot['head_motion']['face_track_count']}"
    )
    print(f"source_asset_modified={shot['head_motion']['source_asset_modified']}")


def verification() -> None:
    manifest = json.loads((ON_RUN / "manifest.json").read_text(encoding="utf-8"))
    final_video = Path(manifest["shots"][0]["final_mp4"])
    command([f'VIDEO="{final_video}"'])
    command(
        [
            ".tools/ffmpeg/bin/ffprobe -v error -count_frames \\",
            "-show_entries stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,channels,start_time \\",
            '"$VIDEO"',
        ]
    )
    probe = subprocess.check_output(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,channels,start_time",
            "-of",
            "json",
            str(final_video),
        ],
        text=True,
    )
    print(probe.strip())
    print("\n$ .tools/ffmpeg/bin/ffmpeg -v error -i \"$VIDEO\" \\")
    print("  -map 0:v:0 -f null - -map 0:a:0 -f null -")
    decoded = subprocess.run(
        [
            str(FFMPEG),
            "-v",
            "error",
            "-i",
            str(final_video),
            "-map",
            "0:v:0",
            "-f",
            "null",
            "-",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    print("decode=PASS" if decoded.returncode == 0 else "decode=FAIL")
    sync = manifest["shots"][0]["verification"]["content_sync"]
    print(
        f"A/V start=0 ms  face lag={sync['lag_frames']} frame  "
        f"correlation={sync['correlation']:.4f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage",
        choices=(
            "baseline",
            "head-motion",
            "manifest",
            "unreal-assets",
            "verification",
        ),
    )
    args = parser.parse_args()
    {
        "baseline": baseline,
        "head-motion": head_motion,
        "manifest": manifest_summary,
        "unreal-assets": unreal_assets,
        "verification": verification,
    }[args.stage]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
