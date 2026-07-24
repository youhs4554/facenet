from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from pyfeat_benchmark_case_render import (
    render_aflfp_cases,
    render_aflfp_ground_truth_example,
    render_aflfp_target_cases,
    render_disfa_cases,
    render_disfa_ground_truth_example,
    render_disfa_target_cases,
    render_disfa_target_strip,
)
from pyfeat_benchmark_cases import (
    AFLFPCase,
    AFLFPSelection,
    DISFACase,
    DISFASelection,
    score_disfa_case,
    select_aflfp_extremes,
    select_aflfp_target_cases,
    select_disfa_extremes,
    select_disfa_target_cases,
)


def _points(offset: float) -> np.ndarray:
    values = np.linspace(40.0, 160.0, 68)
    return np.column_stack([values + offset, values[::-1] + offset])


def _aflfp_case(
    image_path: Path,
    key: str,
    nme: float,
    movement: str = "brow raise",
) -> AFLFPCase:
    truth = _points(0.0)
    return AFLFPCase(
        key=key,
        subject=key,
        movement=movement,
        image_path=image_path,
        face_score=0.95,
        nme=nme,
        truth=truth,
        prediction=truth + nme * 10.0,
    )


def _disfa_case(
    image_path: Path,
    key: str,
    mismatch_count: int,
    probability_mae: float,
) -> DISFACase:
    predictions = tuple(
        0.9 if index >= mismatch_count else 0.1 for index in range(12)
    )
    truth = tuple(2 for _ in range(12))
    return DISFACase(
        key=key,
        subject=key,
        frame_number=1,
        image_path=image_path,
        face_score=0.94,
        agreement_count=12 - mismatch_count,
        mismatch_count=mismatch_count,
        probability_mae=probability_mae,
        truth_intensities=truth,
        predictions=predictions,
        landmarks=_points(0.0),
    )


def _disfa_target_case(
    image_path: Path,
    key: str,
    truth: tuple[int, ...],
    predictions: tuple[float, ...],
) -> DISFACase:
    score = score_disfa_case(truth, predictions)
    return DISFACase(
        key=key,
        subject=key,
        frame_number=1,
        image_path=image_path,
        face_score=0.94,
        agreement_count=score.agreement_count,
        mismatch_count=score.mismatch_count,
        probability_mae=score.probability_mae,
        truth_intensities=truth,
        predictions=predictions,
        landmarks=_points(0.0),
    )


def test_aflfp_extremes_select_lowest_and_highest_nme(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = [
        _aflfp_case(image_path, "a", 0.01),
        _aflfp_case(image_path, "b", 0.02),
        _aflfp_case(image_path, "c", 0.08),
        _aflfp_case(image_path, "d", 0.09),
    ]

    # When
    selection = select_aflfp_extremes(cases, count=2)

    # Then
    assert [case.key for case in selection.best] == ["a", "b"]
    assert [case.key for case in selection.worst] == ["d", "c"]


def test_aflfp_target_cases_use_allowed_subjects_and_median_nme(
    tmp_path: Path,
) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = [
        _aflfp_case(image_path, "1", 0.01, "close smile"),
        _aflfp_case(image_path, "3", 0.02, "close smile"),
        _aflfp_case(image_path, "99", 0.03, "close smile"),
        _aflfp_case(image_path, "4", 0.01, "open smile"),
        _aflfp_case(image_path, "5", 0.02, "open smile"),
        _aflfp_case(image_path, "98", 0.03, "open smile"),
    ]

    # When
    selected = select_aflfp_target_cases(
        cases,
        movements=("close smile", "open smile"),
        allowed_subjects=frozenset({"1", "3", "4", "5"}),
    )

    # Then
    assert [(case.subject, case.movement) for case in selected] == [
        ("3", "close smile"),
        ("5", "open smile"),
    ]


def test_disfa_case_score_uses_thresholds_and_probability_tiebreak() -> None:
    # Given
    truth = (0, 2, 5, 1)
    prediction = (0.1, 0.7, 0.4, 0.6)

    # When
    score = score_disfa_case(truth, prediction)

    # Then
    assert score.agreement_count == 2
    assert score.mismatch_count == 2
    assert score.probability_mae == 0.4


def test_disfa_extremes_select_most_mismatches_as_worst(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = [
        _disfa_case(image_path, "a", 0, 0.10),
        _disfa_case(image_path, "b", 0, 0.20),
        _disfa_case(image_path, "c", 4, 0.30),
        _disfa_case(image_path, "d", 4, 0.40),
    ]

    # When
    selection = select_disfa_extremes(cases, count=2)

    # Then
    assert [case.key for case in selection.best] == ["a", "b"]
    assert [case.key for case in selection.worst] == ["d", "c"]


def test_disfa_target_cases_select_three_aus_and_neutral(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    zero_truth = (0,) * 12
    zero_predictions = (0.05,) * 12
    au12_truth = (*((0,) * 6), 5, *((0,) * 5))
    au25_truth = (*((0,) * 10), 5, 0)
    au26_truth = (*((0,) * 11), 5)
    cases = [
        _disfa_target_case(
            image_path, "SN001", au12_truth, (*((0.05,) * 6), 0.90, *((0.05,) * 5))
        ),
        _disfa_target_case(
            image_path, "SN002", au25_truth, (*((0.05,) * 10), 0.95, 0.05)
        ),
        _disfa_target_case(
            image_path, "SN003", au26_truth, (*((0.05,) * 11), 0.85)
        ),
        _disfa_target_case(image_path, "SN004", zero_truth, zero_predictions),
    ]

    # When
    selected = select_disfa_target_cases(cases)

    # Then
    assert [case.subject for case in selected] == [
        "SN001",
        "SN002",
        "SN003",
        "SN004",
    ]


def test_aflfp_renderer_writes_report_ready_png(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = tuple(
        _aflfp_case(image_path, key, nme)
        for key, nme in (("a", 0.01), ("b", 0.02), ("c", 0.08), ("d", 0.09))
    )
    selection = AFLFPSelection(best=cases[:2], worst=tuple(reversed(cases[2:])))
    output_path = tmp_path / "aflfp.png"

    # When
    render_aflfp_cases(selection, output_path)

    # Then
    with Image.open(output_path) as rendered:
        assert rendered.size == (1920, 1600)


def test_aflfp_target_renderer_writes_report_ready_png(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = tuple(
        _aflfp_case(image_path, str(index), 0.02, movement)
        for index, movement in enumerate(
            ("close smile", "open smile", "left smile", "right smile"), start=1
        )
    )
    output_path = tmp_path / "aflfp-target.png"

    # When
    render_aflfp_target_cases(cases, output_path)

    # Then
    with Image.open(output_path) as rendered:
        assert rendered.size == (1920, 1600)


def test_aflfp_ground_truth_renderer_writes_wide_png(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    case = _aflfp_case(image_path, "18", 0.02, "close smile")
    output_path = tmp_path / "aflfp-ground-truth.png"

    # When
    render_aflfp_ground_truth_example(case, output_path)

    # Then
    with Image.open(output_path) as rendered:
        assert rendered.size == (1920, 800)


def test_disfa_renderer_writes_report_ready_png(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = tuple(
        _disfa_case(image_path, key, mismatches, probability_mae)
        for key, mismatches, probability_mae in (
            ("a", 0, 0.1),
            ("b", 1, 0.2),
            ("c", 3, 0.3),
            ("d", 4, 0.4),
        )
    )
    selection = DISFASelection(best=cases[:2], worst=tuple(reversed(cases[2:])))
    output_path = tmp_path / "disfa.png"

    # When
    render_disfa_cases(selection, output_path)

    # Then
    with Image.open(output_path) as rendered:
        assert rendered.size == (1920, 1600)


def test_disfa_target_renderer_writes_report_ready_png(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = tuple(
        _disfa_case(image_path, f"SN00{index}", 0, 0.1)
        for index in range(1, 5)
    )
    output_path = tmp_path / "disfa-target.png"

    # When
    render_disfa_target_cases(cases, output_path)

    # Then
    with Image.open(output_path) as rendered:
        assert rendered.size == (1920, 1600)


def test_disfa_target_strip_writes_compact_paper_png(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    cases = tuple(
        _disfa_case(image_path, f"SN00{index}", 0, 0.1)
        for index in range(1, 5)
    )
    output_path = tmp_path / "disfa-target-strip.png"

    # When
    render_disfa_target_strip(cases, output_path)

    # Then
    with Image.open(output_path) as rendered:
        assert rendered.size == (2400, 640)


def test_disfa_ground_truth_renderer_writes_wide_png(tmp_path: Path) -> None:
    # Given
    image_path = tmp_path / "face.png"
    Image.new("RGB", (200, 200), "white").save(image_path)
    case = _disfa_case(image_path, "SN007", 0, 0.1)
    output_path = tmp_path / "disfa-ground-truth.png"

    # When
    render_disfa_ground_truth_example(case, output_path)

    # Then
    with Image.open(output_path) as rendered:
        assert rendered.size == (1920, 800)
