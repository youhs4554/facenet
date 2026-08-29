#!/usr/bin/env python3
"""Crop the numbered hands-on screenshot set and write provenance metadata."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "screenshots/source"
OUTPUT = ROOT / "screenshots"
MANIFEST = OUTPUT / "screenshot-manifest.json"
RUN_R7 = "20260829-110741-head-motion-sync-final-r7"
RUN_OFF = "20260829-084624-head-motion-off-r1"


SCREENSHOTS = (
    {
        "stage": "CLI help and head-motion controls",
        "source": "01-cli-help-full.png",
        "output": "01-cli-help-head-motion.png",
        "crop": (0, 560, 1602, 1000),
        "surface": "canonical CLI --help",
        "command": "scripts/audio2face-metahuman/run-a2f-metahuman.py --help",
        "associated_run": None,
        "real_terminal_capture": True,
        "real_gui_capture": False,
        "deterministic_composition": False,
    },
    {
        "stage": "input, NIM, and GPU preflight",
        "source": "02-preflight-full.png",
        "output": "02-runtime-preflight.png",
        "crop": (0, 27, 1602, 330),
        "surface": "read-only terminal preflight",
        "command": "ffprobe + docker ps + nvidia-smi",
        "associated_run": None,
        "real_terminal_capture": True,
        "real_gui_capture": False,
        "deterministic_composition": False,
    },
    {
        "stage": "baseline facial-animation command and completed stages",
        "source": "03-baseline-progress-full.png",
        "output": "03-baseline-progress.png",
        "crop": (0, 27, 1722, 500),
        "surface": "terminal replay of machine-readable progress events",
        "command": "render_terminal_evidence.py baseline",
        "associated_run": RUN_OFF,
        "real_terminal_capture": True,
        "real_gui_capture": False,
        "deterministic_composition": True,
    },
    {
        "stage": "head-motion command and completed stages",
        "source": "04-head-motion-progress-full.png",
        "output": "04-head-motion-progress.png",
        "crop": (0, 27, 1818, 555),
        "surface": "terminal replay of machine-readable progress events",
        "command": "render_terminal_evidence.py head-motion",
        "associated_run": RUN_R7,
        "real_terminal_capture": True,
        "real_gui_capture": False,
        "deterministic_composition": True,
    },
    {
        "stage": "head-motion success and bone-authoring summary",
        "source": "05-head-motion-manifest-full.png",
        "output": "05-head-motion-manifest.png",
        "crop": (0, 27, 1722, 265),
        "surface": "terminal projection of manifest and final verification JSON",
        "command": "render_terminal_evidence.py manifest",
        "associated_run": RUN_R7,
        "real_terminal_capture": True,
        "real_gui_capture": False,
        "deterministic_composition": True,
    },
    {
        "stage": "run-owned Unreal FinalSequence, viewport, and animation tracks",
        "source": "06-unreal-run-owned-sequence-full.png",
        "output": "06-unreal-run-owned-sequence.png",
        "crop": (0, 0, 1608, 1020),
        "surface": "UE 5.6 VNC window with r7 FinalSequence at frame 60",
        "command": "UnrealEditor -DisablePlugins=Bridge,Fab + per-process CEF/restore overrides",
        "associated_run": RUN_R7,
        "real_terminal_capture": False,
        "real_gui_capture": True,
        "deterministic_composition": False,
    },
    {
        "stage": "actual OFF/ON MetaHuman render comparison",
        "source": "07-head-motion-off-on-contact-sheet-full.png",
        "output": "07-head-motion-off-on-result.png",
        "crop": (0, 95, 1920, 995),
        "surface": "deterministic contact sheet of actual MRQ pixels",
        "command": "existing r7 head-motion-off-on-contact-sheet.png",
        "associated_run": RUN_R7,
        "real_terminal_capture": False,
        "real_gui_capture": False,
        "deterministic_composition": True,
    },
    {
        "stage": "ffprobe, decode, A/V, and facial-content verification",
        "source": "08-verification-full.png",
        "output": "08-video-verification.png",
        "crop": (0, 27, 1722, 860),
        "surface": "project-local ffprobe/ffmpeg terminal verification",
        "command": "render_terminal_evidence.py verification",
        "associated_run": RUN_R7,
        "real_terminal_capture": True,
        "real_gui_capture": False,
        "deterministic_composition": False,
    },
    {
        "stage": "clean GUI review of actual OFF/ON result",
        "source": "09-off-on-viewer-full.png",
        "output": "09-off-on-viewer.png",
        "crop": (0, 0, 1640, 910),
        "surface": "GNOME Image Viewer window on VNC DISPLAY=:1",
        "command": "eog r7/head-motion-off-on-contact-sheet.png",
        "associated_run": RUN_R7,
        "real_terminal_capture": False,
        "real_gui_capture": True,
        "deterministic_composition": False,
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    for item in SCREENSHOTS:
        source = SOURCE / item["source"]
        output = OUTPUT / item["output"]
        if not source.is_file():
            raise FileNotFoundError(source)
        with Image.open(source) as image:
            image.load()
            left, top, right, bottom = item["crop"]
            if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                raise ValueError(f"crop is outside source image: {item['source']}")
            cropped = image.crop(item["crop"])
            framed = ImageOps.expand(cropped, border=16, fill=(18, 18, 18))
            framed.save(output, optimize=True)
            source_dimensions = [image.width, image.height]
            output_dimensions = [framed.width, framed.height]
        timestamp = datetime.fromtimestamp(
            source.stat().st_mtime, tz=ZoneInfo("Asia/Seoul")
        ).isoformat()
        records.append(
            {
                "semantic_stage": item["stage"],
                "source_capture_path": str(source.relative_to(ROOT)),
                "source_sha256": sha256(source),
                "source_dimensions": source_dimensions,
                "capture_timestamp_kst": timestamp,
                "terminal_command_or_gui_surface": item["command"],
                "surface": item["surface"],
                "crop_rectangle_xywh": [
                    item["crop"][0],
                    item["crop"][1],
                    item["crop"][2] - item["crop"][0],
                    item["crop"][3] - item["crop"][1],
                ],
                "output_path": str(output.relative_to(ROOT)),
                "output_dimensions": output_dimensions,
                "output_sha256": sha256(output),
                "real_terminal_capture": item["real_terminal_capture"],
                "real_gui_capture": item["real_gui_capture"],
                "deterministic_composition": item["deterministic_composition"],
                "associated_run": item["associated_run"],
                "generative_pixels_used": False,
                "empirical_avatar_pixels_altered": False,
            }
        )
    payload = {
        "schema_version": 1,
        "generated_at_kst": datetime.now(tz=ZoneInfo("Asia/Seoul")).isoformat(),
        "generator": str(Path(__file__).relative_to(ROOT)),
        "disclosure": (
            "All screenshots use real terminal/GUI or actual MRQ pixels. "
            "Only cropping and a uniform external border were applied; no "
            "generative pixels or avatar beautification were used."
        ),
        "resolved_gui_capture": {
            "status": "pass",
            "root_cause": (
                "Bridge/Fab restored a CEF surface whose Linux ANGLE Vulkan "
                "initialization failed; force-closing the child window caused "
                "the prior X11/LocalizableMessage shutdown failure."
            ),
            "safe_process_overrides": [
                "-DisablePlugins=Bridge,Fab",
                "-ini:Engine:[SystemSettings]:r.CEFGPUAcceleration=0",
                "-ini:EditorPerProjectUserSettings:[/Script/UnrealEd.EditorLoadingSavingSettings]:RestoreOpenAssetTabsOnRestart=NeverRestore",
            ],
            "evidence_log_path": ".tools/audio2face-metahuman/KairosSample/Saved/Logs/KairosSample.log",
            "observed_at_kst": "2026-08-29T18:43:31+09:00",
            "source_assets_saved": False,
            "editor_exit": "QUIT_EDITOR graceful exit",
        },
        "superseded_attempts": [
            {
                "path": None,
                "capture_retained": False,
                "evidence_log_path": ".tools/audio2face-metahuman/KairosSample/Saved/Logs/KairosSample.log",
                "observed_at_kst": "2026-08-29T17:40:55+09:00",
                "reason": (
                    "UE 5.6 CEF/ANGLE Vulkan initialization produced a black "
                    "viewport and the editor later exited with SIGSEGV; this "
                    "capture was not retained or presented as successful GUI evidence."
                ),
            }
        ],
        "screenshots": records,
    }
    MANIFEST.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(records)} screenshots and {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
