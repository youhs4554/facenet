"""Offline py-feat inference and report generation for benchmark datasets."""

from __future__ import annotations

import csv
import json
import math
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Protocol, SupportsFloat, cast

import numpy as np

from pyfeat_benchmark_aflfp import select_balanced_aflfp_samples
from pyfeat_benchmark_data import (
    AFLFPSample,
    load_aflfp_samples,
    read_landmarks,
)
from pyfeat_benchmark_metrics import (
    LandmarkSummary,
    landmark_nme,
    summarize_landmark_scores,
)


class DetectionRow(Protocol):
    def __getitem__(self, key: str) -> SupportsFloat: ...


class DetectionTable(Protocol):
    def iterrows(self) -> Iterable[tuple[object, DetectionRow]]: ...


@dataclass(frozen=True, slots=True)
class AFLFPBenchmarkReport:
    dataset: str
    detector: str
    py_feat_version: str
    device: str
    seed: int
    evaluation_mode: str
    sample_strategy: str
    batch_size: int
    output_size: int
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
    subjects: int
    movements: int
    nme_definition: str
    sample_results: tuple[AFLFPSampleResult, ...]


@dataclass(frozen=True, slots=True)
class AFLFPSampleResult:
    subject: str
    movement: str
    sample_id: str
    detected: bool
    nme: float | None


def run_aflfp_benchmark(
    data_root: Path,
    max_samples: int,
    seed: int,
    device: str,
    batch_size: int,
) -> AFLFPBenchmarkReport:
    """Run the default repository Detectorv2 over a balanced AFLFP test cohort."""
    from feat import Detectorv2  # pyright: ignore[reportMissingTypeStubs]

    samples = select_balanced_aflfp_samples(
        load_aflfp_samples(data_root), max_samples=max_samples, seed=seed
    )
    detector = Detectorv2(
        device=device,
        identity_model=None,  # pyright: ignore[reportArgumentType]
    )
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
    summary, sample_results = _score_aflfp_samples(
        detections, samples, elapsed_s=elapsed_s
    )
    return AFLFPBenchmarkReport(
        dataset="aflfp",
        detector="Detectorv2",
        py_feat_version=version("py-feat"),
        device=device,
        seed=seed,
        evaluation_mode="test-only; pretrained weights; no fitting or tuning",
        sample_strategy="balanced unique subject/movement pairs",
        batch_size=batch_size,
        output_size=512,
        requested_samples=max_samples,
        processed_samples=summary.processed_samples,
        scored_samples=summary.scored_samples,
        detection_rate=summary.detection_rate,
        nme_mean=summary.nme_mean,
        nme_std=summary.nme_std,
        nme_median=summary.nme_median,
        nme_p90=summary.nme_p90,
        elapsed_s=summary.elapsed_s,
        fps=summary.fps,
        subjects=len({sample.subject for sample in samples}),
        movements=len({sample.movement for sample in samples}),
        nme_definition="mean point error / sqrt(GT bbox width * GT bbox height)",
        sample_results=sample_results,
    )


def score_aflfp_detections(
    detections: DetectionTable,
    samples: list[AFLFPSample],
    elapsed_s: float,
) -> LandmarkSummary:
    """Align top-face rows to AFLFP inputs and summarize landmark NME."""
    summary, _ = _score_aflfp_samples(detections, samples, elapsed_s)
    return summary


def _score_aflfp_samples(
    detections: DetectionTable,
    samples: list[AFLFPSample],
    elapsed_s: float,
) -> tuple[LandmarkSummary, tuple[AFLFPSampleResult, ...]]:
    top_faces: dict[int, tuple[float, DetectionRow]] = {}
    for _, row in detections.iterrows():
        frame = int(float(row["frame"]))
        face_score = float(row["FaceScore"])
        previous = top_faces.get(frame)
        if math.isfinite(face_score) and (previous is None or face_score > previous[0]):
            top_faces[frame] = (face_score, row)

    scores: list[float | None] = []
    sample_results: list[AFLFPSampleResult] = []
    for frame, sample in enumerate(samples):
        selected = top_faces.get(frame)
        if selected is None:
            scores.append(None)
            sample_results.append(_aflfp_sample_result(sample, None))
            continue
        row = selected[1]
        prediction = np.column_stack(
            [
                [float(row[f"x_{index}"]) for index in range(68)],
                [float(row[f"y_{index}"]) for index in range(68)],
            ]
        )
        if not np.isfinite(prediction).all():
            scores.append(None)
            sample_results.append(_aflfp_sample_result(sample, None))
            continue
        score = landmark_nme(prediction, read_landmarks(sample.annotation_path))
        scores.append(score)
        sample_results.append(_aflfp_sample_result(sample, score))
    return (
        summarize_landmark_scores(scores, elapsed_s=elapsed_s),
        tuple(sample_results),
    )


def _aflfp_sample_result(
    sample: AFLFPSample, nme: float | None
) -> AFLFPSampleResult:
    return AFLFPSampleResult(
        subject=sample.subject,
        movement=sample.movement,
        sample_id="/".join(sample.image_path.parts[-3:]),
        detected=nme is not None,
        nme=nme,
    )


def write_aflfp_report(
    report: AFLFPBenchmarkReport, output_dir: Path
) -> tuple[Path, Path, Path]:
    """Persist AFLFP aggregate JSON, concise Markdown, and sample-level CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "aflfp-test.json"
    markdown_path = output_dir / "aflfp-test.md"
    csv_path = output_dir / "aflfp-samples.csv"
    json_path.write_text(
        f"{json.dumps(aflfp_report_dict(report), indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_aflfp_markdown(report), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("subject", "movement", "sample_id", "detected", "nme")
        )
        writer.writeheader()
        for sample in report.sample_results:
            writer.writerow(asdict(sample))
    return json_path, markdown_path, csv_path


def aflfp_report_dict(report: AFLFPBenchmarkReport) -> dict[str, object]:
    payload = asdict(report)
    del payload["sample_results"]
    return payload


def _aflfp_markdown(report: AFLFPBenchmarkReport) -> str:
    return (
        "# AFLFP py-feat Detectorv2 test-only evaluation\n\n"
        f"- Samples: {report.scored_samples:,} scored / {report.processed_samples:,} processed "
        f"({report.detection_rate:.1%})\n"
        f"- NME mean / std: {report.nme_mean:.4f} / {report.nme_std:.4f}\n"
        f"- NME median / P90: {report.nme_median:.4f} / {report.nme_p90:.4f}\n"
        f"- Throughput: {report.fps:.2f} FPS ({report.elapsed_s:.2f} s)\n"
        f"- Coverage: {report.subjects} subjects, {report.movements} movement labels\n"
        f"- Normalization: {report.nme_definition}\n"
    )
