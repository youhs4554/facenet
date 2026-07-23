"""Pure accuracy metrics for raw py-feat dataset benchmarks."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class MetricInputError(Exception):
    metric: str
    detail: str

    def __str__(self) -> str:
        return f"{self.metric}: {self.detail}"


@dataclass(frozen=True, slots=True)
class LandmarkSummary:
    requested_samples: int
    processed_samples: int
    scored_samples: int
    detection_rate: float
    nme_mean: float
    nme_std: float
    nme_median: float
    nme_p90: float
    elapsed_s: float
    fps: float


@dataclass(frozen=True, slots=True)
class AUMetric:
    au: str
    f1: float
    icc: float
    evaluated_samples: int
    support: int
    prevalence: float
    truth_positive_count: int
    predicted_positive_count: int


@dataclass(frozen=True, slots=True)
class AUSummary:
    au_metrics: tuple[AUMetric, ...]
    macro_f1: float
    macro_icc: float


def landmark_nme(
    prediction: npt.NDArray[np.float64],
    truth: npt.NDArray[np.float64],
) -> float:
    """Compute AFLFP paper NME using sqrt(GT bounding-box area)."""
    if prediction.shape != truth.shape or truth.ndim != 2 or truth.shape[1] != 2:
        raise MetricInputError(
            metric="landmark_nme",
            detail=f"prediction {prediction.shape} and truth {truth.shape} must be Nx2",
        )
    width = float(np.ptp(truth[:, 0]))
    height = float(np.ptp(truth[:, 1]))
    normalization = math.sqrt(width * height)
    if normalization <= 0.0:
        raise MetricInputError(
            metric="landmark_nme",
            detail="ground-truth bounding box has zero area",
        )
    point_errors = np.linalg.norm(prediction - truth, axis=1)
    return float(point_errors.mean() / normalization)


def summarize_landmark_scores(
    scores: Sequence[float | None],
    elapsed_s: float,
) -> LandmarkSummary:
    """Summarize valid NME values while retaining misses in detection rate."""
    if elapsed_s <= 0.0:
        raise MetricInputError(
            metric="landmark_summary", detail="elapsed_s must be positive"
        )
    valid = np.asarray(
        [score for score in scores if score is not None], dtype=np.float64
    )
    if valid.size == 0:
        raise MetricInputError(
            metric="landmark_summary", detail="no landmarks were scored"
        )
    processed = len(scores)
    return LandmarkSummary(
        requested_samples=processed,
        processed_samples=processed,
        scored_samples=int(valid.size),
        detection_rate=float(valid.size / processed),
        nme_mean=float(valid.mean()),
        nme_std=float(valid.std()),
        nme_median=float(np.median(valid)),
        nme_p90=float(np.quantile(valid, 0.9)),
        elapsed_s=elapsed_s,
        fps=float(processed / elapsed_s),
    )


def summarize_au_scores(
    truth: Mapping[str, npt.ArrayLike],
    prediction: Mapping[str, npt.ArrayLike],
) -> AUSummary:
    """Summarize DISFA AUs using truth >=2 and prediction >=0.5."""
    common = sorted(set(truth) & set(prediction))
    if not common:
        raise MetricInputError(metric="au_summary", detail="no common AU columns")
    au_metrics: list[AUMetric] = []
    for au in common:
        truth_values = np.asarray(truth[au], dtype=np.float64)
        predicted_values = np.asarray(prediction[au], dtype=np.float64)
        if truth_values.ndim != 1 or truth_values.shape != predicted_values.shape:
            raise MetricInputError(
                metric="au_summary",
                detail=f"{au} truth {truth_values.shape} and prediction "
                f"{predicted_values.shape} must be equal 1-D arrays",
            )
        finite = np.isfinite(truth_values) & np.isfinite(predicted_values)
        truth_values = truth_values[finite]
        predicted_values = predicted_values[finite]
        if truth_values.size == 0:
            raise MetricInputError(
                metric="au_summary", detail=f"{au} has no finite pairs"
            )
        truth_binary = truth_values >= 2.0
        predicted_binary = predicted_values >= 0.5
        truth_positive_count = int(truth_binary.sum())
        predicted_positive_count = int(predicted_binary.sum())
        au_metrics.append(
            AUMetric(
                au=au,
                f1=_binary_f1(truth_binary, predicted_binary),
                icc=_icc_3_1(truth_values, predicted_values),
                evaluated_samples=int(truth_values.size),
                support=truth_positive_count,
                prevalence=float(truth_positive_count / truth_values.size),
                truth_positive_count=truth_positive_count,
                predicted_positive_count=predicted_positive_count,
            )
        )
    return AUSummary(
        au_metrics=tuple(au_metrics),
        macro_f1=float(np.mean([metric.f1 for metric in au_metrics])),
        macro_icc=float(np.mean([metric.icc for metric in au_metrics])),
    )


def _binary_f1(
    truth: npt.NDArray[np.bool_],
    prediction: npt.NDArray[np.bool_],
) -> float:
    true_positive = int(np.count_nonzero(truth & prediction))
    false_positive = int(np.count_nonzero(~truth & prediction))
    false_negative = int(np.count_nonzero(truth & ~prediction))
    denominator = 2 * true_positive + false_positive + false_negative
    return 0.0 if denominator == 0 else float(2 * true_positive / denominator)


def _icc_3_1(
    truth: npt.NDArray[np.float64],
    prediction: npt.NDArray[np.float64],
) -> float:
    if truth.size < 2:
        return 0.0
    ratings = np.stack([truth, prediction], axis=1)
    sample_count, rater_count = ratings.shape
    grand_mean = ratings.mean()
    sample_means = ratings.mean(axis=1)
    rater_means = ratings.mean(axis=0)
    sample_ss = rater_count * np.sum((sample_means - grand_mean) ** 2)
    rater_ss = sample_count * np.sum((rater_means - grand_mean) ** 2)
    total_ss = np.sum((ratings - grand_mean) ** 2)
    error_ss = total_ss - sample_ss - rater_ss
    sample_ms = sample_ss / (sample_count - 1)
    error_ms = error_ss / ((sample_count - 1) * (rater_count - 1))
    denominator = sample_ms + (rater_count - 1) * error_ms
    if denominator <= 1e-12:
        return 0.0
    return float((sample_ms - error_ms) / denominator)
