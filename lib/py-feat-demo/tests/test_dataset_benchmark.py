from __future__ import annotations

from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

import pyfeat_benchmark_data as benchmark
import pyfeat_benchmark_aflfp as aflfp
import pyfeat_benchmark_metrics as metrics


DATA_ROOT = Path(__file__).resolve().parents[3] / "data"


def test_inspect_real_dataset_contract() -> None:
    inventory = benchmark.inspect_datasets(DATA_ROOT)

    assert inventory.aflfp.subjects == 88
    assert inventory.aflfp.images == 6_476
    assert inventory.aflfp.annotated_samples == 5_328
    assert inventory.aflfp.landmark_points == 68
    assert inventory.disfa.subjects == 27
    assert inventory.disfa.labeled_frames == 130_814
    assert inventory.disfa.au_count == 12


def test_load_aflfp_rejects_non_68_point_annotation(tmp_path: Path) -> None:
    annotation = tmp_path / "bad.pts"
    annotation.write_text("\n".join(f"{index}.0 {index}.0" for index in range(67)))

    with pytest.raises(benchmark.LandmarkFormatError):
        benchmark.read_landmarks(annotation)


def test_aflfp_nme_uses_bbox_area() -> None:
    truth = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 9.0], [0.0, 9.0]])
    prediction = truth + np.array([3.0, 4.0])

    score = metrics.landmark_nme(prediction, truth)

    assert score == pytest.approx(5.0 / 6.0)


def test_aflfp_missing_detection_stays_in_denominator() -> None:
    summary = metrics.summarize_landmark_scores([0.1, None, 0.2], elapsed_s=2.0)

    assert summary.requested_samples == 3
    assert summary.processed_samples == 3
    assert summary.scored_samples == 2
    assert summary.detection_rate == pytest.approx(2.0 / 3.0)
    assert summary.nme_mean == pytest.approx(0.15)
    assert summary.fps == pytest.approx(1.5)


def test_aflfp_sampling_balances_subjects_and_canonical_movements() -> None:
    selected = aflfp.select_balanced_aflfp_samples(
        benchmark.load_aflfp_samples(DATA_ROOT),
        max_samples=256,
        seed=42,
    )

    subject_counts = Counter(sample.subject for sample in selected)
    movement_counts = Counter(sample.movement for sample in selected)
    repeated = aflfp.select_balanced_aflfp_samples(
        benchmark.load_aflfp_samples(DATA_ROOT),
        max_samples=256,
        seed=42,
    )
    assert len(selected) == 256
    assert [sample.image_path for sample in selected] == [
        sample.image_path for sample in repeated
    ]
    assert len(subject_counts) == 88
    assert set(subject_counts.values()) == {2, 3}
    assert len(movement_counts) == 16
    assert set(movement_counts.values()) == {16}


def test_disfa_zip_labels_align_one_based_frames(tmp_path: Path) -> None:
    archive_path = tmp_path / "ActionUnit_Labels.zip"
    with ZipFile(archive_path, mode="w") as archive:
        for au in (1, 2, 4, 5, 6, 9, 12, 15, 17, 20, 25, 26):
            second_intensity = 2 if au == 1 else 0
            archive.writestr(
                f"SN001/SN001_au{au}.txt",
                f"1,0\n2,{second_intensity}\n",
            )

    labels = benchmark.load_disfa_labels(archive_path)

    assert len(labels) == 2
    assert labels[0].subject == "SN001"
    assert labels[0].frame_number == 1
    assert labels[0].video_frame_index == 0
    assert labels[1].frame_number == 2
    assert labels[1].video_frame_index == 1
    assert labels[1].intensities[0] == 2


def test_disfa_metrics_use_documented_thresholds() -> None:
    truth = {"AU01": np.array([0.0, 1.0, 2.0, 5.0])}
    prediction = {"AU01": np.array([0.1, 0.9, 0.5, 0.49])}

    summary = metrics.summarize_au_scores(truth, prediction)
    metric = summary.au_metrics[0]

    assert metric.truth_positive_count == 2
    assert metric.predicted_positive_count == 2
    assert metric.support == 2
    assert metric.prevalence == pytest.approx(0.5)
    assert metric.f1 == pytest.approx(0.5)
