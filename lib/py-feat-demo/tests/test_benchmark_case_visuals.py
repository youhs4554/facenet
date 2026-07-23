from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from pyfeat_benchmark_case_render import render_aflfp_cases, render_disfa_cases
from pyfeat_benchmark_cases import (
    AFLFPCase,
    AFLFPSelection,
    DISFACase,
    DISFASelection,
    score_disfa_case,
    select_aflfp_extremes,
    select_disfa_extremes,
)


def _points(offset: float) -> np.ndarray:
    values = np.linspace(40.0, 160.0, 68)
    return np.column_stack([values + offset, values[::-1] + offset])


def _aflfp_case(image_path: Path, key: str, nme: float) -> AFLFPCase:
    truth = _points(0.0)
    return AFLFPCase(
        key=key,
        subject=key,
        movement="brow raise",
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
