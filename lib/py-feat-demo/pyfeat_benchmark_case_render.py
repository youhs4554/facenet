"""Report-ready raster rendering for benchmark case selections."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from PIL import Image

from pyfeat_benchmark_cases import (
    AFLFPSelection,
    DISFASelection,
    PointMatrix,
)


DISFA_AUS: Final = ("AU01", "AU02", "AU04", "AU05", "AU06", "AU09",
                    "AU12", "AU15", "AU17", "AU20", "AU25", "AU26")
TEAL: Final = "#00A6A6"
CORAL: Final = "#EF6F6C"
NAVY: Final = "#17324D"
KOREAN_FONT: Final = FontProperties(family="Noto Sans CJK KR")


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
