"""AFLFP canonical movement balancing for benchmark pilots."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from pyfeat_benchmark_data import AFLFPSample, DatasetLayoutError


CANONICAL_MOVEMENTS: Final = (
    "brow raise",
    "close smile",
    "frown",
    "funny",
    "gentle eyes closure",
    "left eyebrow",
    "left smile",
    "left snarl",
    "left wink",
    "open smile",
    "right eyebrow",
    "right smile",
    "right snarl",
    "right wink",
    "snarl",
    "tight eyes closure",
)
MOVEMENT_ALIASES: Final = {
    "close eyes gentle": "gentle eyes closure",
    "close eyes gently": "gentle eyes closure",
    "frow": "frown",
    "frowm": "frown",
    "gentle eye closure": "gentle eyes closure",
    "gentle eys closure": "gentle eyes closure",
    "gentle smile": "close smile",
    "gently eyes closure": "gentle eyes closure",
    "left eyeborw": "left eyebrow",
    "left eyrbrow": "left eyebrow",
    "rigth smile": "right smile",
    "tight eues closure": "tight eyes closure",
    "tight eye closure": "tight eyes closure",
    "tight eyes close": "tight eyes closure",
}


def select_balanced_aflfp_samples(
    samples: Sequence[AFLFPSample],
    max_samples: int,
    seed: int,
) -> list[AFLFPSample]:
    """Balance a deterministic pilot across subjects and canonical movements."""
    grouped = _group_canonical_samples(samples)
    if max_samples <= 0:
        return [
            _canonical_sample(sample, movement)
            for subject_groups in grouped.values()
            for movement, movement_samples in subject_groups.items()
            for sample in movement_samples
        ]
    available_pairs = sum(len(groups) for groups in grouped.values())
    if max_samples > available_pairs:
        raise DatasetLayoutError(
            path=Path("AFLFP"),
            detail=f"requested {max_samples} unique subject/movement pairs; found {available_pairs}",
        )
    allocation, rng = _allocate_balanced_pairs(grouped, max_samples, seed)
    return [
        _canonical_sample(
            rng.choice(
                sorted(
                    grouped[subject][movement], key=lambda item: item.image_path.name
                )
            ),
            movement,
        )
        for subject, movement in allocation
    ]


def _group_canonical_samples(
    samples: Sequence[AFLFPSample],
) -> dict[str, dict[str, list[AFLFPSample]]]:
    grouped: dict[str, dict[str, list[AFLFPSample]]] = {}
    expected = set(CANONICAL_MOVEMENTS)
    for sample in samples:
        movement = MOVEMENT_ALIASES.get(sample.movement, sample.movement)
        if movement not in expected:
            raise DatasetLayoutError(
                path=sample.image_path,
                detail=f"unknown AFLFP movement {sample.movement!r}",
            )
        grouped.setdefault(sample.subject, {}).setdefault(movement, []).append(sample)
    found = {movement for groups in grouped.values() for movement in groups}
    if found != expected:
        raise DatasetLayoutError(
            path=Path("AFLFP"),
            detail=f"canonical movements differ from {sorted(expected)}",
        )
    return grouped


def _allocate_balanced_pairs(
    grouped: Mapping[str, Mapping[str, Sequence[AFLFPSample]]],
    max_samples: int,
    seed: int,
) -> tuple[list[tuple[str, str]], random.Random]:
    base_subjects = sorted(grouped, key=int)
    for attempt in range(100):
        rng = random.Random(seed + attempt)
        subjects = base_subjects.copy()
        movements = list(CANONICAL_MOVEMENTS)
        rng.shuffle(subjects)
        subject_base, subject_remainder = divmod(max_samples, len(subjects))
        subject_targets = {
            subject: subject_base + int(index < subject_remainder)
            for index, subject in enumerate(subjects)
        }
        rng.shuffle(movements)
        movement_base, movement_remainder = divmod(max_samples, len(movements))
        movement_targets = {
            movement: movement_base + int(index < movement_remainder)
            for index, movement in enumerate(movements)
        }
        allocation = _greedy_allocation(
            grouped, subjects, subject_targets, movement_targets, rng
        )
        if len(allocation) == max_samples:
            return allocation, rng
    raise DatasetLayoutError(
        path=Path("AFLFP"), detail="could not satisfy subject/movement balance"
    )


def _greedy_allocation(
    grouped: Mapping[str, Mapping[str, Sequence[AFLFPSample]]],
    subjects: list[str],
    subject_targets: Mapping[str, int],
    movement_targets: Mapping[str, int],
    rng: random.Random,
) -> list[tuple[str, str]]:
    movement_counts: Counter[str] = Counter()
    used: dict[str, set[str]] = {subject: set() for subject in subjects}
    allocation: list[tuple[str, str]] = []
    for round_index in range(max(subject_targets.values(), default=0)):
        active = [
            subject for subject in subjects if subject_targets[subject] > round_index
        ]
        rng.shuffle(active)
        for subject in active:
            candidates = [
                movement
                for movement in grouped[subject]
                if movement not in used[subject]
                and movement_counts[movement] < movement_targets[movement]
            ]
            if not candidates:
                return []
            largest_deficit = max(
                movement_targets[movement] - movement_counts[movement]
                for movement in candidates
            )
            tied = sorted(
                movement
                for movement in candidates
                if movement_targets[movement] - movement_counts[movement]
                == largest_deficit
            )
            movement = rng.choice(tied)
            used[subject].add(movement)
            movement_counts[movement] += 1
            allocation.append((subject, movement))
    return allocation


def _canonical_sample(sample: AFLFPSample, movement: str) -> AFLFPSample:
    return AFLFPSample(
        subject=sample.subject,
        movement=movement,
        image_path=sample.image_path,
        annotation_path=sample.annotation_path,
    )
