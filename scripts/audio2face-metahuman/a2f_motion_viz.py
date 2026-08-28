#!/usr/bin/env python3
"""Deterministic visualization and FFmpeg composition for A2F artifacts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _load_motion():
    try:
        import a2f_motion  # type: ignore
        return a2f_motion
    except ModuleNotFoundError:
        path = Path(__file__).with_name("a2f_motion.py")
        spec = importlib.util.spec_from_file_location("_a2f_motion_local", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


motion = _load_motion()


FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")


def _font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.ImageFont:
    name = (
        "DejaVuSansMono.ttf"
        if mono
        else "DejaVuSans-Bold.ttf"
        if bold
        else "DejaVuSans.ttf"
    )
    try:
        return ImageFont.truetype(str(FONT_ROOT / name), size=size)
    except OSError:
        return ImageFont.load_default(size=size)


def select_top_k(raw: dict[str, Any], effective: dict[str, Any], top_k: int) -> list[str]:
    if top_k < 0 or top_k > len(motion.BLENDSHAPE_NAMES):
        raise ValueError("top_k outside canonical curve range")
    scores = []
    for index, name in enumerate(motion.BLENDSHAPE_NAMES):
        peak = max(
            max(abs(float(frame["values"][index])) for frame in raw["frames"]),
            max(abs(float(frame["values"][index])) for frame in effective["frames"]),
        )
        scores.append((-peak, index, name))
    return [name for _, _, name in sorted(scores)[:top_k]]


def select_frame_top_k(
    effective: dict[str, Any],
    frame_index: int,
    top_k: int,
    active_curve_names: list[str] | None = None,
) -> list[str]:
    """Sort the current frame by displayed effective magnitude."""
    if top_k < 0 or top_k > len(motion.BLENDSHAPE_NAMES):
        raise ValueError("top_k outside canonical curve range")
    source_index = min(frame_index, len(effective["frames"]) - 1)
    values = effective["frames"][source_index]["values"]
    allowed = (
        set(active_curve_names)
        if active_curve_names is not None
        else set(motion.BLENDSHAPE_NAMES)
    )
    if not allowed or not allowed.issubset(set(motion.BLENDSHAPE_NAMES)):
        raise ValueError("active_curve_names must be canonical A2F curves")
    scores = [
        (-abs(float(value)), index, name)
        for index, (name, value) in enumerate(
            zip(motion.BLENDSHAPE_NAMES, values)
        )
        if name in allowed
    ]
    return [name for _, _, name in sorted(scores)[:top_k]]


def _value_at(series: dict[str, Any], frame_index: int, name: str, names_key: str) -> float:
    names = series[names_key]
    source_index = min(frame_index, len(series["frames"]) - 1)
    return float(series["frames"][source_index]["values"][names.index(name)])


def render_motion_panel(
    raw: dict[str, Any],
    effective: dict[str, Any],
    emotions: dict[str, Any],
    frame_index: int,
    width: int = 960,
    height: int = 1080,
    top_k: int = 12,
) -> tuple[Image.Image, dict[str, Any]]:
    if frame_index < 0 or frame_index >= len(effective["frames"]):
        raise IndexError("frame_index outside series")
    image = Image.new("RGB", (width, height), (11, 15, 24))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    title_color = (235, 242, 255)
    muted = (155, 170, 190)
    raw_color = (75, 120, 185)
    effective_color = (73, 216, 143)
    timestamp = float(effective["frames"][frame_index]["time_seconds"])
    draw.text((18, 14), "NVIDIA Audio2Face-3D motion", fill=title_color, font=font)
    draw.text((18, 30), f"frame {frame_index:04d}  t={timestamp:0.3f}s", fill=muted, font=font)

    # All 68 values remain visible as an ordered heat strip; raw is the upper
    # half and effective is the lower half of each cell.
    margin, top = 18, 58
    usable = max(1, width - 2 * margin)
    cell = usable / len(motion.BLENDSHAPE_NAMES)
    raw_values = effective_values = None
    raw_values = raw["frames"][min(frame_index, len(raw["frames"]) - 1)]["values"]
    effective_values = effective["frames"][frame_index]["values"]
    for index, (raw_value, value) in enumerate(zip(raw_values, effective_values)):
        x0 = int(margin + index * cell)
        x1 = max(x0 + 1, int(margin + (index + 1) * cell) - 1)
        raw_level = max(0, min(255, int(abs(float(raw_value)) * 255)))
        level = max(0, min(255, int(abs(float(value)) * 255)))
        draw.rectangle((x0, top, x1, top + 17), fill=(20, 45 + raw_level // 3, 65 + raw_level // 2))
        draw.rectangle((x0, top + 19, x1, top + 36), fill=(15, 55 + level // 2, 40 + level // 2))
    draw.text((margin, top + 41), "68 curves: raw (blue) / effective (green), canonical order", fill=muted, font=font)

    names = select_top_k(raw, effective, top_k)
    y = top + 68
    bar_x = min(240, max(120, width // 3))
    bar_width = max(60, width - bar_x - 25)
    row_height = max(15, min(25, (height - y - 170) // max(1, top_k)))
    draw.text((margin, y - 15), f"Top {top_k} active curves", fill=title_color, font=font)
    for name in names:
        raw_value = _value_at(raw, frame_index, name, "curve_names")
        value = _value_at(effective, frame_index, name, "curve_names")
        draw.text((margin, y + 2), f"{name:22s} {value: .3f}", fill=title_color, font=font)
        draw.rectangle((bar_x, y + 3, bar_x + int(bar_width * max(0.0, min(1.0, raw_value))), y + 8), fill=raw_color)
        draw.rectangle((bar_x, y + 10, bar_x + int(bar_width * max(0.0, min(1.0, value))), y + 15), fill=effective_color)
        y += row_height

    emotion_y = max(y + 8, height - 140)
    draw.text((margin, emotion_y), "Emotion conditioning", fill=title_color, font=font)
    emotion_y += 17
    for name in motion.EMOTION_NAMES:
        value = _value_at(emotions, frame_index, name, "emotion_names")
        draw.text((margin, emotion_y), f"{name:12s}", fill=muted, font=font)
        draw.rectangle((110, emotion_y + 2, 110 + int((width - 145) * max(0.0, min(1.0, value))), emotion_y + 7), fill=(222, 159, 65))
        emotion_y += 11
        if emotion_y >= height - 5:
            break
    return image, {
        "schema_version": 1,
        "frame_index": frame_index,
        "time_seconds": timestamp,
        "curve_count": len(motion.BLENDSHAPE_NAMES),
        "emotion_count": len(motion.EMOTION_NAMES),
        "top_k": names,
    }


def render_compact_motion_panel(
    raw: dict[str, Any],
    effective: dict[str, Any],
    emotions: dict[str, Any],
    frame_index: int,
    width: int = 640,
    height: int = 540,
    top_k: int = 8,
    panel_identity: dict[str, str] | None = None,
    active_curve_names: list[str] | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """Render a legible 640x540 panel designed for the triptych quadrant."""
    if width < 600 or height < 500:
        raise ValueError("compact motion panel requires at least 600x500")
    if frame_index < 0 or frame_index >= len(effective["frames"]):
        raise IndexError("frame_index outside series")
    if top_k < 1 or top_k > 8:
        raise ValueError("compact panel displays between one and eight curves")

    background = (8, 14, 24)
    surface = (15, 25, 41)
    title_color = (244, 248, 255)
    body_color = (222, 231, 244)
    muted = (156, 174, 198)
    divider = (40, 56, 78)
    raw_color = (74, 145, 230)
    effective_color = (65, 220, 139)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    title_font = _font(24, bold=True)
    section_font = _font(16, bold=True)
    curve_font = _font(18)
    value_font = _font(18, mono=True)
    timestamp_font = _font(16, mono=True)
    small_font = _font(16)
    timestamp = float(effective["frames"][frame_index]["time_seconds"])
    identity = panel_identity or {
        "panel_title": "A2F MOTION",
        "panel_model": "MODEL UNATTESTED",
        "panel_source": "RAW / EFFECTIVE",
    }
    required_identity = {"panel_title", "panel_model", "panel_source"}
    if set(identity) < required_identity:
        raise ValueError("panel_identity requires title, model, and source labels")

    margin = 20
    draw.text(
        (margin, 14), identity["panel_title"], fill=title_color, font=title_font
    )
    stamp = f"F{frame_index:04d}  {timestamp:0.3f}s"
    stamp_box = draw.textbbox((0, 0), stamp, font=timestamp_font)
    draw.text(
        (width - margin - (stamp_box[2] - stamp_box[0]), 20),
        stamp,
        fill=body_color,
        font=timestamp_font,
    )
    draw.text((margin, 53), identity["panel_model"], fill=muted, font=small_font)
    model_box = draw.textbbox((margin, 53), identity["panel_model"], font=small_font)
    source_x = min(width - 260, model_box[2] + 20)
    draw.text(
        (source_x, 53), identity["panel_source"], fill=effective_color, font=small_font
    )
    playhead_x = int(
        margin
        + (width - 2 * margin)
        * frame_index
        / max(1, len(effective["frames"]) - 1)
    )
    draw.line((margin, 77, width - margin, 77), fill=divider, width=1)
    draw.line((playhead_x, 73, playhead_x, 80), fill=title_color, width=3)

    # Every canonical curve remains represented, but the compact panel gives
    # names and tabular values only to the eight most useful active channels.
    heat_left, heat_top = margin, 82
    heat_width = width - 2 * margin
    cell_width = heat_width / len(motion.BLENDSHAPE_NAMES)
    raw_values = raw["frames"][min(frame_index, len(raw["frames"]) - 1)]["values"]
    effective_values = effective["frames"][frame_index]["values"]
    for index, (raw_value, value) in enumerate(zip(raw_values, effective_values)):
        x0 = int(heat_left + index * cell_width)
        x1 = max(x0 + 1, int(heat_left + (index + 1) * cell_width) - 1)
        raw_level = max(0.0, min(1.0, abs(float(raw_value))))
        level = max(0.0, min(1.0, abs(float(value))))
        draw.rectangle(
            (x0, heat_top, x1, heat_top + 8),
            fill=tuple(int(15 + (channel - 15) * raw_level) for channel in raw_color),
        )
        draw.rectangle(
            (x0, heat_top + 11, x1, heat_top + 21),
            fill=tuple(
                int(15 + (channel - 15) * level) for channel in effective_color
            ),
        )
    draw.text(
        (margin, 108),
        "ALL 68 CURVES · CANONICAL ORDER",
        fill=muted,
        font=small_font,
    )
    draw.line((margin, 132, width - margin, 132), fill=divider, width=1)

    names = select_frame_top_k(
        effective, frame_index, top_k, active_curve_names
    )
    draw.text((margin, 143), "TOP ACTIVE CURVES", fill=title_color, font=section_font)
    row_top = 174
    row_height = 39
    value_x = 238
    bar_x = 326
    bar_right = width - margin
    bar_width = bar_right - bar_x
    for row, name in enumerate(names):
        y = row_top + row * row_height
        raw_value = max(0.0, min(1.0, _value_at(raw, frame_index, name, "curve_names")))
        value = max(
            0.0,
            min(1.0, _value_at(effective, frame_index, name, "curve_names")),
        )
        if row % 2 == 0:
            draw.rectangle((margin - 4, y - 3, width - margin + 4, y + 32), fill=surface)
        draw.text((margin, y), name, fill=body_color, font=curve_font)
        draw.text((value_x, y), f"{value:0.3f}", fill=title_color, font=value_font)
        draw.rounded_rectangle(
            (bar_x, y + 4, bar_right, y + 15), radius=5, fill=(27, 39, 56)
        )
        if value > 0.0:
            draw.rounded_rectangle(
                (bar_x, y + 4, bar_x + int(bar_width * value), y + 15),
                radius=5,
                fill=effective_color,
            )
        if raw_value > 0.0:
            draw.rectangle(
                (bar_x, y + 24, bar_x + int(bar_width * raw_value), y + 29),
                fill=raw_color,
            )
    footer_y = row_top + top_k * row_height + 3
    draw.line((margin, footer_y, width - margin, footer_y), fill=divider, width=1)
    draw.text(
        (margin, footer_y + 10),
        "SORTED LIVE · EFFECTIVE VALUE DESCENDING",
        fill=muted,
        font=small_font,
    )
    displayed_values = [
        float(_value_at(effective, frame_index, name, "curve_names"))
        for name in names
    ]
    displayed_bar_pixels = [
        int(bar_width * max(0.0, min(1.0, value)))
        for value in displayed_values
    ]
    ace_scope = active_curve_names == list(motion.ACE25_SOURCE_CURVE_NAMES)
    pose_asset_scope = active_curve_names == list(
        motion.A2F_POSE_ASSET_EXTENDED_CURVE_NAMES
    )
    return image, {
        "schema_version": 2,
        "layout": "triptych-compact-v3",
        "frame_index": frame_index,
        "time_seconds": timestamp,
        "curve_count": len(motion.BLENDSHAPE_NAMES),
        "emotion_count": len(motion.EMOTION_NAMES),
        "displayed_curve_count": len(names),
        "displayed_emotion_count": 0,
        "minimum_font_px": 16,
        "top_k": names,
        "displayed_values": displayed_values,
        "displayed_bar_pixels": displayed_bar_pixels,
        "bar_width_pixels": bar_width,
        "sort": "current_effective_value_descending",
        "emotion_artifacts_preserved": True,
        "playhead_x": playhead_x,
        "playhead_time_seconds": timestamp,
        "panel_title": identity["panel_title"],
        "panel_model": identity["panel_model"],
        "panel_source": identity["panel_source"],
        "top_curve_scope": (
            "ACE2.5-consumed-52"
            if ace_scope
            else "A2F-pose-asset-baked-68"
            if pose_asset_scope
            else "all-A2F-68"
        ),
        "reference_only_extended_tongue_count": 16 if ace_scope else 0,
    }


def render_motion_frames(
    raw: dict[str, Any], effective: dict[str, Any], emotions: dict[str, Any],
    output_dir: Path, width: int = 960, height: int = 1080, top_k: int = 12,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    digits = max(4, len(str(max(0, len(effective["frames"]) - 1))))
    for index in range(len(effective["frames"])):
        image, _ = render_motion_panel(raw, effective, emotions, index, width, height, top_k)
        path = output_dir / f"frame.{index:0{digits}d}.png"
        image.save(path, format="PNG", optimize=False, compress_level=9)
        paths.append(path)
    return paths


def render_compact_motion_frames(
    raw: dict[str, Any],
    effective: dict[str, Any],
    emotions: dict[str, Any],
    output_dir: Path,
    width: int = 640,
    height: int = 540,
    top_k: int = 8,
    panel_identity: dict[str, str] | None = None,
    active_curve_names: list[str] | None = None,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    digits = max(4, len(str(max(0, len(effective["frames"]) - 1))))
    for index in range(len(effective["frames"])):
        image, _ = render_compact_motion_panel(
            raw,
            effective,
            emotions,
            index,
            width,
            height,
            top_k,
            panel_identity,
            active_curve_names,
        )
        path = output_dir / f"frame.{index:0{digits}d}.png"
        image.save(path, format="PNG", optimize=False, compress_level=9)
        paths.append(path)
    return paths


def build_visualization_command(ffmpeg: Path, frames: Path, output: Path, fps: int, frame_count: int) -> list[str]:
    return [
        str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
        "-framerate", str(fps), "-i", str(Path(frames) / "frame.%04d.png"),
        "-frames:v", str(frame_count), "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", str(fps), "-an", str(output),
    ]


def build_hstack_command(
    ffmpeg: Path, avatar: Path, visualization: Path, output: Path,
    fps: int, frame_count: int,
) -> list[str]:
    graph = (
        f"[0:v]fps={fps},settb=AVTB,setpts=N/({fps}*TB)[left];"
        f"[1:v]fps={fps},scale=-2:1080,settb=AVTB,"
        f"setpts=N/({fps}*TB)[right];"
        "[left][right]hstack=inputs=2[v]"
    )
    return [
        str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
        "-i", str(avatar), "-i", str(visualization), "-filter_complex", graph,
        "-map", "[v]", "-map", "0:a:0", "-frames:v", str(frame_count),
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(output),
    ]


def build_avatar_comparison_command(
    ffmpeg: Path, baseline: Path, enhanced: Path, output: Path,
    fps: int, frame_count: int,
) -> list[str]:
    graph = (
        f"[0:v]fps={fps},settb=AVTB,setpts=N/({fps}*TB)[left];"
        f"[1:v]fps={fps},settb=AVTB,setpts=N/({fps}*TB)[right];"
        "[left][right]hstack=inputs=2[v]"
    )
    return [
        str(ffmpeg), "-hide_banner", "-y", "-loglevel", "warning",
        "-i", str(baseline), "-i", str(enhanced), "-filter_complex", graph,
        "-map", "[v]", "-map", "1:a:0", "-frames:v", str(frame_count),
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(output),
    ]
