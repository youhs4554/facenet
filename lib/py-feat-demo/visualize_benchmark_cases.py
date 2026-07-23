#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib>=3.10",
#     "numpy>=2.0",
#     "pillow>=11.0",
#     "py-feat==2.0.3",
#     "typer>=0.16",
# ]
# ///

"""Rerun deterministic pilots and render auditable best/worst cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
import typer
from feat import Detectorv2

from pyfeat_benchmark_aflfp import select_balanced_aflfp_samples
from pyfeat_benchmark_case_render import render_aflfp_cases, render_disfa_cases
from pyfeat_benchmark_case_manifest import (
    CaseManifestSettings,
    write_case_manifests,
)
from pyfeat_benchmark_cases import (
    AFLFPCase,
    DISFACase,
    score_disfa_case,
    select_aflfp_extremes,
    select_disfa_extremes,
)
from pyfeat_benchmark_data import (
    DISFA_AUS,
    DISFAFrameLabel,
    load_aflfp_samples,
    load_disfa_labels,
    read_landmarks,
)
from pyfeat_benchmark_disfa import (
    DISFAFrameSample,
    materialize_disfa_frames,
    select_subject_balanced_labels,
)
from pyfeat_benchmark_metrics import landmark_nme


SEED: Final = 42
AFLFP_SAMPLE_COUNT: Final = 256
DISFA_SAMPLE_COUNT: Final = 270
BATCH_SIZE: Final = 4
OUTPUT_SIZE: Final = 512
EXTREME_COUNT: Final = 2
AU_NAMES: Final = tuple(f"AU{au:02d}" for au in DISFA_AUS)
LANDMARK_COLUMNS: Final = tuple(
    [f"x_{index}" for index in range(68)]
    + [f"y_{index}" for index in range(68)]
)


@dataclass(frozen=True, slots=True)
class DetectedFace:
    face_score: float
    landmarks: npt.NDArray[np.float64]
    au_probabilities: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RunConfig:
    data_root: Path
    output_dir: Path
    asset_dir: Path
    device: str


def _detect_faces(
    detector: Detectorv2, image_paths: list[Path], require_aus: bool
) -> dict[int, DetectedFace]:
    columns = ("frame", "FaceScore", *LANDMARK_COLUMNS, *AU_NAMES)
    detections = detector.detect(
        [str(path) for path in image_paths],
        data_type="image",
        output_size=OUTPUT_SIZE,
        batch_size=BATCH_SIZE,
        num_workers=0,
        progress_bar=True,
    )
    values = np.asarray(
        detections[list(columns)].to_numpy(dtype=np.float64), dtype=np.float64
    )
    faces: dict[int, DetectedFace] = {}
    for row in values:
        frame = int(row[0])
        face_score = float(row[1])
        landmarks = np.column_stack((row[2:70], row[70:138]))
        probabilities = row[138:150]
        if not np.isfinite(face_score) or not np.isfinite(landmarks).all():
            continue
        if require_aus and not np.isfinite(probabilities).all():
            continue
        previous = faces.get(frame)
        if previous is None or face_score > previous.face_score:
            faces[frame] = DetectedFace(
                face_score=face_score,
                landmarks=landmarks,
                au_probabilities=tuple(float(value) for value in probabilities),
            )
    return faces


def _run_aflfp(detector: Detectorv2, config: RunConfig) -> list[AFLFPCase]:
    samples = select_balanced_aflfp_samples(
        load_aflfp_samples(config.data_root), AFLFP_SAMPLE_COUNT, SEED
    )
    faces = _detect_faces(detector, [sample.image_path for sample in samples], False)
    cases: list[AFLFPCase] = []
    for frame, sample in enumerate(samples):
        face = faces.get(frame)
        if face is None:
            continue
        truth = read_landmarks(sample.annotation_path)
        cases.append(
            AFLFPCase(
                key=str(sample.image_path.relative_to(config.data_root)),
                subject=sample.subject,
                movement=sample.movement,
                image_path=sample.image_path,
                face_score=face.face_score,
                nme=landmark_nme(face.landmarks, truth),
                truth=truth,
                prediction=face.landmarks,
            )
        )
    selection = select_aflfp_extremes(cases, EXTREME_COUNT)
    render_aflfp_cases(
        selection,
        config.asset_dir / "py-feat-detectorv2-aflfp-best-worst-2026-07-21.png",
    )
    return cases


def _run_disfa(detector: Detectorv2, config: RunConfig) -> list[DISFACase]:
    labels = select_subject_balanced_labels(
        load_disfa_labels(config.data_root / "DISFA" / "ActionUnit_Labels.zip"),
        DISFA_SAMPLE_COUNT,
        SEED,
    )
    with materialize_disfa_frames(config.data_root, labels) as samples:
        cases = _score_disfa_samples(detector, samples, labels)
        selection = select_disfa_extremes(cases, EXTREME_COUNT)
        render_disfa_cases(
            selection,
            config.asset_dir / "py-feat-detectorv2-disfa-best-worst-2026-07-21.png",
        )
    return cases


def _score_disfa_samples(
    detector: Detectorv2,
    samples: list[DISFAFrameSample],
    labels: list[DISFAFrameLabel],
) -> list[DISFACase]:
    faces = _detect_faces(detector, [sample.image_path for sample in samples], True)
    cases: list[DISFACase] = []
    for frame, (sample, label) in enumerate(zip(samples, labels, strict=True)):
        face = faces.get(frame)
        if face is None:
            continue
        score = score_disfa_case(label.intensities, face.au_probabilities)
        cases.append(
            DISFACase(
                key=f"{label.subject}/frame-{label.frame_number:06d}",
                subject=label.subject,
                frame_number=label.frame_number,
                image_path=sample.image_path,
                face_score=face.face_score,
                agreement_count=score.agreement_count,
                mismatch_count=score.mismatch_count,
                probability_mae=score.probability_mae,
                truth_intensities=label.intensities,
                predictions=face.au_probabilities,
                landmarks=face.landmarks,
            )
        )
    return cases


def main(
    data_root: Path = Path("../../data"),
    output_dir: Path = Path("../../output/benchmarks/case-analysis"),
    asset_dir: Path = Path("../../docs/weekly/assets"),
) -> None:
    """Generate rankings and four-panel figures for both benchmark datasets."""
    config = RunConfig(
        data_root=data_root.resolve(), output_dir=output_dir.resolve(),
        asset_dir=asset_dir.resolve(), device="mps",
    )
    detector = Detectorv2(device=config.device)
    aflfp_cases = _run_aflfp(detector, config)
    disfa_cases = _run_disfa(detector, config)
    manifest_settings = CaseManifestSettings(
        output_dir=config.output_dir, device=config.device, seed=SEED,
        batch_size=BATCH_SIZE, output_size=OUTPUT_SIZE,
        extreme_count=EXTREME_COUNT, aflfp_requested=AFLFP_SAMPLE_COUNT,
        disfa_requested=DISFA_SAMPLE_COUNT,
    )
    aflfp_manifest, disfa_manifest = write_case_manifests(
        manifest_settings, aflfp_cases, disfa_cases
    )
    typer.echo(f"AFLFP: {len(aflfp_cases)} scored; {aflfp_manifest}")
    typer.echo(f"DISFA: {len(disfa_cases)} scored; {disfa_manifest}")


if __name__ == "__main__":
    typer.run(main)
