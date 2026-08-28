#!/usr/bin/env python3
"""Generate reproducible Audio2Face hands-on introduction figure candidates."""

from pathlib import Path
import shutil

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle


HERE = Path(__file__).resolve().parent
CANDIDATES = HERE / "../../../figures/candidates/audio2face-hands-on"
FINAL = HERE / "figures"

FONT = "/home/aim/.local/share/fonts/NanumGothic-Regular.ttf"
BOLD = "/home/aim/.local/share/fonts/NanumGothic-Bold.ttf"

mpl.rcParams.update(
    {
        "font.family": "NanumGothic",
        "font.sans-serif": ["NanumGothic", "Noto Sans CJK KR", "DejaVu Sans"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 11,
        "figure.facecolor": "white",
    }
)

INK = "#152235"
MUTED = "#607086"
BLUE = "#2775CA"
TEAL = "#17A398"
AMBER = "#E49B2F"
GREEN = "#2E9D62"
LIGHT = "#F3F7FB"
LINE = "#C7D3E1"


def box(ax, x, y, w, h, title, subtitle="", color=BLUE, *, fs=12):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=1.5,
        edgecolor=color,
        facecolor="white",
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h * 0.59, title, ha="center", va="center", fontsize=fs,
            fontweight="bold", color=INK, fontproperties=mpl.font_manager.FontProperties(fname=BOLD))
    if subtitle:
        ax.text(x + w / 2, y + h * 0.27, subtitle, ha="center", va="center",
                fontsize=max(8, fs - 3), color=MUTED,
                fontproperties=mpl.font_manager.FontProperties(fname=FONT))
    return patch


def arrow(ax, start, end, color=MUTED, label=None, curve=0.0):
    item = FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=15, linewidth=1.8,
        color=color, connectionstyle=f"arc3,rad={curve}", zorder=2,
    )
    ax.add_patch(item)
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx, my + 0.035, label, ha="center", va="bottom", fontsize=8.5,
                color=color, fontproperties=mpl.font_manager.FontProperties(fname=FONT))


def setup(title, subtitle):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    ax.text(0.04, 0.93, title, fontsize=24, fontweight="bold", color=INK,
            fontproperties=mpl.font_manager.FontProperties(fname=BOLD))
    ax.text(0.04, 0.88, subtitle, fontsize=12, color=MUTED,
            fontproperties=mpl.font_manager.FontProperties(fname=FONT))
    return fig, ax


def save(fig, name):
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    fig.savefig(CANDIDATES / f"{name}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(
        CANDIDATES / f"{name}.tiff",
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    fig.savefig(CANDIDATES / f"{name}.svg", bbox_inches="tight", facecolor="white")
    fig.savefig(CANDIDATES / f"{name}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def concept_linear():
    fig, ax = setup(
        "Audio to animated MetaHuman — one reusable CLI journey",
        "Choose the avatar, camera, emotion and motion for each run",
    )
    titles = ["Audio + choices", "Audio-driven face", "Selected MetaHuman", "Camera + render", "Video + artifacts"]
    subtitles = ["avatar · camera · emotion", "facial motion", "animation capture", "frames + original audio", "video · report · diagnostics"]
    colors = [MUTED, BLUE, TEAL, AMBER, GREEN]
    xs = [0.04, 0.23, 0.42, 0.61, 0.80]
    for i, (x, title, subtitle, color) in enumerate(zip(xs, titles, subtitles, colors)):
        box(ax, x, 0.47, 0.15, 0.20, title, subtitle, color, fs=12)
        ax.add_patch(Circle((x + 0.075, 0.72), 0.025, color=color, alpha=0.95))
        ax.text(x + 0.075, 0.72, str(i + 1), ha="center", va="center", color="white",
                fontsize=10, fontweight="bold")
        if i < 4:
            arrow(ax, (x + 0.15, 0.57), (xs[i + 1], 0.57), colors[i + 1])
    ax.text(0.31, 0.37, "audio → facial motion", ha="center", color=BLUE,
            fontsize=13, fontweight="bold")
    ax.text(0.70, 0.37, "render → reusable results", ha="center", color=TEAL,
            fontsize=13, fontweight="bold")
    ax.text(0.50, 0.17, "No training · source assets preserved · repeatable run", ha="center",
            fontsize=13, color=INK,
            bbox={"boxstyle": "round,pad=0.5", "fc": LIGHT, "ec": LINE})
    save(fig, "routeA-concept-linear")


def concept_hub():
    fig, ax = setup(
        "Audio2Face CLI가 재현성을 만드는 방법",
        "한 manifest가 입력·모델·motion·avatar·camera·codec 증거를 묶는다",
    )
    box(ax, 0.39, 0.42, 0.22, 0.22, "run-a2f-metahuman.py", "preflight · orchestration · verification", BLUE, fs=14)
    nodes = [
        (0.07, 0.60, "오디오", "input SHA-256", MUTED),
        (0.07, 0.25, "Motion config", "face · emotion · intensity", TEAL),
        (0.72, 0.65, "NVIDIA NIM", "v3.0 · multi_v3.2", BLUE),
        (0.72, 0.39, "UE + MetaHuman", "ACE · Take Recorder · MRQ", AMBER),
        (0.72, 0.13, "검증 산출물", "MP4 · JSON/CSV · triptych", GREEN),
    ]
    for x, y, title, subtitle, color in nodes:
        box(ax, x, y, 0.21, 0.14, title, subtitle, color, fs=12)
        if x < 0.5:
            arrow(ax, (x + 0.21, y + 0.07), (0.39, 0.50), color)
        else:
            arrow(ax, (0.61, 0.53), (x, y + 0.07), color)
    ax.text(0.50, 0.29, "strict lineage gate", ha="center", color=INK, fontsize=11,
            bbox={"boxstyle": "round,pad=0.4", "fc": LIGHT, "ec": LINE})
    save(fig, "routeA-concept-hub")


def architecture_lanes():
    fig, ax = setup(
        "How the Audio2Face MetaHuman CLI works",
        "A novice-friendly path from input choices to checked results",
    )
    titles = ["1. Choose input", "2. Generate face motion", "3. Animate MetaHuman", "4. Render video", "5. Check results"]
    subtitles = ["audio · avatar · camera · emotion", "NVIDIA Audio2Face", "NVIDIA ACE + Unreal Engine", "frames + original audio", "video · report · diagnostics"]
    xs = [0.03, 0.225, 0.42, 0.615, 0.81]
    colors = [MUTED, BLUE, TEAL, AMBER, GREEN]
    for x, title, subtitle, color in zip(xs, titles, subtitles, colors):
        box(ax, x, 0.39, 0.16, 0.25, title, subtitle, color, fs=11)
    for index in range(4):
        arrow(ax, (xs[index] + 0.16, 0.515), (xs[index + 1], 0.515), colors[index + 1])
    ax.text(0.50, 0.16, "Setup may need VNC once · repeat runs use the CLI", ha="center", fontsize=11,
            color=MUTED)
    save(fig, "routeA-architecture-lanes")


def architecture_stack():
    fig, ax = setup(
        "Audio2Face CLI — 검증 가능한 artifact stack",
        "각 층의 output이 다음 층의 input이며 SHA·timecode·frame gate로 연결된다",
    )
    layers = [
        (0.16, 0.67, 0.68, "CLI control", "avatar · shot · motion · emotion · render options", MUTED),
        (0.20, 0.53, 0.60, "NVIDIA inference", "v3 multi_v3.2 / A2F-68 / emotion tracks", BLUE),
        (0.24, 0.39, 0.52, "ACE capture", "MetaHuman Face_AnimBP / Take Recorder / one face track", TEAL),
        (0.28, 0.25, 0.44, "MRQ render", "camera preset or custom transform / 109 PNG frames", AMBER),
        (0.32, 0.11, 0.36, "Verified delivery", "H.264 + AAC / triptych / manifest", GREEN),
    ]
    for x, y, w, title, subtitle, color in layers:
        box(ax, x, y, w, 0.095, title, subtitle, color, fs=12)
    for y1, y2 in [(0.67, 0.625), (0.53, 0.485), (0.39, 0.345), (0.25, 0.205)]:
        arrow(ax, (0.50, y1), (0.50, y2), MUTED)
    ax.text(0.06, 0.12, "GPU1\nA4500\nNIM", ha="center", va="center", fontsize=11, color=BLUE,
            bbox={"boxstyle": "round,pad=0.5", "fc": "white", "ec": BLUE})
    ax.text(0.91, 0.36, "GPU0\nRTX 5000\nUE/MRQ", ha="center", va="center", fontsize=11, color=AMBER,
            bbox={"boxstyle": "round,pad=0.5", "fc": "white", "ec": AMBER})
    save(fig, "routeA-architecture-stack")


def main():
    concept_linear()
    concept_hub()
    architecture_lanes()
    architecture_stack()
    FINAL.mkdir(parents=True, exist_ok=True)
    # Route A remains the authoritative semantic blueprint. Final generated
    # bitmaps are selected only after the separate Route B semantic audit.
    shutil.copy2(
        CANDIDATES / "routeA-concept-linear.png",
        FINAL / "concept-overview-routeA-blueprint.png",
    )
    shutil.copy2(
        CANDIDATES / "routeA-architecture-lanes.png",
        FINAL / "cli-architecture-routeA-blueprint.png",
    )


if __name__ == "__main__":
    main()
