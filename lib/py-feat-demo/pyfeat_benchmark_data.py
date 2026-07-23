"""Raw AFLFP and DISFA dataset contracts for py-feat benchmarks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from zipfile import ZipFile

import numpy as np
import numpy.typing as npt


AFLFP_LANDMARK_COUNT: Final = 68
DISFA_AU_COUNT: Final = 12
DISFA_AUS: Final = (1, 2, 4, 5, 6, 9, 12, 15, 17, 20, 25, 26)
DISFA_LABEL_MEMBER: Final = re.compile(
    r"(?P<subject>SN\d{3})/(?P=subject)_au(?P<au>\d+)\.txt"
)


@dataclass(frozen=True, slots=True)
class LandmarkFormatError(Exception):
    path: Path
    found_shape: tuple[int, ...]

    def __str__(self) -> str:
        return (
            f"{self.path}: expected ({AFLFP_LANDMARK_COUNT}, 2) landmarks, "
            f"found {self.found_shape}"
        )


@dataclass(frozen=True, slots=True)
class DatasetLayoutError(Exception):
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.detail}"


@dataclass(frozen=True, slots=True)
class AFLFPInventory:
    subjects: int
    images: int
    annotated_samples: int
    landmark_points: int


@dataclass(frozen=True, slots=True)
class DISFAInventory:
    subjects: int
    labeled_frames: int
    au_count: int


@dataclass(frozen=True, slots=True)
class DatasetInventory:
    data_root: str
    aflfp: AFLFPInventory
    disfa: DISFAInventory


@dataclass(frozen=True, slots=True)
class AFLFPSample:
    subject: str
    movement: str
    image_path: Path
    annotation_path: Path


@dataclass(frozen=True, slots=True)
class DISFAFrameLabel:
    subject: str
    frame_number: int
    video_frame_index: int
    intensities: tuple[int, ...]


def read_landmarks(path: Path) -> npt.NDArray[np.float64]:
    """Parse one AFLFP manual 68-point annotation."""
    try:
        points = np.loadtxt(path, dtype=np.float64)
    except (OSError, ValueError) as exc:
        raise LandmarkFormatError(path=path, found_shape=()) from exc
    if points.shape != (AFLFP_LANDMARK_COUNT, 2):
        raise LandmarkFormatError(path=path, found_shape=points.shape)
    return points


def inspect_datasets(data_root: Path) -> DatasetInventory:
    """Validate and summarize the two raw dataset distributions."""
    root = data_root.resolve()
    aflfp = root / "AFLFP"
    disfa = root / "DISFA"
    if not aflfp.is_dir():
        raise DatasetLayoutError(path=aflfp, detail="AFLFP directory is missing")
    if not disfa.is_dir():
        raise DatasetLayoutError(path=disfa, detail="DISFA directory is missing")

    subject_dirs = [
        path for path in aflfp.iterdir() if path.is_dir() and path.name.isdigit()
    ]
    annotations = sorted(
        path
        for path in aflfp.rglob("*.pts")
        if not path.name.startswith("._") and not path.name.endswith("_detect.pts")
    )
    for annotation in annotations:
        _ = read_landmarks(annotation)
    images = sum(1 for path in aflfp.rglob("*.jpg") if not path.name.startswith("._"))

    disfa_inventory = _inspect_disfa(disfa / "ActionUnit_Labels.zip")
    return DatasetInventory(
        data_root=str(root),
        aflfp=AFLFPInventory(
            subjects=len(subject_dirs),
            images=images,
            annotated_samples=len(annotations),
            landmark_points=AFLFP_LANDMARK_COUNT,
        ),
        disfa=disfa_inventory,
    )


def load_aflfp_samples(data_root: Path) -> list[AFLFPSample]:
    """Load every paired manual AFLFP annotation and source JPEG."""
    aflfp = data_root.resolve() / "AFLFP"
    samples: list[AFLFPSample] = []
    for annotation in sorted(aflfp.rglob("*.pts")):
        if annotation.name.startswith("._") or annotation.name.endswith("_detect.pts"):
            continue
        image_path = annotation.with_suffix(".jpg")
        if not image_path.is_file():
            raise DatasetLayoutError(
                path=image_path, detail="paired AFLFP JPEG is missing"
            )
        relative = annotation.relative_to(aflfp)
        subject = relative.parts[0]
        sample_stem = annotation.stem.rsplit("_", maxsplit=1)[0]
        movement = sample_stem.split("-", maxsplit=1)[-1]
        samples.append(
            AFLFPSample(
                subject=subject,
                movement=movement,
                image_path=image_path,
                annotation_path=annotation,
            )
        )
    return samples


def _inspect_disfa(label_archive: Path) -> DISFAInventory:
    labels = load_disfa_labels(label_archive)
    return DISFAInventory(
        subjects=len({label.subject for label in labels}),
        labeled_frames=len(labels),
        au_count=len(DISFA_AUS),
    )


def load_disfa_labels(label_archive: Path) -> list[DISFAFrameLabel]:
    """Load DISFA AU intensities and map one-based labels to video indices."""
    if not label_archive.is_file():
        raise DatasetLayoutError(
            path=label_archive, detail="AU label archive is missing"
        )

    subject_members: dict[str, dict[str, str]] = {}
    with ZipFile(label_archive) as archive:
        for member in archive.namelist():
            matched = DISFA_LABEL_MEMBER.fullmatch(member)
            if matched is None:
                continue
            subject = matched.group("subject")
            au = matched.group("au")
            subject_members.setdefault(subject, {})[au] = member

        labels: list[DISFAFrameLabel] = []
        expected_aus = {str(au) for au in DISFA_AUS}
        for subject in sorted(subject_members):
            au_members = subject_members[subject]
            if set(au_members) != expected_aus:
                raise DatasetLayoutError(
                    path=label_archive,
                    detail=f"{subject} AU files differ from {sorted(expected_aus, key=int)}",
                )
            columns = [
                _read_disfa_au_column(archive, au_members[str(au)], label_archive)
                for au in DISFA_AUS
            ]
            frame_sequences = {
                tuple(frame for frame, _ in column) for column in columns
            }
            if len(frame_sequences) != 1:
                raise DatasetLayoutError(
                    path=label_archive,
                    detail=f"{subject} AU files have inconsistent frame sequences",
                )
            frames = next(iter(frame_sequences))
            for row_index, frame_number in enumerate(frames):
                if frame_number != row_index + 1:
                    raise DatasetLayoutError(
                        path=label_archive,
                        detail=f"{subject} expected frame {row_index + 1}, found {frame_number}",
                    )
                labels.append(
                    DISFAFrameLabel(
                        subject=subject,
                        frame_number=frame_number,
                        video_frame_index=frame_number - 1,
                        intensities=tuple(column[row_index][1] for column in columns),
                    )
                )
    return labels


def _read_disfa_au_column(
    archive: ZipFile,
    member: str,
    label_archive: Path,
) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    for line in archive.read(member).decode("utf-8-sig").splitlines():
        try:
            frame_text, intensity_text = line.split(",", maxsplit=1)
            frame_number = int(frame_text)
            intensity = int(intensity_text)
        except ValueError as exc:
            raise DatasetLayoutError(
                path=label_archive,
                detail=f"{member} contains malformed row {line!r}",
            ) from exc
        if not 0 <= intensity <= 5:
            raise DatasetLayoutError(
                path=label_archive,
                detail=f"{member} contains intensity {intensity}; expected 0..5",
            )
        rows.append((frame_number, intensity))
    return rows
