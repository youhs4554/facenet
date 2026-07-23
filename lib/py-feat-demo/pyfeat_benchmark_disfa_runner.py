"""Offline py-feat inference and reports for raw DISFA videos."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Protocol, SupportsFloat, cast

import numpy as np

from pyfeat_benchmark_data import DISFA_AUS, DISFAFrameLabel, load_disfa_labels
from pyfeat_benchmark_disfa import (
    materialize_disfa_frames,
    select_subject_balanced_labels,
)
from pyfeat_benchmark_metrics import AUMetric, summarize_au_scores


class DetectionRow(Protocol):
    def __getitem__(self, key: str) -> SupportsFloat: ...


class DetectionTable(Protocol):
    def iterrows(self) -> Iterable[tuple[object, DetectionRow]]: ...


@dataclass(frozen=True, slots=True)
class DISFABenchmarkReport:
    dataset: str
    detector: str
    py_feat_version: str
    device: str
    seed: int
    requested_samples: int
    processed_samples: int
    scored_samples: int
    detection_rate: float
    macro_f1: float
    macro_icc: float
    elapsed_s: float
    fps: float
    subjects: int
    truth_threshold: float
    prediction_threshold: float
    au_metrics: tuple[AUMetric, ...]


def run_disfa_benchmark(
    data_root: Path,
    max_samples: int,
    seed: int,
    device: str,
    batch_size: int,
) -> DISFABenchmarkReport:
    """Run Detectorv2 over subject-balanced raw DISFA left-camera frames."""
    from feat import Detectorv2  # pyright: ignore[reportMissingTypeStubs]

    labels = select_subject_balanced_labels(
        load_disfa_labels(data_root.resolve() / "DISFA" / "ActionUnit_Labels.zip"),
        max_samples=max_samples,
        seed=seed,
    )
    detector = Detectorv2(
        device=device,
        identity_model=None,  # pyright: ignore[reportArgumentType]
    )
    with materialize_disfa_frames(data_root, labels) as samples:
        started = time.perf_counter()
        detections = cast(
            DetectionTable,
            cast(
                object,
                detector.detect(
                    [str(sample.image_path) for sample in samples],
                    data_type="image",
                    output_size=512,
                    batch_size=batch_size,
                    num_workers=0,
                    progress_bar=True,
                ),
            ),
        )
        elapsed_s = time.perf_counter() - started
        return score_disfa_detections(detections, labels, elapsed_s, device, seed)


def score_disfa_detections(
    detections: DetectionTable,
    labels: list[DISFAFrameLabel],
    elapsed_s: float,
    device: str,
    seed: int,
) -> DISFABenchmarkReport:
    """Align the highest-confidence detected face to every selected frame."""
    top_faces: dict[int, tuple[float, DetectionRow]] = {}
    for _, row in detections.iterrows():
        frame = int(float(row["frame"]))
        face_score = float(row["FaceScore"])
        previous = top_faces.get(frame)
        if math.isfinite(face_score) and (previous is None or face_score > previous[0]):
            top_faces[frame] = (face_score, row)

    au_names = tuple(f"AU{au:02d}" for au in DISFA_AUS)
    truth = {
        au: np.asarray([label.intensities[index] for label in labels], dtype=np.float64)
        for index, au in enumerate(au_names)
    }
    prediction = {au: np.full(len(labels), np.nan, dtype=np.float64) for au in au_names}
    scored_samples = 0
    for frame, (_, row) in top_faces.items():
        if not 0 <= frame < len(labels):
            continue
        values = np.asarray([float(row[au]) for au in au_names], dtype=np.float64)
        if not np.isfinite(values).all():
            continue
        for au, value in zip(au_names, values, strict=True):
            prediction[au][frame] = value
        scored_samples += 1
    summary = summarize_au_scores(truth, prediction)
    processed_samples = len(labels)
    return DISFABenchmarkReport(
        dataset="disfa",
        detector="Detectorv2",
        py_feat_version=version("py-feat"),
        device=device,
        seed=seed,
        requested_samples=processed_samples,
        processed_samples=processed_samples,
        scored_samples=scored_samples,
        detection_rate=float(scored_samples / processed_samples),
        macro_f1=summary.macro_f1,
        macro_icc=summary.macro_icc,
        elapsed_s=elapsed_s,
        fps=float(processed_samples / elapsed_s),
        subjects=len({label.subject for label in labels}),
        truth_threshold=2.0,
        prediction_threshold=0.5,
        au_metrics=summary.au_metrics,
    )


def write_disfa_report(
    report: DISFABenchmarkReport, output_dir: Path
) -> tuple[Path, Path]:
    """Persist one DISFA report as JSON and concise Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "disfa-pilot.json"
    markdown_path = output_dir / "disfa-pilot.md"
    json_path.write_text(
        f"{json.dumps(asdict(report), indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    markdown_path.write_text(_disfa_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _disfa_markdown(report: DISFABenchmarkReport) -> str:
    rows = "".join(
        f"| {metric.au} | {metric.f1:.4f} | {metric.icc:.4f} | "
        f"{metric.support} | {metric.prevalence:.2%} | {metric.evaluated_samples} |\n"
        for metric in report.au_metrics
    )
    return (
        "# DISFA py-feat Detectorv2 pilot\n\n"
        f"- Samples: {report.scored_samples:,} scored / {report.processed_samples:,} processed "
        f"({report.detection_rate:.1%})\n"
        f"- Macro F1 / ICC(3,1): {report.macro_f1:.4f} / {report.macro_icc:.4f}\n"
        f"- Throughput: {report.fps:.2f} FPS ({report.elapsed_s:.2f} s)\n"
        f"- Thresholds: truth >= {report.truth_threshold:g}, prediction >= "
        f"{report.prediction_threshold:g}\n\n"
        "| AU | F1 | ICC(3,1) | Support | Prevalence | Evaluated |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        f"{rows}"
    )
