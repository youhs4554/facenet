#!/usr/bin/env python3
"""Render an inspectable projection of official A2F SDK direct skin geometry."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import matplotlib.tri as mtri
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def geometry_digest(vertices: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(vertices, dtype=np.float32).tobytes()).hexdigest()


def nearest_source_frame(
    timestamps: np.ndarray, *, output_frame: int, output_fps: float
) -> int:
    target = output_frame / output_fps
    return int(np.argmin(np.abs(np.asarray(timestamps) - target)))


def read_timestamps(path: Path) -> np.ndarray:
    rows = list(csv.DictReader(path.open()))
    values = np.asarray(
        [int(row["timestamp_current"]) / 16000.0 for row in rows],
        dtype=np.float64,
    )
    if not len(values) or np.any(np.diff(values) <= 0):
        raise RuntimeError("SDK timestamps must be non-empty and strictly monotonic")
    return values


def build_projection_triangles(neutral: np.ndarray, mask: np.ndarray) -> np.ndarray:
    points = neutral[mask][:, :2]
    triangles = mtri.Triangulation(points[:, 0], points[:, 1]).triangles
    edges = np.stack(
        [
            np.linalg.norm(points[triangles[:, 0]] - points[triangles[:, 1]], axis=1),
            np.linalg.norm(points[triangles[:, 1]] - points[triangles[:, 2]], axis=1),
            np.linalg.norm(points[triangles[:, 2]] - points[triangles[:, 0]], axis=1),
        ],
        axis=1,
    )
    maximum_edge = np.max(edges, axis=1)
    threshold = min(1.0, float(np.quantile(maximum_edge, 0.995)) * 1.25)
    return triangles[maximum_edge <= threshold]


def render(run_dir: Path, output_dir: Path, ffmpeg: Path) -> dict:
    geometry_meta = json.loads((run_dir / "geometry/geometry-metadata.json").read_text())
    frames = int(geometry_meta["frame_count"])
    vertices = np.fromfile(run_dir / "geometry/skin.f32", dtype=np.float32).reshape(
        frames, -1, 3
    )
    basis = np.load(run_dir / "model/bs_skin_Claire.npz")
    neutral = basis["neutral"]
    mask = basis["frontalMask"].astype(np.int64)
    if vertices.shape[1:] != neutral.shape:
        raise RuntimeError("direct SDK geometry and Claire basis topology do not match")
    timestamps = read_timestamps(run_dir / "geometry/timestamps.csv")
    triangles = build_projection_triangles(neutral, mask)
    output_dir.mkdir(parents=True, exist_ok=True)
    video = output_dir / "direct-sdk-claire-geometry-reference.mp4"
    log = output_dir / "direct-sdk-claire-geometry-ffmpeg.log"

    width = height = 720
    figure = plt.figure(figsize=(width / 100, height / 100), dpi=100, facecolor="#060a12")
    axis = figure.add_axes((0.04, 0.045, 0.92, 0.88), facecolor="#060a12")
    axis.set_aspect("equal")
    axis.axis("off")
    projected_neutral = neutral[mask][:, :2]
    padding = 0.7
    axis.set_xlim(projected_neutral[:, 0].min() - padding, projected_neutral[:, 0].max() + padding)
    axis.set_ylim(projected_neutral[:, 1].min() - padding, projected_neutral[:, 1].max() + padding)
    collection = PolyCollection([], linewidths=0.12, edgecolors=(0.2, 0.75, 1.0, 0.33))
    axis.add_collection(collection)
    title = figure.text(
        0.5, 0.966, "A2F v3.0 — DIRECT SDK CLAIRE SKIN GEOMETRY",
        color="#e9f5ff", ha="center", va="top", fontsize=13, weight="bold",
    )
    del title
    frame_text = figure.text(0.04, 0.018, "", color="#b9dfff", fontsize=10, ha="left")
    figure.text(
        0.96, 0.018, "Frontal Delaunay projection — visualization topology only",
        color="#7896ad", fontsize=8, ha="right",
    )
    colormap = matplotlib.colormaps["Blues_r"]
    depth_min = float(np.percentile(vertices[:, mask, 2], 2))
    depth_max = float(np.percentile(vertices[:, mask, 2], 98))
    representative = sorted(
        {
            0,
            nearest_source_frame(timestamps, output_frame=83, output_fps=30),
            nearest_source_frame(timestamps, output_frame=86, output_fps=30),
        }
    )
    images = []

    with log.open("w") as log_stream:
        process = subprocess.Popen(
            [
                str(ffmpeg), "-hide_banner", "-loglevel", "warning", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}",
                "-r", "60", "-i", "-", "-an", "-c:v", "libx264",
                "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(video),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=log_stream,
        )
        assert process.stdin is not None
        for frame in range(frames):
            projected = vertices[frame, mask]
            polygons = projected[:, :2][triangles]
            depth = projected[:, 2][triangles].mean(axis=1)
            normalized = np.clip((depth - depth_min) / max(depth_max - depth_min, 1e-6), 0, 1)
            collection.set_verts(polygons)
            collection.set_facecolors(colormap(0.18 + 0.68 * normalized))
            frame_text.set_text(f"F{frame:04d}  /  t={timestamps[frame]:.3f}s  /  24,002 vertices")
            figure.canvas.draw()
            process.stdin.write(np.asarray(figure.canvas.buffer_rgba()).tobytes())
            if frame in representative:
                image = output_dir / f"direct-sdk-frame-{frame:04d}.png"
                figure.savefig(image, facecolor=figure.get_facecolor())
                images.append(image)
        process.stdin.close()
        return_code = process.wait()
    plt.close(figure)
    if return_code != 0 or not video.is_file():
        raise RuntimeError(f"ffmpeg direct geometry encode failed with {return_code}")

    contact_sheet = output_dir / "direct-sdk-geometry-contact-sheet.png"
    figure, axes = plt.subplots(1, len(images), figsize=(15, 5), dpi=120, facecolor="#060a12")
    for axis, image in zip(np.atleast_1d(axes), images):
        axis.imshow(plt.imread(image))
        axis.axis("off")
        axis.set_title(image.stem.rsplit("-", 1)[-1], color="white", fontsize=10)
    figure.tight_layout(pad=0.4)
    figure.savefig(contact_sheet, facecolor=figure.get_facecolor(), bbox_inches="tight")
    plt.close(figure)

    report = {
        "schema_version": 1,
        "status": "pass",
        "source": "official Audio2Face-3D SDK direct skinGeometry callback",
        "semantic_boundary": (
            "Vertex positions are official direct Claire geometry. Triangles are a local 2D "
            "Delaunay visualization over the official frontalMask, not NVIDIA mesh topology."
        ),
        "frames": frames,
        "fps": 60,
        "vertices": int(vertices.shape[1]),
        "triangles": int(len(triangles)),
        "timestamps_first_last": [float(timestamps[0]), float(timestamps[-1])],
        "source_geometry_sha256": sha256(run_dir / "geometry/skin.f32"),
        "representative_source_frames": representative,
        "representative_geometry_sha256": [geometry_digest(vertices[index]) for index in representative],
        "video": {"path": str(video.resolve()), "sha256": sha256(video)},
        "contact_sheet": {"path": str(contact_sheet.resolve()), "sha256": sha256(contact_sheet)},
        "images": [{"path": str(path.resolve()), "sha256": sha256(path)} for path in images],
    }
    manifest = output_dir / "direct-geometry-visualization.json"
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.run_dir.resolve(), args.output_dir.resolve(), args.ffmpeg.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
