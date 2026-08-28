"""Strict provenance and lineage gates for Audio2Face cross-avatar runs."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


LISTING_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
PRESET_ID_RE = re.compile(r"^[A-Za-z0-9]{8}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
REQUIRED_TAGS = frozenset({"asian", "metahuman", "editable"})
CROSS_AVATAR_LINEAGE_FIELDS = (
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
MANUAL_STAGES = frozenset(
    {
        "login",
        "mfa",
        "cloudflare",
        "account_verification",
        "eula",
        "license_acceptance",
        "assembly_unsupported",
        "import_unsupported",
    }
)
REQUIRED_AVATAR_ROLES = frozenset(
    {"elderly_asian_male", "elderly_asian_female"}
)
ELDERLY_METADATA_VALUES = frozenset(
    {"old", "elderly", "senior", "aged", "mature"}
)


class FabCandidateError(ValueError):
    """Raised when a Fab candidate does not meet the acquisition contract."""


class CrossAvatarError(ValueError):
    """Raised when a cross-avatar comparison changes more than the avatar."""


class AvatarMatrixError(ValueError):
    """Raised when the required two-avatar qualification matrix is incomplete."""


def _required_text(value: Any, field: str, *, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise FabCandidateError(f"{field} must be non-empty text")
    return value.strip()


def validate_fab_candidate(candidate: Any) -> dict[str, Any]:
    """Validate official-surface metadata before a free Fab acquisition."""

    if not isinstance(candidate, dict):
        raise FabCandidateError("candidate must be an object")
    listing_id = _required_text(candidate.get("listing_id"), "listing_id", limit=64)
    if not LISTING_ID_RE.fullmatch(listing_id):
        raise FabCandidateError("listing_id must be a Fab UUID")
    listing_url = _required_text(candidate.get("listing_url"), "listing_url")
    parsed = urlparse(listing_url)
    expected_path = f"/listings/{listing_id}"
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"fab.com", "www.fab.com"}
        or parsed.path.rstrip("/") != expected_path
        or parsed.username
        or parsed.password
    ):
        raise FabCandidateError("listing_url must be the canonical HTTPS Fab listing")
    if _required_text(candidate.get("price"), "price").casefold() != "free":
        raise FabCandidateError("only a Free Fab listing may be acquired")
    tags = candidate.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise FabCandidateError("tags must be a string list")
    normalized_tags = {tag.strip().casefold() for tag in tags}
    if not REQUIRED_TAGS.issubset(normalized_tags):
        raise FabCandidateError("official metadata must include Asian, MetaHuman, Editable")
    formats = candidate.get("formats")
    if not isinstance(formats, list) or "metahuman" not in {
        str(item).strip().casefold() for item in formats
    }:
        raise FabCandidateError("listing must include the MetaHuman format")
    if _required_text(candidate.get("license"), "license").casefold() != "standard":
        raise FabCandidateError("MetaHuman acquisition must use the Fab Standard License")
    if candidate.get("no_ai") is not True:
        raise FabCandidateError("the mandatory MetaHuman NoAI provenance must be recorded")
    if candidate.get("intended_use") != "runtime_animation":
        raise FabCandidateError("candidate is approved only for runtime animation")

    publisher = _required_text(candidate.get("publisher"), "publisher")
    return {
        "schema_version": 1,
        "listing_id": listing_id.lower(),
        "listing_url": listing_url,
        "title": _required_text(candidate.get("title"), "title"),
        "publisher": publisher,
        "price": "Free",
        "required_tags": ["Asian", "Editable", "MetaHuman"],
        "formats": ["MetaHuman"],
        "license": "Standard",
        "no_ai": True,
        "intended_use": "runtime_animation",
        "epic_authored": publisher.casefold() == "epic games",
        "acquisition_surface": "official-fab",
    }


def manual_action_boundary(*, stage: str, reason: str, evidence: str) -> dict[str, Any]:
    """Return a credential-safe Phase A stop record."""

    if stage not in MANUAL_STAGES:
        raise FabCandidateError(f"unsupported manual action stage: {stage}")
    return {
        "schema_version": 1,
        "status": "manual_action_required",
        "phase": "A",
        "stage": stage,
        "reason": _required_text(reason, "reason", limit=2048),
        "evidence": _required_text(evidence, "evidence", limit=2048),
        "phase_b_allowed": False,
    }


def _avatar_path(manifest: dict[str, Any]) -> str:
    avatar = manifest.get("avatar")
    if not isinstance(avatar, dict):
        raise CrossAvatarError("manifest has no avatar object")
    path = avatar.get("canonical_asset_path") or avatar.get("object_path")
    if not isinstance(path, str) or not path.startswith("/Game/MetaHumans/"):
        raise CrossAvatarError("avatar canonical path is missing or out of scope")
    if avatar.get("source_asset_modified") is not False:
        raise CrossAvatarError("source MetaHuman asset modification is not permitted")
    return path


def validate_cross_avatar_pair(
    baseline: Any, candidate: Any
) -> dict[str, Any]:
    """Prove that a benchmark pair differs only by its MetaHuman asset."""

    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise CrossAvatarError("both manifests must be objects")
    if baseline.get("status") != "success" or candidate.get("status") != "success":
        raise CrossAvatarError("both runs must be successful")
    baseline_avatar = _avatar_path(baseline)
    candidate_avatar = _avatar_path(candidate)
    if baseline_avatar == candidate_avatar:
        raise CrossAvatarError("cross-avatar benchmark requires distinct avatars")
    baseline_lineage = baseline.get("compositor_lineage")
    candidate_lineage = candidate.get("compositor_lineage")
    if not isinstance(baseline_lineage, dict) or not isinstance(candidate_lineage, dict):
        raise CrossAvatarError("both manifests require compositor lineage")
    mismatches = [
        field
        for field in CROSS_AVATAR_LINEAGE_FIELDS
        if baseline_lineage.get(field) != candidate_lineage.get(field)
        or baseline_lineage.get(field) is None
    ]
    if mismatches:
        raise CrossAvatarError(
            "cross-avatar lineage mismatch: " + ", ".join(mismatches)
        )
    if baseline_lineage["model_id"] != "v3.0-diffusion":
        raise CrossAvatarError("cross-avatar gate requires v3.0-diffusion")

    return {
        "schema_version": 1,
        "valid": True,
        "changed_dimension": "avatar_only",
        "baseline_avatar": baseline_avatar,
        "candidate_avatar": candidate_avatar,
        "shared_curve_sha256": baseline_lineage["curve_source_sha256"],
        "shared_source_run_id": baseline_lineage["source_run_id"],
        "checked_fields": list(CROSS_AVATAR_LINEAGE_FIELDS),
    }


def classify_taro_acquisition_route(evidence: Any) -> dict[str, Any]:
    """Classify the historical Taro route without treating it as policy approval."""

    if not isinstance(evidence, dict):
        raise AvatarMatrixError("Taro provenance evidence must be an object")
    character_id = evidence.get("character_id")
    catalog = urlparse(str(evidence.get("catalog_url") or ""))
    download = urlparse(str(evidence.get("download_api") or ""))
    if (
        character_id != "k8bukITg"
        or catalog.scheme != "https"
        or catalog.hostname != "mhc-api.quixel.com"
        or "/characters/presets/list" not in catalog.path
        or download.scheme != "https"
        or download.hostname != "mhc-api.quixel.com"
        or f"/characters/presets/{character_id}/download" not in download.path
    ):
        raise AvatarMatrixError("evidence does not identify the official Taro preset route")
    if (
        evidence.get("bundle_format") != "preassembled_ue_zip"
        or evidence.get("import_operation") != "unzip_no_overwrite"
        or evidence.get("editable_mhc_asset_present") is not False
        or evidence.get("sample_project_source") is not False
    ):
        raise AvatarMatrixError("Taro bundle/import evidence is inconsistent")

    credential_contents_read = (
        evidence.get("credential_source") == "bridge_token_file_contents"
    )
    official_ui_import = (
        evidence.get("download_executor") == "bridge_ui"
        and evidence.get("import_operation") == "bridge_add"
    )
    return {
        "schema_version": 1,
        "classification": "A_bridge_preassembled",
        "character_id": character_id,
        "canonical_asset": evidence.get("canonical_asset"),
        "bundle_format": "preassembled_ue_zip",
        "export_quality": evidence.get("export_quality"),
        "export_tool_version": evidence.get("export_tool_version"),
        "official_ui_import": official_ui_import,
        "credential_contents_read": credential_contents_read,
        "reusable_under_current_policy": official_ui_import
        and not credential_contents_read,
        "policy_blocker": (
            "credential_file_contents_were_read"
            if credential_contents_read
            else None
        ),
    }


def _matrix_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise AvatarMatrixError(f"{field} must be non-empty text")
    return value.strip()


def _qualify_visual_bridge_preset(
    role: str, candidate: dict[str, Any]
) -> dict[str, Any]:
    """Validate an explicitly user-authorized visual estimate without relabeling it metadata."""

    expected_gender = "Male" if role.endswith("_male") else "Female"
    character_id = _matrix_text(candidate.get("character_id"), "character_id")
    if not PRESET_ID_RE.fullmatch(character_id):
        raise AvatarMatrixError("Bridge preset character_id is invalid")
    if _matrix_text(candidate.get("price"), "price").casefold() != "free":
        raise AvatarMatrixError("candidate must be Free")
    if candidate.get("format") != "preassembled_ue_zip":
        raise AvatarMatrixError("visual Bridge candidate must be a preassembled UE zip")
    if candidate.get("linux_ue56_supported") is not True:
        raise AvatarMatrixError("Linux UE 5.6 support must be explicit")
    if candidate.get("source") != "official_bridge_preset_catalog":
        raise AvatarMatrixError("visual selection is limited to the official Bridge catalog")

    source_url = urlparse(_matrix_text(candidate.get("source_url"), "source_url"))
    if (
        source_url.scheme != "https"
        or source_url.hostname != "mhc-api.quixel.com"
        or source_url.path.rstrip("/") != "/v1/mhc/characters/presets/list"
    ):
        raise AvatarMatrixError("source_url must identify the official Bridge preset list")
    preview_url = urlparse(
        _matrix_text(candidate.get("preview_url"), "preview_url")
    )
    if (
        preview_url.scheme != "https"
        or preview_url.hostname
        != "quixel-mhc-presets-previews.s3-us-west-2.amazonaws.com"
        or f"/{character_id}/previews/" not in preview_url.path
    ):
        raise AvatarMatrixError("preview_url must be the official preset preview")
    preview_sha256 = _matrix_text(
        candidate.get("preview_sha256"), "preview_sha256"
    ).lower()
    if not SHA256_RE.fullmatch(preview_sha256):
        raise AvatarMatrixError("preview_sha256 must be a SHA-256 digest")

    assessment = candidate.get("visual_assessment")
    if not isinstance(assessment, dict):
        raise AvatarMatrixError("visual_assessment must be an object")
    if assessment.get("user_authorized") is not True:
        raise AvatarMatrixError("visual demographic estimation requires user authorization")
    if assessment.get("limitations_acknowledged") is not True:
        raise AvatarMatrixError("visual-estimate limitations must be acknowledged")
    ethnicity = _matrix_text(
        assessment.get("ethnicity_appearance"),
        "visual_assessment.ethnicity_appearance",
    )
    gender = _matrix_text(
        assessment.get("gender_presentation"),
        "visual_assessment.gender_presentation",
    )
    age = _matrix_text(
        assessment.get("age_appearance"), "visual_assessment.age_appearance"
    )
    if ethnicity.casefold() != "asian":
        raise AvatarMatrixError("visual ethnicity appearance must be Asian")
    if gender.casefold() != expected_gender.casefold():
        raise AvatarMatrixError(
            f"visual gender presentation must be {expected_gender} for {role}"
        )
    if age.casefold() not in ELDERLY_METADATA_VALUES:
        raise AvatarMatrixError("visual age appearance must indicate old age")

    return {
        "schema_version": 1,
        "role": role,
        "character_id": character_id,
        "name": _matrix_text(candidate.get("name"), "name"),
        "source": "official_bridge_preset_catalog",
        "source_url": source_url.geturl(),
        "preview_url": preview_url.geturl(),
        "preview_sha256": preview_sha256,
        "price": "Free",
        "format": "preassembled_ue_zip",
        "linux_ue56_supported": True,
        "selection_basis": "user_authorized_visual_assessment",
        "metadata_provenance": "visual_estimate_not_demographic_metadata",
        "visual_assessment": {
            "user_authorized": True,
            "ethnicity_appearance": "Asian",
            "gender_presentation": expected_gender,
            "age_appearance": age,
            "limitations_acknowledged": True,
        },
        "license": _matrix_text(candidate.get("license"), "license"),
        "disclaimer": (
            "Appearance-based selection authorized by the user; this is not official "
            "demographic metadata and does not establish a person's identity."
        ),
    }


def qualify_avatar_role(role: str, candidate: Any) -> dict[str, Any]:
    """Require explicit official demographic and platform metadata for a slot."""

    if role not in REQUIRED_AVATAR_ROLES:
        raise AvatarMatrixError(f"unsupported avatar role: {role}")
    if not isinstance(candidate, dict):
        raise AvatarMatrixError("candidate must be an object")
    if candidate.get("role", role) != role:
        raise AvatarMatrixError("candidate role does not match the requested slot")
    if candidate.get("selection_basis") == "user_authorized_visual_assessment":
        return _qualify_visual_bridge_preset(role, candidate)
    metadata = candidate.get("metadata")
    if not isinstance(metadata, dict):
        raise AvatarMatrixError("explicit demographic metadata is required")
    ethnicity = _matrix_text(metadata.get("ethnicity"), "metadata.ethnicity")
    gender = _matrix_text(metadata.get("gender"), "metadata.gender")
    age = _matrix_text(metadata.get("age"), "metadata.age")
    expected_gender = "Male" if role.endswith("_male") else "Female"
    if ethnicity.casefold() != "asian":
        raise AvatarMatrixError("official ethnicity metadata must be Asian")
    if gender.casefold() != expected_gender.casefold():
        raise AvatarMatrixError(
            f"official gender metadata must be {expected_gender} for {role}"
        )
    if age.casefold() not in ELDERLY_METADATA_VALUES:
        raise AvatarMatrixError("official age metadata must explicitly indicate old age")
    if _matrix_text(candidate.get("price"), "price").casefold() != "free":
        raise AvatarMatrixError("candidate must be Free")
    asset_format = _matrix_text(candidate.get("format"), "format")
    if asset_format not in {"preassembled_ue_zip", "assembled_metahuman", "mhpkg"}:
        raise AvatarMatrixError("candidate format is not a supported MetaHuman format")
    if candidate.get("linux_ue56_supported") is not True:
        raise AvatarMatrixError("Linux UE 5.6 support must be explicit")
    source = _matrix_text(candidate.get("source"), "source")
    source_url = urlparse(_matrix_text(candidate.get("source_url"), "source_url"))
    if source != "official_catalog" or source_url.scheme != "https":
        raise AvatarMatrixError("candidate must come from an official HTTPS catalog")

    return {
        "schema_version": 1,
        "role": role,
        "character_id": _matrix_text(candidate.get("character_id"), "character_id"),
        "name": _matrix_text(candidate.get("name"), "name"),
        "source": source,
        "source_url": source_url.geturl(),
        "price": "Free",
        "format": asset_format,
        "linux_ue56_supported": True,
        "metadata": {
            "ethnicity": "Asian",
            "gender": expected_gender,
            "age": age,
        },
        "license": _matrix_text(candidate.get("license"), "license"),
    }


def validate_required_avatar_matrix(candidates: Any) -> dict[str, Any]:
    """Validate the two mandatory, distinct demographic slots."""

    if not isinstance(candidates, list) or len(candidates) != 2:
        raise AvatarMatrixError("exactly two avatar candidates are required")
    roles = [candidate.get("role") if isinstance(candidate, dict) else None for candidate in candidates]
    if set(roles) != REQUIRED_AVATAR_ROLES:
        raise AvatarMatrixError("both required avatar roles must be present exactly once")
    qualified = [
        qualify_avatar_role(str(candidate["role"]), candidate)
        for candidate in candidates
    ]
    character_ids = [item["character_id"] for item in qualified]
    if len(set(character_ids)) != len(character_ids):
        raise AvatarMatrixError("the two roles must use distinct MetaHuman characters")
    if {item["name"].casefold() for item in qualified} & {"taro", "jesse"}:
        raise AvatarMatrixError("Taro and Jesse cannot fill a new avatar slot")
    return {
        "schema_version": 1,
        "status": "qualified",
        "roles": {item["role"]: item for item in qualified},
    }


def phase_a_matrix_gate(results: Any) -> dict[str, Any]:
    """Permit Phase B only after both avatar E2E results pass every gate."""

    if not isinstance(results, dict):
        raise AvatarMatrixError("Phase A results must be an object")
    missing_roles = REQUIRED_AVATAR_ROLES - set(results)
    extra_roles = set(results) - REQUIRED_AVATAR_ROLES
    if missing_roles or extra_roles:
        raise AvatarMatrixError("Phase A results must contain both required roles only")
    required_checks = ("acquired", "imported", "readiness", "same_lineage_e2e")
    failed = {}
    for role in sorted(REQUIRED_AVATAR_ROLES):
        result = results.get(role)
        if not isinstance(result, dict):
            raise AvatarMatrixError(f"{role} result must be an object")
        failed_checks = [check for check in required_checks if result.get(check) is not True]
        if failed_checks:
            failed[role] = failed_checks
    return {
        "schema_version": 1,
        "status": "pass" if not failed else "partial",
        "phase_b_allowed": not failed,
        "failed": failed,
        "required_roles": sorted(REQUIRED_AVATAR_ROLES),
    }
