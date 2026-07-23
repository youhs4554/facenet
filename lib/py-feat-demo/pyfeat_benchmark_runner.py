"""Offline py-feat inference and report generation for benchmark datasets."""

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


def run_aflfp_benchmark(
    data_root: Path,
    max_samples: int,
    seed: int,
    device: str,
    batch_size: int,
) -> AFLFPBenchmarkReport:
    """Run the default repository Detectorv2 over a balanced AFLFP pilot."""
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
    summary = score_aflfp_detections(detections, samples, elapsed_s=elapsed_s)
    return AFLFPBenchmarkReport(
        dataset="aflfp",
        detector="Detectorv2",
        py_feat_version=version("py-feat"),
        device=device,
        seed=seed,
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
    )


def score_aflfp_detections(
    detections: DetectionTable,
    samples: list[AFLFPSample],
    elapsed_s: float,
) -> LandmarkSummary:
    """Align top-face rows to AFLFP inputs and summarize landmark NME."""
    top_faces: dict[int, tuple[float, DetectionRow]] = {}
    for _, row in detections.iterrows():
        frame = int(float(row["frame"]))
        face_score = float(row["FaceScore"])
        previous = top_faces.get(frame)
        if math.isfinite(face_score) and (previous is None or face_score > previous[0]):
            top_faces[frame] = (face_score, row)

    scores: list[float | None] = []
    for frame, sample in enumerate(samples):
        selected = top_faces.get(frame)
        if selected is None:
            scores.append(None)
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
            continue
        scores.append(landmark_nme(prediction, read_landmarks(sample.annotation_path)))
    return summarize_landmark_scores(scores, elapsed_s=elapsed_s)


def write_aflfp_report(
    report: AFLFPBenchmarkReport, output_dir: Path
) -> tuple[Path, Path]:
    """Persist one AFLFP report as JSON and concise Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "aflfp-pilot.json"
    markdown_path = output_dir / "aflfp-pilot.md"
    json_path.write_text(
        f"{json.dumps(asdict(report), indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    markdown_path.write_text(_aflfp_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _aflfp_markdown(report: AFLFPBenchmarkReport) -> str:
    return (
        "# AFLFP py-feat Detectorv2 pilot\n\n"
        f"- Samples: {report.scored_samples:,} scored / {report.processed_samples:,} processed "
        f"({report.detection_rate:.1%})\n"
        f"- NME mean / std: {report.nme_mean:.4f} / {report.nme_std:.4f}\n"
        f"- NME median / P90: {report.nme_median:.4f} / {report.nme_p90:.4f}\n"
        f"- Throughput: {report.fps:.2f} FPS ({report.elapsed_s:.2f} s)\n"
        f"- Coverage: {report.subjects} subjects, {report.movements} movement labels\n"
        f"- Normalization: {report.nme_definition}\n"
    )
