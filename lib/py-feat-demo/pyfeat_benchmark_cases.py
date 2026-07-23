"""Per-sample ranking contracts for benchmark case studies."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import numpy as np
import numpy.typing as npt


PointMatrix = npt.NDArray[np.float64]
CaseType = TypeVar("CaseType")


class CaseSelectionError(Exception):
    """Raised when a requested best/worst selection cannot be formed."""

    def __init__(self, *, required: int, found: int) -> None:
        self.required = required
        self.found = found
        super().__init__(f"case selection requires {required} records; found {found}")


class CaseInputError(Exception):
    """Raised when per-sample truth and prediction values cannot be scored."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class AFLFPCase:
    key: str
    subject: str
    movement: str
    image_path: Path
    face_score: float
    nme: float
    truth: PointMatrix
    prediction: PointMatrix


@dataclass(frozen=True, slots=True)
class AFLFPSelection:
    best: tuple[AFLFPCase, ...]
    worst: tuple[AFLFPCase, ...]


@dataclass(frozen=True, slots=True)
class DISFACaseScore:
    agreement_count: int
    mismatch_count: int
    probability_mae: float


@dataclass(frozen=True, slots=True)
class DISFACase:
    key: str
    subject: str
    frame_number: int
    image_path: Path
    face_score: float
    agreement_count: int
    mismatch_count: int
    probability_mae: float
    truth_intensities: tuple[int, ...]
    predictions: tuple[float, ...]
    landmarks: PointMatrix


@dataclass(frozen=True, slots=True)
class DISFASelection:
    best: tuple[DISFACase, ...]
    worst: tuple[DISFACase, ...]


def score_disfa_case(
    truth_intensities: Sequence[int], predictions: Sequence[float]
) -> DISFACaseScore:
    if len(truth_intensities) == 0 or len(truth_intensities) != len(predictions):
        raise CaseInputError(
            "DISFA truth and prediction must be non-empty and have equal length"
        )
    truth = np.asarray(truth_intensities, dtype=np.float64)
    probability = np.asarray(predictions, dtype=np.float64)
    if not np.isfinite(truth).all() or not np.isfinite(probability).all():
        raise CaseInputError("DISFA case scores must be finite")
    binary_truth = truth >= 2.0
    binary_prediction = probability >= 0.5
    mismatch_count = int(np.count_nonzero(binary_truth != binary_prediction))
    return DISFACaseScore(
        agreement_count=len(truth_intensities) - mismatch_count,
        mismatch_count=mismatch_count,
        probability_mae=float(
            np.mean(np.abs(binary_truth.astype(np.float64) - probability))
        ),
    )


def select_aflfp_extremes(
    cases: Sequence[AFLFPCase], count: int
) -> AFLFPSelection:
    _require_extremes(cases, count)
    ordered = sorted(cases, key=lambda case: (case.nme, case.key))
    return AFLFPSelection(
        best=tuple(ordered[:count]), worst=tuple(reversed(ordered[-count:]))
    )


def select_disfa_extremes(
    cases: Sequence[DISFACase], count: int
) -> DISFASelection:
    _require_extremes(cases, count)
    ordered = sorted(
        cases,
        key=lambda case: (case.mismatch_count, case.probability_mae, case.key),
    )
    return DISFASelection(
        best=tuple(ordered[:count]), worst=tuple(reversed(ordered[-count:]))
    )


def _require_extremes(cases: Sequence[CaseType], count: int) -> None:
    required = count * 2
    if count <= 0 or len(cases) < required:
        raise CaseSelectionError(required=required, found=len(cases))
