#!/usr/bin/env python3
"""Truthful, isolated adapter for the unrelated LAM-A2E reference project.

LAM (Large Avatar Model for One-shot Animatable Gaussian Head) is not an
audio-to-face backbone. Its optional LAM-A2E demo can emit 52 ARKit values;
this adapter is reference-only and never substitutes for NVIDIA A2F-3D.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any


LAM_A2E_GIT_SHA = "02a703c3ea7d8e360eb43098eca85ee98a083529"
LAM_A2E_HF_REVISION = "0fe5f4dbb283ec7d9c01688681e6e4b6ac314858"
ADAPTER_SCOPE = "reference_artifacts_only"


def _load_motion():
    path = Path(__file__).with_name("a2f_motion.py")
    spec = importlib.util.spec_from_file_location("_a2f_motion_lam", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_motion = _load_motion()
A2F_NAMES = _motion.BLENDSHAPE_NAMES
# ARKit's canonical 52 includes TongueOut. NVIDIA A2F-3D extends that schema
# with 16 solver-specific tongue curves, which LAM-A2E cannot provide.
TONGUE_CURVES = tuple(
    name for name in A2F_NAMES if name.startswith("Tongue") and name != "TongueOut"
)
LAM_ARKIT_52 = tuple(name for name in A2F_NAMES if name not in TONGUE_CURVES)


def map_lam52_to_a2f(values: list[list[float]], fps: float) -> dict[str, Any]:
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be positive and finite")
    frames = []
    for frame_index, row in enumerate(values):
        if len(row) != 52:
            raise ValueError("LAM-A2E rows must contain exactly 52 ARKit values")
        by_name = {}
        for name, value in zip(LAM_ARKIT_52, row):
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError("LAM-A2E values must be finite")
            by_name[name] = parsed
        frames.append({
            "frame_index": frame_index,
            "time_seconds": frame_index / fps,
            "values": [by_name.get(name) for name in A2F_NAMES],
        })
    return {
        "schema_version": 1,
        "kind": "blendshape-reference-partial",
        "curve_names": list(A2F_NAMES),
        "availability": [name in LAM_ARKIT_52 for name in A2F_NAMES],
        "source": "LAM-A2E-reference-only",
        "provenance": {
            "git_sha": LAM_A2E_GIT_SHA,
            "hf_revision": LAM_A2E_HF_REVISION,
            "scope": ADAPTER_SCOPE,
        },
        "frames": frames,
    }


def build_lam_inference_command(
    python: Path, repo: Path, audio: Path, output_json: Path, checkpoint: Path,
) -> list[str]:
    return [
        str(python), str(Path(repo) / "inference.py"),
        "--config-file",
        str(Path(repo) / "configs/lam_audio2exp_config_streaming.py"),
        "--options",
        f"save_path={Path(output_json).parent}",
        f"weight={checkpoint}",
        f"audio_input={audio}",
        f"save_json_path={output_json}",
    ]
