"""Audit manifests for deterministic benchmark case analysis."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from pyfeat_benchmark_cases import AFLFPCase, DISFACase

type JsonValue = (
    str
    | int
    | float
    | bool
    | None
    | list[JsonValue]
    | dict[str, JsonValue]
)


@dataclass(frozen=True, slots=True)
class CaseManifestSettings:
    output_dir: Path
    device: str
    seed: int
    batch_size: int
    output_size: int
    extreme_count: int
    aflfp_requested: int
    disfa_requested: int


def write_case_manifests(
    settings: CaseManifestSettings,
    aflfp_cases: list[AFLFPCase],
    disfa_cases: list[DISFACase],
) -> tuple[Path, Path]:
    """Persist complete per-sample scores and predictions for both datasets."""
    aflfp_records = [_aflfp_record(case) for case in aflfp_cases]
    disfa_records = [_disfa_record(case) for case in disfa_cases]
    aflfp_path = _write_manifest(settings, "aflfp", aflfp_records)
    disfa_path = _write_manifest(settings, "disfa", disfa_records)
    return aflfp_path, disfa_path


def write_target_manifest(
    settings: CaseManifestSettings,
    path: Path,
    aflfp_cases: Sequence[AFLFPCase],
    disfa_cases: Sequence[DISFACase],
) -> Path:
    """Persist only the cases shown in the target-aligned publication figures."""
    disfa_panels = ("AU12", "AU25", "AU26", "inactive reference")
    payload: dict[str, JsonValue] = {
        "purpose": (
            "target-aligned qualitative examples; not aggregate benchmark replacement"
        ),
        "detector": "Detectorv2",
        "py_feat_version": version("py-feat"),
        "device": settings.device,
        "seed": settings.seed,
        "batch_size": settings.batch_size,
        "output_size": settings.output_size,
        "raw_media_included": False,
        "selection_rules": {
            "aflfp": (
                "median-NME case per target movement, publication-eligible subjects "
                "only, distinct subjects when available"
            ),
            "disfa": (
                "highest manual intensity then highest Py-Feat probability for "
                "AU12/AU25/AU26, distinct subjects when available, plus the "
                "lowest target-AU probability inactive frame"
            ),
        },
        "aflfp_panels": [_aflfp_record(case) for case in aflfp_cases],
        "disfa_panels": [
            {"panel": panel, **_disfa_record(case)}
            for panel, case in zip(disfa_panels, disfa_cases, strict=True)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _aflfp_record(case: AFLFPCase) -> dict[str, JsonValue]:
    return {
        "key": case.key,
        "subject": case.subject,
        "movement": case.movement,
        "face_score": case.face_score,
        "nme": case.nme,
        "truth": [[float(x), float(y)] for x, y in case.truth],
        "prediction": [[float(x), float(y)] for x, y in case.prediction],
    }


def _disfa_record(case: DISFACase) -> dict[str, JsonValue]:
    return {
        "key": case.key,
        "subject": case.subject,
        "frame_number": case.frame_number,
        "face_score": case.face_score,
        "agreement_count": case.agreement_count,
        "mismatch_count": case.mismatch_count,
        "probability_mae": case.probability_mae,
        "truth_intensities": list(case.truth_intensities),
        "predictions": list(case.predictions),
        "landmarks": [[float(x), float(y)] for x, y in case.landmarks],
    }


def _write_manifest(
    settings: CaseManifestSettings,
    dataset: str,
    records: list[dict[str, JsonValue]],
) -> Path:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    path = settings.output_dir / f"{dataset}-case-ranking.json"
    record_values: list[JsonValue] = list(records)
    payload: dict[str, JsonValue] = {
        "dataset": dataset,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "best/worst qualitative case analysis; not aggregate benchmark replacement",
        "detector": "Detectorv2",
        "py_feat_version": version("py-feat"),
        "identity_model": "Detectorv2 default",
        "device": settings.device,
        "seed": settings.seed,
        "batch_size": settings.batch_size,
        "output_size": settings.output_size,
        "requested_samples": (
            settings.aflfp_requested
            if dataset == "aflfp"
            else settings.disfa_requested
        ),
        "scored_samples": len(records),
        "best_worst_count": settings.extreme_count,
        "ranking": (
            "NME ascending; worst shown descending"
            if dataset == "aflfp"
            else "binary AU mismatch count ascending, probability MAE tie-break; worst shown descending"
        ),
        "records": record_values,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path
