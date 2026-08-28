#!/usr/bin/env python3

"""Pure validation helpers for Audio2Face MetaHuman and shot requests."""

from __future__ import annotations

import copy
import math
import re
from typing import Any


class AvatarResolutionError(ValueError):
    def __init__(self, message: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


class AvatarImportRequired(AvatarResolutionError):
    pass


class ShotConfigError(ValueError):
    pass


class ResumeError(ValueError):
    pass


SHOT_PRESETS: dict[str, dict[str, Any]] = {
    "close-up-front": {
        "coordinate_space": "avatar_head",
        "mode": "orbit",
        "distance_cm": 96.4,
        "azimuth_deg": 0.0,
        "elevation_deg": -4.0,
        "focal_length_mm": 40.0,
        "aperture": 16.0,
        "focus_distance_cm": 96.4,
    },
    "medium-three-quarter-left": {
        "coordinate_space": "avatar_head",
        "mode": "orbit",
        "distance_cm": 150.0,
        "azimuth_deg": -30.0,
        "elevation_deg": -3.0,
        "focal_length_mm": 50.0,
        "aperture": 8.0,
        "focus_distance_cm": 150.0,
    },
    "medium-three-quarter-right": {
        "coordinate_space": "avatar_head",
        "mode": "orbit",
        "distance_cm": 150.0,
        "azimuth_deg": 30.0,
        "elevation_deg": -3.0,
        "focal_length_mm": 50.0,
        "aperture": 8.0,
        "focus_distance_cm": 150.0,
    },
    "profile-left": {
        "coordinate_space": "avatar_head",
        "mode": "orbit",
        "distance_cm": 135.0,
        "azimuth_deg": -90.0,
        "elevation_deg": -2.0,
        "focal_length_mm": 55.0,
        "aperture": 8.0,
        "focus_distance_cm": 135.0,
    },
}

SHOT_ALIASES = {"profile": "profile-left"}
SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UNREAL_NAME = r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*"
GAME_PATH = re.compile(rf"^/Game(?:/{UNREAL_NAME})+$")


def validate_unreal_asset_reference(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("/Game/"):
        raise AvatarResolutionError("Unreal asset reference must start with /Game/")
    if ".." in value or "\\" in value or any(char.isspace() for char in value):
        raise AvatarResolutionError("Unreal asset reference contains unsafe characters")
    package, separator, object_name = value.partition(".")
    if not GAME_PATH.fullmatch(package):
        raise AvatarResolutionError("Unreal asset package path is invalid")
    if separator and object_name != package.rsplit("/", 1)[-1]:
        raise AvatarResolutionError("Unreal asset object name must match package name")
    return value


def canonicalize_avatar_path(value: str) -> str:
    validate_unreal_asset_reference(value)
    package, separator, object_name = value.partition(".")
    package_name = package.rsplit("/", 1)[-1]
    if separator:
        if not object_name or object_name != package_name:
            raise AvatarResolutionError("avatar object name must match package name")
        return value
    return f"{package}.{package_name}"


def _plain_avatar_name(value: str) -> str:
    normalized = value.strip()
    if normalized.lower().startswith("bp_"):
        normalized = normalized[3:]
    if not normalized or not re.fullmatch(UNREAL_NAME, normalized):
        raise AvatarResolutionError("avatar name is invalid")
    return normalized.casefold()


def resolve_avatar(selector: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    if selector.startswith("/"):
        canonical = canonicalize_avatar_path(selector)
        matches = [item for item in catalog if item.get("object_path") == canonical]
        method = "asset_path"
    else:
        wanted = _plain_avatar_name(selector)
        matches = []
        for item in catalog:
            asset_name = str(item.get("asset_name", ""))
            if asset_name.lower().startswith("bp_"):
                asset_name = asset_name[3:]
            if asset_name.casefold() == wanted:
                matches.append(item)
        method = "name"
    if not matches:
        raise AvatarImportRequired(f"MetaHuman avatar not found: {selector}")
    if len(matches) > 1:
        candidates = sorted(str(item["object_path"]) for item in matches)
        raise AvatarResolutionError(
            f"MetaHuman avatar is ambiguous: {selector}", candidates=candidates
        )
    resolved = dict(matches[0])
    resolved["requested"] = selector
    resolved["resolution_method"] = method
    return resolved


def _canonical_preset(name: str) -> str:
    if not isinstance(name, str):
        raise ShotConfigError("shot preset must be a string")
    canonical = SHOT_ALIASES.get(name, name)
    if canonical not in SHOT_PRESETS:
        raise ShotConfigError(f"unknown shot preset: {name}")
    return canonical


def _safe_shot_id(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 64 or not SAFE_ID.fullmatch(value):
        raise ShotConfigError("shot id must be a safe lowercase slug")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShotConfigError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ShotConfigError(f"{name} must be finite")
    return result


def _vector(value: Any, name: str, limit: float) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ShotConfigError(f"{name} must contain three numbers")
    result = [_finite_number(item, name) for item in value]
    if any(abs(item) > limit for item in result):
        raise ShotConfigError(f"{name} is outside the supported range")
    return result


def _custom_camera(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShotConfigError("camera must be an object")
    allowed = {
        "coordinate_space",
        "location_cm",
        "rotation_deg",
        "focal_length_mm",
        "aperture",
        "focus_distance_cm",
    }
    if set(value) != allowed:
        raise ShotConfigError("camera has missing or unknown keys")
    coordinate_space = value["coordinate_space"]
    if not isinstance(coordinate_space, str) or coordinate_space not in {
        "avatar_head",
        "world",
    }:
        raise ShotConfigError("camera coordinate_space must be avatar_head or world")
    focal = _finite_number(value["focal_length_mm"], "focal_length_mm")
    aperture = _finite_number(value["aperture"], "aperture")
    focus = _finite_number(value["focus_distance_cm"], "focus_distance_cm")
    if not 12.0 <= focal <= 300.0:
        raise ShotConfigError("focal_length_mm must be in [12, 300]")
    if not 1.2 <= aperture <= 32.0:
        raise ShotConfigError("aperture must be in [1.2, 32]")
    if not 1.0 <= focus <= 100000.0:
        raise ShotConfigError("focus_distance_cm must be in [1, 100000]")
    return {
        "coordinate_space": coordinate_space,
        "mode": "transform",
        "location_cm": _vector(value["location_cm"], "location_cm", 100000.0),
        "rotation_deg": _vector(value["rotation_deg"], "rotation_deg", 360.0),
        "focal_length_mm": focal,
        "aperture": aperture,
        "focus_distance_cm": focus,
    }


def resolve_named_shots(names: list[str]) -> list[dict[str, Any]]:
    requested = names or ["close-up-front"]
    result = []
    seen = set()
    for name in requested:
        canonical = _canonical_preset(name)
        shot_id = _safe_shot_id(canonical)
        if shot_id in seen:
            raise ShotConfigError(f"duplicate shot id: {shot_id}")
        seen.add(shot_id)
        result.append(
            {
                "id": shot_id,
                "preset": canonical,
                "camera": copy.deepcopy(SHOT_PRESETS[canonical]),
            }
        )
    if len(result) > 16:
        raise ShotConfigError("at most 16 shots are supported")
    return result


def validate_shot_document(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or set(document) != {"schema_version", "shots"}:
        raise ShotConfigError("shot document has missing or unknown keys")
    if document["schema_version"] != 1:
        raise ShotConfigError("unsupported shot schema_version")
    raw_shots = document["shots"]
    if not isinstance(raw_shots, list) or not 1 <= len(raw_shots) <= 16:
        raise ShotConfigError("shots must contain between 1 and 16 items")
    result = []
    seen = set()
    for item in raw_shots:
        if not isinstance(item, dict) or not set(item).issubset(
            {"id", "preset", "camera"}
        ):
            raise ShotConfigError("shot has unknown keys")
        if set(item) not in ({"id", "preset"}, {"id", "camera"}):
            raise ShotConfigError("shot must specify exactly one of preset or camera")
        shot_id = _safe_shot_id(item["id"])
        if shot_id in seen:
            raise ShotConfigError(f"duplicate shot id: {shot_id}")
        seen.add(shot_id)
        if "preset" in item:
            canonical = _canonical_preset(item["preset"])
            camera = copy.deepcopy(SHOT_PRESETS[canonical])
        else:
            canonical = None
            camera = _custom_camera(item["camera"])
        result.append({"id": shot_id, "preset": canonical, "camera": camera})
    return result


def validate_resume(
    manifest: dict[str, Any], *, input_sha256: str, config_sha256: str
) -> dict[str, Any]:
    completion = (manifest.get("status"), manifest.get("exit_code"))
    if completion not in {
        ("success", 0),
        ("manual_action_required", 45),
        ("manual_action_required", 46),
    }:
        raise ResumeError("resume run has no reusable completion boundary")
    if manifest.get("input_sha256") != input_sha256:
        raise ResumeError("resume input hash does not match")
    versions = manifest.get("versions") or {}
    if versions.get("official_claire_config_sha256") != config_sha256:
        raise ResumeError("resume config hash does not match")
    inference = manifest.get("official_nvidia_inference")
    if not isinstance(inference, dict) or not inference.get("output_dir"):
        raise ResumeError("resume manifest has no successful NVIDIA inference")
    return inference


def apply_manifest_v2(
    manifest: dict[str, Any], *, avatar: dict[str, Any], shots: list[dict[str, Any]]
) -> dict[str, Any]:
    result = dict(manifest)
    result["schema_version"] = 2
    result["avatar"] = copy.deepcopy(avatar)
    result["shots"] = copy.deepcopy(shots)
    if len(shots) == 1 and isinstance(shots[0].get("verification"), dict):
        verification = copy.deepcopy(shots[0]["verification"])
        result["verification"] = verification
        if verification.get("final_mp4"):
            result["final_mp4"] = verification["final_mp4"]
    return result
