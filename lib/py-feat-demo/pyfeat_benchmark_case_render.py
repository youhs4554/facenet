"""Report-ready raster rendering for benchmark case selections."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from PIL import Image

from pyfeat_benchmark_cases import (
    TARGET_AU_INDICES,
    AFLFPCase,
    AFLFPSelection,
    DISFACase,
    DISFASelection,
    PointMatrix,
)

DISFA_AUS: Final = ("AU01", "AU02", "AU04", "AU05", "AU06", "AU09",
                    "AU12", "AU15", "AU17", "AU20", "AU25", "AU26")
TEAL: Final = "#00A6A6"
CORAL: Final = "#EF6F6C"
NAVY: Final = "#17324D"
KOREAN_FONT: Final = FontProperties(family="Noto Sans CJK KR")
MONO_FONT: Final = FontProperties(family="DejaVu Sans Mono")
ORAL_JAW_INDICES: Final = np.r_[0:17, 48:68]


def render_aflfp_cases(selection: AFLFPSelection, output_path: Path) -> None:
    figure, axes = _case_canvas()
    cases = (*selection.best, *selection.worst)
    for index, (axis, case) in enumerate(zip(axes, cases, strict=True)):
        _draw_face(axis, case.image_path, np.vstack((case.truth, case.prediction)))
        axis.scatter(
            case.truth[:, 0], case.truth[:, 1], s=20, facecolors="none",
            edgecolors=TEAL, linewidths=1.2, label="GT 68점",
        )
        axis.scatter(
            case.prediction[:, 0], case.prediction[:, 1], s=20, marker="x",
            color=CORAL, linewidths=1.1, label="py-feat 68점",
        )
        rank = index + 1 if index < 2 else index - 1
        group = "BEST" if index < 2 else "WORST"
        axis.set_title(
            f"{group} #{rank}  |  NME {case.nme:.4f}\n"
            f"subject {case.subject} · {case.movement} · FaceScore {case.face_score:.3f}",
            fontproperties=KOREAN_FONT, fontsize=11, color=NAVY, loc="left",
        )
        axis.legend(loc="lower right", prop=KOREAN_FONT, fontsize=8,
                    framealpha=0.86)
    _finish(figure, output_path,
            "AFLFP 사례 분석 · 낮은 NME가 더 정확함 · seed 42 표본 내 상·하위 2건")


def render_disfa_cases(selection: DISFASelection, output_path: Path) -> None:
    figure, axes = _case_canvas()
    cases = (*selection.best, *selection.worst)
    for index, (axis, case) in enumerate(zip(axes, cases, strict=True)):
        _draw_face(axis, case.image_path, case.landmarks)
        truth_positive = _positive_aus(case.truth_intensities, 2.0)
        predicted_positive = _positive_aus(case.predictions, 0.5)
        mismatched = sorted(set(truth_positive) ^ set(predicted_positive))
        rank = index + 1 if index < 2 else index - 1
        group = "BEST" if index < 2 else "WORST"
        axis.set_title(
            f"{group} #{rank}  |  불일치 {case.mismatch_count}/12 · "
            f"확률 MAE {case.probability_mae:.3f}\n"
            f"{case.subject} frame {case.frame_number} · FaceScore {case.face_score:.3f}",
            fontproperties=KOREAN_FONT, fontsize=11, color=NAVY, loc="left",
        )
        axis.text(
            0.02, 0.02,
            "GT+  " + _au_text(truth_positive) + "\n"
            "예측+ " + _au_text(predicted_positive) + "\n"
            "불일치 " + _au_text(tuple(mismatched)),
            transform=axis.transAxes, va="bottom", ha="left",
            fontproperties=KOREAN_FONT, fontsize=8.5, color="white",
            bbox={"boxstyle": "round,pad=0.45", "facecolor": NAVY,
                  "edgecolor": "none", "alpha": 0.84},
        )
    _finish(figure, output_path,
            "DISFA 사례 분석 · AU 이진 불일치 수 우선, 확률 MAE 동률 해소 · seed 42 표본")


def render_aflfp_target_cases(
    cases: Sequence[AFLFPCase], output_path: Path
) -> None:
    """Render oral opening, closure, and lateral-movement landmark cases."""
    if len(cases) != 4:
        raise ValueError(f"expected four AFLFP target cases; found {len(cases)}")
    figure, axes = _case_canvas()
    for axis, case in zip(axes, cases, strict=True):
        points = np.vstack((case.truth, case.prediction))
        _draw_face(axis, case.image_path, points)
        axis.scatter(
            case.truth[:, 0], case.truth[:, 1], s=8, facecolors="none",
            edgecolors="#64748B", linewidths=0.7, alpha=0.65,
        )
        axis.scatter(
            case.prediction[:, 0], case.prediction[:, 1], s=8, marker="x",
            color="#94A3B8", linewidths=0.7, alpha=0.65,
        )
        axis.scatter(
            case.truth[ORAL_JAW_INDICES, 0], case.truth[ORAL_JAW_INDICES, 1],
            s=28, facecolors="none", edgecolors=TEAL, linewidths=1.4,
            label="GT oral/jaw",
        )
        axis.scatter(
            case.prediction[ORAL_JAW_INDICES, 0],
            case.prediction[ORAL_JAW_INDICES, 1],
            s=28, marker="x", color=CORAL, linewidths=1.2,
            label="Py-Feat oral/jaw",
        )
        aperture, corner_delta = _oral_geometry(case.prediction)
        axis.set_title(
            f"{case.movement.upper()}  |  NME {case.nme * 100:.2f}%\n"
            f"aperture {aperture * 100:.2f}%  ·  "
            f"lip-corner Δy {corner_delta * 100:.2f}%",
            fontsize=10.5, color=NAVY, loc="left",
        )
        axis.legend(loc="lower right", fontsize=7.5, framealpha=0.88)
    _finish(
        figure,
        output_path,
        "Target-aligned AFLFP cases · mouth opening, closure, and lateral asymmetry",
    )


def render_disfa_target_cases(
    cases: Sequence[DISFACase], output_path: Path
) -> None:
    """Render lower-face crops for AU12, AU25, AU26, and an inactive reference."""
    if len(cases) != 4:
        raise ValueError(f"expected four DISFA target cases; found {len(cases)}")
    figure, axes = _case_canvas()
    panel_names = ("AU12 high intensity", "AU25 high intensity",
                   "AU26 high intensity", "inactive reference")
    for axis, case, panel_name in zip(axes, cases, panel_names, strict=True):
        _draw_disfa_target_panel(axis, case, panel_name)
    _finish(
        figure,
        output_path,
        "Target-aligned DISFA cases · GT intensity (0–5) vs Py-Feat probability (0–1)",
    )


def render_disfa_target_strip(
    cases: Sequence[DISFACase], output_path: Path
) -> None:
    """Render the same DISFA cases as a compact full-width paper strip."""
    if len(cases) != 4:
        raise ValueError(f"expected four DISFA target cases; found {len(cases)}")
    figure, axes_array = plt.subplots(1, 4, figsize=(15, 4), dpi=160)
    figure.patch.set_facecolor("#F5F7F9")
    panel_names = ("AU12 high intensity", "AU25 high intensity",
                   "AU26 high intensity", "inactive reference")
    for axis, case, panel_name in zip(
        tuple(axes_array), cases, panel_names, strict=True
    ):
        _draw_disfa_target_panel(axis, case, panel_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.suptitle(
        "Target-aligned DISFA cases · GT intensity (0–5) vs Py-Feat probability (0–1)",
        fontproperties=KOREAN_FONT,
        fontsize=15,
        fontweight="bold",
        color=NAVY,
        y=0.975,
    )
    figure.subplots_adjust(
        left=0.015, right=0.992, bottom=0.035, top=0.84, wspace=0.08
    )
    figure.savefig(output_path, dpi=160, facecolor=figure.get_facecolor())
    plt.close(figure)


def _draw_disfa_target_panel(
    axis: Axes, case: DISFACase, panel_name: str
) -> None:
    _draw_lower_face(axis, case.image_path, case.landmarks)
    axis.scatter(
        case.landmarks[0:17, 0], case.landmarks[0:17, 1],
        s=16, facecolors="none", edgecolors="#94A3B8", linewidths=0.9,
    )
    axis.scatter(
        case.landmarks[48:68, 0], case.landmarks[48:68, 1],
        s=24, facecolors="none", edgecolors=TEAL, linewidths=1.2,
    )
    axis.set_title(panel_name, fontsize=11, color=NAVY, loc="left")
    axis.text(
        0.02,
        0.02,
        _target_au_text(case),
        transform=axis.transAxes,
        va="bottom",
        ha="left",
        fontproperties=MONO_FONT,
        fontsize=8.2,
        color="white",
        bbox={
            "boxstyle": "round,pad=0.45",
            "facecolor": NAVY,
            "edgecolor": "none",
            "alpha": 0.88,
        },
    )


def _case_canvas() -> tuple[Figure, tuple[Axes, ...]]:
    figure, axes_grid = plt.subplots(2, 2, figsize=(12, 10), dpi=160)
    figure.patch.set_facecolor("#F5F7F9")
    return figure, tuple(axes_grid.ravel())


def _draw_face(axis: Axes, image_path: Path, points: PointMatrix) -> None:
    with Image.open(image_path) as source:
        image = np.asarray(source.convert("RGB"))
    axis.imshow(image)
    x_min, y_min = np.min(points, axis=0)
    x_max, y_max = np.max(points, axis=0)
    width = max(float(x_max - x_min), 1.0)
    height = max(float(y_max - y_min), 1.0)
    padding = max(width, height) * 0.35
    axis.set_xlim(max(0.0, x_min - padding), min(image.shape[1], x_max + padding))
    axis.set_ylim(min(image.shape[0], y_max + padding), max(0.0, y_min - padding))
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_color("#D4DEE5")
        spine.set_linewidth(1.2)


def _draw_lower_face(axis: Axes, image_path: Path, points: PointMatrix) -> None:
    with Image.open(image_path) as source:
        image = np.asarray(source.convert("RGB"))
    axis.imshow(image)
    x_min = float(np.min(points[:, 0]))
    x_max = float(np.max(points[:, 0]))
    lower_face_indices = np.r_[31:36, 48:68]
    y_min = float(np.min(points[lower_face_indices, 1]))
    y_max = float(np.max(points[:, 1]))
    width = max(x_max - x_min, 1.0)
    height = max(y_max - y_min, 1.0)
    axis.set_xlim(
        max(0.0, x_min - width * 0.12),
        min(image.shape[1], x_max + width * 0.12),
    )
    axis.set_ylim(
        min(image.shape[0], y_max + height * 0.12),
        max(0.0, y_min - height * 0.08),
    )
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_color("#D4DEE5")
        spine.set_linewidth(1.2)


def _oral_geometry(points: PointMatrix) -> tuple[float, float]:
    x_min, y_min = np.min(points, axis=0)
    x_max, y_max = np.max(points, axis=0)
    scale = np.sqrt(max(float((x_max - x_min) * (y_max - y_min)), 1.0))
    aperture = float(np.linalg.norm(points[62] - points[66])) / scale
    corner_delta = abs(float(points[48, 1] - points[54, 1])) / scale
    return aperture, corner_delta


def _target_au_text(case: DISFACase) -> str:
    rows = ["       GT/5  Py-Feat"]
    for au, index in TARGET_AU_INDICES:
        rows.append(
            f"AU{au:02d}   {case.truth_intensities[index]:>1}     "
            f"{case.predictions[index]:.2f}"
        )
    return "\n".join(rows)


def _positive_aus(values: tuple[int, ...] | tuple[float, ...], threshold: float) -> tuple[str, ...]:
    return tuple(au for au, value in zip(DISFA_AUS, values, strict=True)
                 if value >= threshold)


def _au_text(aus: tuple[str, ...]) -> str:
    return ", ".join(aus) if aus else "없음"


def _finish(figure: Figure, output_path: Path, title: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.suptitle(title, fontproperties=KOREAN_FONT, fontsize=15,
                    fontweight="bold", color=NAVY, y=0.985)
    figure.subplots_adjust(left=0.035, right=0.985, bottom=0.035,
                           top=0.92, wspace=0.10, hspace=0.22)
    figure.savefig(output_path, dpi=160, facecolor=figure.get_facecolor())
    plt.close(figure)
