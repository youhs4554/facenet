#!/usr/bin/env python3
"""Blendshape-driven diagnostic face using NVIDIA's open Claire geometry basis.

The public model package contains vertex positions and blendshape deltas but no
render topology in the open-weight NPZ files.  This renderer therefore uses a
dense, neutral-material point-splat surface.  It is geometry deformation, not
a recolored avatar or a claim that the diagnostic surface is a final rig.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _load_motion():
    path = Path(__file__).with_name("a2f_motion.py")
    spec = importlib.util.spec_from_file_location("_a2f_motion_mannequin", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


motion = _load_motion()


class MannequinBasis:
    def __init__(
        self,
        *,
        curve_names: tuple[str, ...],
        skin_neutral: np.ndarray,
        skin_deltas: np.ndarray,
        skin_render_indices: np.ndarray,
        tongue_neutral: np.ndarray,
        tongue_deltas: np.ndarray,
        source_skin: Path,
        source_tongue: Path,
        skin_triangles: np.ndarray | None = None,
        tongue_triangles: np.ndarray | None = None,
        topology_source: Path | None = None,
        source_model: str | None = None,
        license_name: str | None = None,
    ) -> None:
        self.curve_names = curve_names
        self.skin_neutral = skin_neutral
        self.skin_deltas = skin_deltas
        self.skin_render_indices = skin_render_indices
        self.tongue_neutral = tongue_neutral
        self.tongue_deltas = tongue_deltas
        self.source_skin = source_skin
        self.source_tongue = source_tongue
        self.skin_triangles = (
            np.asarray(skin_triangles, dtype=np.int32)
            if skin_triangles is not None
            else np.empty((0, 3), dtype=np.int32)
        )
        self.tongue_triangles = (
            np.asarray(tongue_triangles, dtype=np.int32)
            if tongue_triangles is not None
            else np.empty((0, 3), dtype=np.int32)
        )
        self.topology_source = topology_source
        self.render_mode = (
            "triangle_surface" if len(self.skin_triangles) else "point_splat"
        )
        self.source_model = source_model or (
            "nvidia/Audio2Face-3D-v3.0@"
            "b74132732fd9a9d29b237bec193ded64c9745e91"
        )
        self.license = license_name or "NVIDIA Open Model License"


class MannequinDataError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decoded_pose_names(data: Any) -> list[str]:
    return [
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in data["poseNames"]
    ]


def load_nvidia_mannequin_basis(
    skin_path: Path,
    tongue_path: Path,
    *,
    topology_path: Path | None = None,
) -> MannequinBasis:
    skin_path, tongue_path = Path(skin_path).resolve(), Path(tongue_path).resolve()
    if not skin_path.is_file() or not tongue_path.is_file():
        raise MannequinDataError("NVIDIA mannequin basis files are missing")
    with np.load(skin_path, allow_pickle=False) as skin:
        skin_names = _decoded_pose_names(skin)
        if skin_names[0].casefold() != "neutral" or len(skin_names) != 53:
            raise MannequinDataError("skin basis must contain neutral + ARKit 52")
        canonical_skin = list(motion.BLENDSHAPE_NAMES[:52])
        by_casefold = {name.casefold(): name for name in skin_names[1:]}
        if set(by_casefold) != {name.casefold() for name in canonical_skin}:
            raise MannequinDataError("skin pose names do not match A2F ARKit 52")
        skin_neutral = np.asarray(skin["neutral"], dtype=np.float32).copy()
        skin_deltas = np.stack(
            [np.asarray(skin[by_casefold[name.casefold()]], dtype=np.float32) for name in canonical_skin]
        )
        render_indices = np.asarray(skin["frontalMask"], dtype=np.int32).copy()
    with np.load(tongue_path, allow_pickle=False) as tongue:
        tongue_names = _decoded_pose_names(tongue)
        canonical_tongue = list(motion.BLENDSHAPE_NAMES[52:])
        by_casefold = {name.casefold(): name for name in tongue_names[1:]}
        if tongue_names[0].casefold() != "neutral" or set(by_casefold) != {
            name.casefold() for name in canonical_tongue
        }:
            raise MannequinDataError("tongue pose names do not match A2F extended 16")
        tongue_neutral = np.asarray(tongue["neutral"], dtype=np.float32).copy()
        tongue_deltas = np.stack(
            [np.asarray(tongue[by_casefold[name.casefold()]], dtype=np.float32) for name in canonical_tongue]
        )
    expected_counts = {(24002, 5602), (1500, 520)}
    if (len(skin_neutral), len(tongue_neutral)) not in expected_counts:
        raise MannequinDataError("unexpected NVIDIA Claire vertex counts")
    if not all(
        np.isfinite(array).all()
        for array in (skin_neutral, skin_deltas, tongue_neutral, tongue_deltas)
    ):
        raise MannequinDataError("NVIDIA mannequin basis contains non-finite data")
    skin_triangles = tongue_triangles = None
    resolved_topology = None
    source_model = None
    license_name = None
    if topology_path is not None:
        resolved_topology = Path(topology_path).resolve()
        if not resolved_topology.is_file():
            raise MannequinDataError("Claire topology cache is missing")
        topology = json.loads(resolved_topology.read_text(encoding="utf-8"))

        def triangulate(mesh: dict[str, Any], point_count: int) -> np.ndarray:
            if mesh.get("point_count") != point_count:
                raise MannequinDataError("topology vertex count does not match basis")
            counts = mesh["face_vertex_counts"]
            indices = mesh["face_vertex_indices"]
            triangles = []
            cursor = 0
            for count in counts:
                polygon = indices[cursor : cursor + count]
                cursor += count
                for index in range(1, count - 1):
                    triangles.append((polygon[0], polygon[index], polygon[index + 1]))
            if cursor != len(indices):
                raise MannequinDataError("topology index stream is malformed")
            result = np.asarray(triangles, dtype=np.int32)
            if result.size == 0 or result.min() < 0 or result.max() >= point_count:
                raise MannequinDataError("topology triangle indices are invalid")
            return result

        skin_triangles = triangulate(topology["skin_mesh"], len(skin_neutral))
        tongue_triangles = triangulate(
            topology["tongue_mesh"], len(tongue_neutral)
        )
        source_model = "NVIDIA Audio2Face-3D Claire Training Sample v1.0.0"
        license_name = "NVIDIA Claire sample dataset license - evaluation only"
    return MannequinBasis(
        curve_names=tuple(motion.BLENDSHAPE_NAMES),
        skin_neutral=skin_neutral,
        skin_deltas=skin_deltas,
        skin_render_indices=render_indices,
        tongue_neutral=tongue_neutral,
        tongue_deltas=tongue_deltas,
        source_skin=skin_path,
        source_tongue=tongue_path,
        skin_triangles=skin_triangles,
        tongue_triangles=tongue_triangles,
        topology_source=resolved_topology,
        source_model=source_model,
        license_name=license_name,
    )


def deform_mannequin(
    basis: MannequinBasis, weights: np.ndarray | list[float]
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(weights, dtype=np.float32)
    if values.shape != (68,) or not np.isfinite(values).all():
        raise MannequinDataError("mannequin weights must be finite A2F-68")
    if np.count_nonzero(values) == 0:
        return basis.skin_neutral.copy(), basis.tongue_neutral.copy()
    skin = basis.skin_neutral + np.tensordot(
        values[:52], basis.skin_deltas, axes=(0, 0)
    )
    tongue = basis.tongue_neutral + np.tensordot(
        values[52:], basis.tongue_deltas, axes=(0, 0)
    )
    return skin.astype(np.float32, copy=False), tongue.astype(np.float32, copy=False)


def _point_color(depth: float, minimum: float, maximum: float, tongue: bool) -> tuple[int, int, int]:
    ratio = (depth - minimum) / max(1e-6, maximum - minimum)
    ratio = min(1.0, max(0.0, ratio))
    if tongue:
        value = int(85 + 75 * ratio)
        return (value + 25, value, value)
    value = int(105 + 125 * ratio)
    return (value, value + 3, value + 8)


def _render_triangle_surface(
    basis: MannequinBasis,
    skin: np.ndarray,
    tongue: np.ndarray,
    width: int,
    height: int,
) -> Image.Image:
    antialias = 2
    render_width, render_height = width * antialias, height * antialias
    top, bottom = 52 * antialias, 36 * antialias
    neutral_xy = basis.skin_neutral[:, [0, 1]]
    x_min, y_min = neutral_xy.min(axis=0)
    x_max, y_max = neutral_xy.max(axis=0)
    x_min -= 1.0
    x_max += 1.0
    y_min -= 1.0
    y_max += 1.0
    scale = min(
        (render_width - 48 * antialias) / max(1e-6, x_max - x_min),
        (render_height - top - bottom) / max(1e-6, y_max - y_min),
    )
    x_offset = (render_width - (x_max - x_min) * scale) / 2.0
    y_offset = top + (
        render_height - top - bottom - (y_max - y_min) * scale
    ) / 2.0

    def project(vertices: np.ndarray) -> np.ndarray:
        result = np.empty((len(vertices), 2), dtype=np.float32)
        result[:, 0] = x_offset + (vertices[:, 0] - x_min) * scale
        result[:, 1] = y_offset + (y_max - vertices[:, 1]) * scale
        return result

    def triangle_items(
        vertices: np.ndarray,
        triangles: np.ndarray,
        base_color: tuple[int, int, int],
    ) -> list[tuple[float, list[tuple[int, int]], tuple[int, int, int]]]:
        if not len(triangles):
            return []
        geometry = vertices[triangles]
        edges_a = geometry[:, 1] - geometry[:, 0]
        edges_b = geometry[:, 2] - geometry[:, 0]
        normals = np.cross(edges_a, edges_b)
        normal_lengths = np.linalg.norm(normals, axis=1)
        normals /= np.maximum(normal_lengths[:, None], 1e-6)
        light = np.asarray((0.15, -0.25, 1.0), dtype=np.float32)
        light /= np.linalg.norm(light)
        diffuse = np.abs(normals @ light)
        intensity = 0.36 + 0.64 * diffuse
        screen = project(vertices)
        depth = geometry[:, :, 2].mean(axis=1)
        items = []
        for index, triangle in enumerate(triangles):
            color = tuple(
                max(0, min(255, int(channel * intensity[index])))
                for channel in base_color
            )
            polygon = [tuple(map(int, screen[vertex])) for vertex in triangle]
            items.append((float(depth[index]), polygon, color))
        return items

    items = triangle_items(skin, basis.skin_triangles, (155, 210, 238))
    items.extend(triangle_items(tongue, basis.tongue_triangles, (160, 92, 100)))
    items.sort(key=lambda item: item[0])
    surface = Image.new("RGB", (render_width, render_height), (10, 14, 22))
    draw = ImageDraw.Draw(surface)
    for _depth, polygon, color in items:
        draw.polygon(polygon, fill=color)
    return surface.resize((width, height), Image.Resampling.LANCZOS)


def render_mannequin_frame(
    basis: MannequinBasis,
    weights: np.ndarray | list[float],
    *,
    width: int,
    height: int,
    frame_index: int,
    time_seconds: float,
    source_label: str,
) -> tuple[Image.Image, dict[str, Any]]:
    if width < 160 or height < 160:
        raise MannequinDataError("mannequin render must be at least 160x160")
    skin, tongue = deform_mannequin(basis, weights)
    neutral_skin = basis.skin_neutral
    neutral_tongue = basis.tongue_neutral
    max_displacement = max(
        float(np.linalg.norm(skin - neutral_skin, axis=1).max()),
        float(np.linalg.norm(tongue - neutral_tongue, axis=1).max()),
    )
    if basis.render_mode == "triangle_surface":
        image = _render_triangle_surface(basis, skin, tongue, width, height)
        skin_render_vertices = len(skin)
        tongue_render_vertices = len(tongue)
        footer = (
            "NVIDIA official Claire solver basis · not MetaHuman/Taro geometry"
        )
    else:
        skin_points = skin[basis.skin_render_indices]
        tongue_points = tongue[::3]
        all_xy = basis.skin_neutral[basis.skin_render_indices][:, [0, 1]]
        x_min, y_min = all_xy.min(axis=0)
        x_max, y_max = all_xy.max(axis=0)
        x_min -= 1.5
        x_max += 1.5
        y_min -= 4.0
        y_max += 1.5
        top, bottom = 58, 42
        scale = min(
            (width - 48) / max(1e-6, x_max - x_min),
            (height - top - bottom) / max(1e-6, y_max - y_min),
        )
        x_offset = (width - (x_max - x_min) * scale) / 2.0
        y_offset = top + (
            height - top - bottom - (y_max - y_min) * scale
        ) / 2.0

        def projected(points: np.ndarray, is_tongue: bool) -> list[tuple[float, float, float, bool]]:
            return [
                (
                    x_offset + (float(point[0]) - x_min) * scale,
                    y_offset + (y_max - float(point[1])) * scale,
                    float(point[2]),
                    is_tongue,
                )
                for point in points
            ]

        points = projected(skin_points, False) + projected(tongue_points, True)
        points.sort(key=lambda item: item[2])
        depths = [item[2] for item in points]
        depth_min, depth_max = min(depths), max(depths)
        image = Image.new("RGB", (width, height), (10, 14, 22))
        point_draw = ImageDraw.Draw(image)
        radius = max(1, round(min(width, height) / 270))
        for x, y, depth, is_tongue in points:
            color = _point_color(depth, depth_min, depth_max, is_tongue)
            point_draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius), fill=color
            )
        skin_render_vertices = len(skin_points)
        tongue_render_vertices = len(tongue_points)
        footer = "NVIDIA Claire open-model deltas • point-splat diagnostic (no topology)"
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=14
        )
    except OSError:
        font = ImageFont.load_default()
    draw.text(
        (14, 12),
        "Claire reference geometry — pre-MetaHuman retarget",
        fill=(236, 242, 250),
        font=font,
    )
    draw.text(
        (14, 32),
        f"source={source_label}  frame {frame_index:04d}  t={time_seconds:0.3f}s",
        fill=(154, 171, 194),
        font=font,
    )
    draw.text(
        (14, height - 25),
        footer,
        fill=(133, 148, 170),
        font=font,
    )
    values = np.asarray(weights, dtype=np.float32)
    active = [
        name
        for name, value in zip(basis.curve_names, values)
        if abs(float(value)) >= 0.01
    ]
    metadata = {
        "schema_version": 1,
        "frame_index": frame_index,
        "time_seconds": float(time_seconds),
        "source_label": source_label,
        "curve_count": 68,
        "active_curve_count": len(active),
        "max_vertex_displacement": max_displacement,
        "skin_render_vertices": skin_render_vertices,
        "tongue_render_vertices": tongue_render_vertices,
        "render_mode": basis.render_mode,
        "semantic_label": "Claire reference geometry — pre-MetaHuman retarget",
        "geometry_sha256": hashlib.sha256(
            skin.tobytes(order="C") + tongue.tobytes(order="C")
        ).hexdigest(),
    }
    return image, metadata


def render_mannequin_frames(
    series: dict[str, Any],
    basis: MannequinBasis,
    output_dir: Path,
    *,
    width: int = 640,
    height: int = 540,
    source_label: str,
) -> dict[str, Any]:
    if series.get("curve_names") != list(basis.curve_names):
        raise MannequinDataError("motion series does not use the NVIDIA A2F-68 schema")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, frame in enumerate(series["frames"]):
        image, metadata = render_mannequin_frame(
            basis,
            frame["values"],
            width=width,
            height=height,
            frame_index=index,
            time_seconds=float(frame["time_seconds"]),
            source_label=source_label,
        )
        path = output_dir / f"frame.{index:04d}.png"
        image.save(path, format="PNG", optimize=False, compress_level=9)
        metadata.update(
            {"path": str(path), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        )
        records.append(metadata)
    return {
        "schema_version": 1,
        "source_label": source_label,
        "frame_count": len(records),
        "width": width,
        "height": height,
        "frames": records,
    }


def build_mannequin_video_command(
    *, ffmpeg: Path, frames_dir: Path, output: Path, fps: int, frame_count: int
) -> list[str]:
    return [
        str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
        "-framerate", str(fps), "-i", str(Path(frames_dir) / "frame.%04d.png"),
        "-frames:v", str(frame_count), "-c:v", "libx264", "-crf", "18",
        "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-an", str(output),
    ]


def build_diagnostic_triptych_command(
    *,
    ffmpeg: Path,
    avatar: Path,
    mannequin: Path,
    curves: Path,
    output: Path,
    fps: int,
    frame_count: int,
) -> list[str]:
    graph = (
        f"[0:v]fps={fps},scale=1280:720:force_original_aspect_ratio=decrease,"
        f"pad=1280:1080:(ow-iw)/2:(oh-ih)/2:black,settb=AVTB,"
        f"setpts=N/({fps}*TB)[avatar];"
        f"[1:v]fps={fps},scale=640:540,settb=AVTB,"
        f"setpts=N/({fps}*TB)[mannequin];"
        f"[2:v]fps={fps},scale=640:540,settb=AVTB,"
        f"setpts=N/({fps}*TB)[curves];"
        "[mannequin][curves]vstack=inputs=2[right];"
        "[avatar][right]hstack=inputs=2[v]"
    )
    return [
        str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
        "-i", str(avatar), "-i", str(mannequin), "-i", str(curves),
        "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0",
        "-frames:v", str(frame_count), "-c:v", "libx264", "-crf", "18",
        "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy",
        str(output),
    ]


def basis_provenance(basis: MannequinBasis) -> dict[str, Any]:
    result = {
        "source_model": basis.source_model,
        "license": basis.license,
        "skin": {
            "path": str(basis.source_skin),
            "sha256": sha256_file(basis.source_skin),
            "neutral_vertices": len(basis.skin_neutral),
            "blendshape_deltas": len(basis.skin_deltas),
        },
        "tongue": {
            "path": str(basis.source_tongue),
            "sha256": sha256_file(basis.source_tongue),
            "neutral_vertices": len(basis.tongue_neutral),
            "blendshape_deltas": len(basis.tongue_deltas),
        },
        "rendering": (
            "neutral-material triangulated surface"
            if basis.render_mode == "triangle_surface"
            else "neutral-material point splats; public NPZ contains no triangle topology"
        ),
        "render_mode": basis.render_mode,
        "semantic_boundary": (
            "Claire solver geometry basis driven by A2F-68 weights; not the selected "
            "MetaHuman mesh and not a direct diffusion geometry dump"
        ),
    }
    if basis.topology_source is not None:
        result["topology"] = {
            "path": str(basis.topology_source),
            "sha256": sha256_file(basis.topology_source),
            "skin_triangles": len(basis.skin_triangles),
            "tongue_triangles": len(basis.tongue_triangles),
            "source_usd_license": "NVIDIA Claire sample dataset - evaluation only",
        }
    return result
