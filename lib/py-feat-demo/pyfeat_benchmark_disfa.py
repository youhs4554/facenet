"""Deterministic DISFA sampling and temporary raw-video frame extraction."""

from __future__ import annotations

import random
import re
import shutil
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final
from zipfile import ZipFile

from pyfeat_benchmark_data import DatasetLayoutError, DISFAFrameLabel


VIDEO_MEMBER: Final = re.compile(
    r"leftVideo(?P<subject>SN\d{3})_comp\.avi", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class DISFAFrameSample:
    label: DISFAFrameLabel
    image_path: Path


@dataclass(frozen=True, slots=True)
class FrameExtractionError(Exception):
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"{self.subject}: {self.detail}"


def select_subject_balanced_labels(
    labels: Sequence[DISFAFrameLabel],
    max_samples: int,
    seed: int,
) -> list[DISFAFrameLabel]:
    """Select deterministic uniform-within-subject DISFA frames."""
    if max_samples <= 0 or max_samples >= len(labels):
        return list(labels)
    by_subject: dict[str, list[DISFAFrameLabel]] = {}
    for label in labels:
        by_subject.setdefault(label.subject, []).append(label)
    subjects = sorted(by_subject)
    base, remainder = divmod(max_samples, len(subjects))
    rng = random.Random(seed)
    remainder_subjects = set(rng.sample(subjects, remainder))
    selected: list[DISFAFrameLabel] = []
    for subject in subjects:
        count = base + int(subject in remainder_subjects)
        subject_labels = by_subject[subject]
        if count > len(subject_labels):
            raise DatasetLayoutError(
                path=Path(subject),
                detail=f"requested {count} frames from {len(subject_labels)} labels",
            )
        selected.extend(rng.sample(subject_labels, count))
    return sorted(selected, key=lambda label: (label.subject, label.frame_number))


@contextmanager
def materialize_disfa_frames(
    data_root: Path,
    labels: Sequence[DISFAFrameLabel],
) -> Generator[list[DISFAFrameSample]]:
    """Yield selected JPEG frames, removing extracted video data on exit."""
    video_archive = data_root.resolve() / "DISFA" / "Videos_LeftCamera.zip"
    if not video_archive.is_file():
        raise DatasetLayoutError(
            path=video_archive, detail="left-camera archive is missing"
        )
    with TemporaryDirectory(prefix="pyfeat-disfa-") as temporary_name:
        temporary_root = Path(temporary_name)
        samples = _extract_selected_frames(
            video_archive=video_archive,
            labels=labels,
            temporary_root=temporary_root,
        )
        yield samples


def _extract_selected_frames(
    video_archive: Path,
    labels: Sequence[DISFAFrameLabel],
    temporary_root: Path,
) -> list[DISFAFrameSample]:
    import cv2  # pyright: ignore[reportMissingTypeStubs]

    by_subject: dict[str, list[DISFAFrameLabel]] = {}
    for label in labels:
        by_subject.setdefault(label.subject, []).append(label)
    extracted: list[DISFAFrameSample] = []
    with ZipFile(video_archive) as archive:
        members = _video_members(archive, video_archive)
        for subject in sorted(by_subject):
            member = members.get(subject)
            if member is None:
                raise DatasetLayoutError(
                    path=video_archive,
                    detail=f"left-camera video for {subject} is missing",
                )
            video_path = temporary_root / f"{subject}.avi"
            with archive.open(member) as source, video_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            subject_labels = sorted(
                by_subject[subject], key=lambda label: label.frame_number
            )
            requested = {
                label.video_frame_index: label for label in subject_labels
            }
            capture = cv2.VideoCapture(str(video_path))
            if not capture.isOpened():
                capture.release()
                raise FrameExtractionError(
                    subject=subject, detail="could not open extracted video"
                )
            subject_samples: list[DISFAFrameSample] = []
            last_frame = max(requested)
            frame_index = 0
            while frame_index <= last_frame:
                success, frame = capture.read()
                if not success:
                    break
                label = requested.get(frame_index)
                if label is not None:
                    image_path = temporary_root / (
                        f"{subject}_{label.frame_number:06d}.jpg"
                    )
                    if not cv2.imwrite(str(image_path), frame):
                        capture.release()
                        raise FrameExtractionError(
                            subject=subject,
                            detail=f"could not write frame {label.frame_number}",
                        )
                    subject_samples.append(
                        DISFAFrameSample(label=label, image_path=image_path)
                    )
                frame_index += 1
            capture.release()
            video_path.unlink()
            if len(subject_samples) != len(subject_labels):
                raise FrameExtractionError(
                    subject=subject,
                    detail=f"decoded {len(subject_samples)} of "
                    f"{len(subject_labels)} requested frames",
                )
            extracted.extend(subject_samples)
    return extracted


def _video_members(archive: ZipFile, video_archive: Path) -> dict[str, str]:
    members: dict[str, str] = {}
    for member in archive.namelist():
        matched = VIDEO_MEMBER.fullmatch(member)
        if matched is not None:
            members[matched.group("subject").upper()] = member
    if not members:
        raise DatasetLayoutError(
            path=video_archive, detail="no left-camera videos found"
        )
    return members
