#!/usr/bin/env python3
"""Strict provenance contract for Audio2Face showcase composition."""

from __future__ import annotations

import re
from typing import Any


LINEAGE_FIELDS = (
    "source_run_id",
    "input_sha256",
    "authoritative_audio_sha256",
    "model_id",
    "architecture",
    "nim_model_id",
    "nim_endpoint",
    "curve_source_sha256",
    "curve_source",
    "fps",
    "frame_count",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
OPTIONAL_LINEAGE_FIELDS = ("head_motion_lineage",)


class LineageError(ValueError):
    """Raised before composition when any component has mixed provenance."""


def make_lineage(**values: Any) -> dict[str, Any]:
    unknown = set(values) - set(LINEAGE_FIELDS) - set(OPTIONAL_LINEAGE_FIELDS)
    missing = set(LINEAGE_FIELDS) - set(values)
    if unknown or missing:
        raise LineageError(
            f"lineage fields missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    for key in (
        "source_run_id",
        "model_id",
        "architecture",
        "nim_model_id",
        "nim_endpoint",
        "curve_source",
    ):
        value = values[key]
        if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
            raise LineageError(f"lineage {key} must be a non-empty safe string")
    for key in (
        "input_sha256",
        "authoritative_audio_sha256",
        "curve_source_sha256",
    ):
        if not isinstance(values[key], str) or not SHA256_PATTERN.fullmatch(
            values[key]
        ):
            raise LineageError(f"lineage {key} must be lowercase SHA-256")
    for key in ("fps", "frame_count"):
        value = values[key]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise LineageError(f"lineage {key} must be a positive integer")
    result = {"schema_version": 1, **{key: values[key] for key in LINEAGE_FIELDS}}
    if "head_motion_lineage" in values:
        head = values["head_motion_lineage"]
        if not isinstance(head, dict):
            raise LineageError("head_motion_lineage must be an object")
        result["head_motion_lineage"] = make_head_motion_lineage(
            **{
                key: head.get(key)
                for key in (
                    "enabled",
                    "profile",
                    "config_sha256",
                    "samples_sha256",
                    "fps",
                    "frame_count",
                )
            }
        )
    return result


def make_head_motion_lineage(**values: Any) -> dict[str, Any]:
    ordered = (
        "enabled",
        "profile",
        "config_sha256",
        "samples_sha256",
        "fps",
        "frame_count",
    )
    if set(values) != set(ordered):
        raise LineageError("head motion lineage fields are incomplete or unknown")
    if values["enabled"] is not True:
        raise LineageError("head motion lineage is only emitted when enabled")
    if values["profile"] != "subtle-conversational":
        raise LineageError("head motion lineage profile is unsupported")
    for key in ("config_sha256", "samples_sha256"):
        if not isinstance(values[key], str) or not SHA256_PATTERN.fullmatch(values[key]):
            raise LineageError(f"head motion lineage {key} must be SHA-256")
    for key in ("fps", "frame_count"):
        if not isinstance(values[key], int) or isinstance(values[key], bool) or values[key] <= 0:
            raise LineageError(f"head motion lineage {key} must be positive integer")
    return {"schema_version": 1, **{key: values[key] for key in ordered}}


def validate_compositor_lineage(
    expected: dict[str, Any], components: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    expected_normalized = make_lineage(
        **{key: expected.get(key) for key in LINEAGE_FIELDS},
        **(
            {"head_motion_lineage": expected.get("head_motion_lineage")}
            if "head_motion_lineage" in expected
            else {}
        ),
    )
    if expected_normalized["curve_source"] == "raw-ace-reinference":
        raise LineageError(
            "artifact-only ACE re-inference has request-level provenance but no "
            "captured curve SHA; strict avatar/mannequin/panel composition is refused"
        )
    required_roles = {"avatar", "mannequin", "curve_panel", "audio"}
    if set(components) != required_roles:
        raise LineageError(
            "compositor lineage requires exactly avatar, mannequin, curve_panel, audio"
        )
    component_records = {}
    for role in sorted(required_roles):
        candidate = make_lineage(
            **{key: components[role].get(key) for key in LINEAGE_FIELDS},
            **(
                {"head_motion_lineage": components[role].get("head_motion_lineage")}
                if "head_motion_lineage" in components[role]
                else {}
            ),
        )
        mismatches = {
            key: {
                "expected": expected_normalized[key],
                "actual": candidate[key],
            }
            for key in LINEAGE_FIELDS
            if candidate[key] != expected_normalized[key]
        }
        if candidate.get("head_motion_lineage") != expected_normalized.get(
            "head_motion_lineage"
        ):
            mismatches["head_motion_lineage"] = {
                "expected": expected_normalized.get("head_motion_lineage"),
                "actual": candidate.get("head_motion_lineage"),
            }
        if mismatches:
            raise LineageError(f"{role} lineage mismatch: {mismatches}")
        component_records[role] = candidate
    return {
        "schema_version": 1,
        "valid": True,
        "component_count": len(component_records),
        "expected": expected_normalized,
        "components": component_records,
        "validated_fields": list(LINEAGE_FIELDS),
    }


def showcase_identity(
    *,
    model_id: str,
    architecture: str,
    nim_model_id: str,
    curve_source: str,
    layout_id: str,
) -> dict[str, str]:
    if not re.fullmatch(r"layout-v[1-9][0-9]*", layout_id):
        raise LineageError("layout_id must use layout-vN")
    if model_id == "v3.0-diffusion" and architecture == "transformer-diffusion":
        model_token = "v30-diffusion"
        panel_title = "A2F v3.0 DIFFUSION"
    elif model_id == "v2.3-regression" and architecture == "regression":
        model_token = "v23-regression"
        panel_title = "A2F v2.3 REGRESSION"
    else:
        raise LineageError(
            f"unsupported model/architecture identity: {model_id}/{architecture}"
        )
    source_labels = {
        "effective-final-render": "EFFECTIVE / FINAL-RENDER",
        "ace-node-overrides": "ACE NODE OVERRIDES / CAPTURED",
        "raw-ace-reinference": "RAW / ACE REINFERENCE",
    }
    try:
        panel_source = source_labels[curve_source]
    except KeyError as exc:
        raise LineageError(f"unsupported curve source identity: {curve_source}") from exc
    return {
        "model_id": model_id,
        "architecture": architecture,
        "nim_model_id": nim_model_id,
        "model_token": model_token,
        "layout_id": layout_id,
        "filename_suffix": f"{model_token}-{layout_id}",
        "panel_title": panel_title,
        "panel_model": nim_model_id,
        "panel_source": panel_source,
    }
