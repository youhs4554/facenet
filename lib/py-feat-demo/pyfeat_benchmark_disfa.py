"""Deterministic DISFA sampling and temporary raw-video frame extraction."""

from __future__ import annotations

import random
import re
import shutil
import subprocess
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
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FrameExtractionError(subject="DISFA", detail="ffmpeg is not available")
    with TemporaryDirectory(prefix="pyfeat-disfa-") as temporary_name:
        temporary_root = Path(temporary_name)
        samples = _extract_selected_frames(
            video_archive=video_archive,
            labels=labels,
            ffmpeg=ffmpeg,
            temporary_root=temporary_root,
        )
        yield samples


def _extract_selected_frames(
    video_archive: Path,
    labels: Sequence[DISFAFrameLabel],
    ffmpeg: str,
    temporary_root: Path,
) -> list[DISFAFrameSample]:
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
            output_pattern = temporary_root / f"{subject}_%06d.jpg"
            selector = "+".join(
                f"eq(n\\,{label.video_frame_index})" for label in subject_labels
            )
            command = [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"select={selector}",
                "-fps_mode",
                "vfr",
                "-start_number",
                "0",
                "-q:v",
                "2",
                str(output_pattern),
            ]
            try:
                _ = subprocess.run(command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as exc:
                raise FrameExtractionError(
                    subject=subject, detail=str(exc.stderr).strip()
                ) from exc
            video_path.unlink()
            images = sorted(temporary_root.glob(f"{subject}_*.jpg"))
            if len(images) != len(subject_labels):
                raise FrameExtractionError(
                    subject=subject,
                    detail=f"decoded {len(images)} of {len(subject_labels)} requested frames",
                )
            extracted.extend(
                DISFAFrameSample(label=label, image_path=image)
                for label, image in zip(subject_labels, images, strict=True)
            )
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
