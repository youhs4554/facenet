#!/usr/bin/env python3
"""Host-safety gates and non-impact evidence for the A2F v3 SDK sidecar."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = (ROOT / ".tools/audio2face3d/sdk-v3-geometry").resolve()


def _run(argv: list[str]) -> str:
    completed = subprocess.run(
        argv, check=True, capture_output=True, text=True, timeout=30
    )
    return completed.stdout.strip()


def gpu_inventory(index: int = 1) -> dict[str, Any]:
    rows = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,compute_cap,memory.total,memory.used,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    ).splitlines()
    for row in rows:
        values = [item.strip() for item in row.split(",")]
        if int(values[0]) == index:
            return {
                "index": index,
                "name": values[1],
                "compute_capability": values[2],
                "total_mib": int(values[3]),
                "used_mib": int(values[4]),
                "free_mib": int(values[5]),
                "driver_version": values[6],
            }
    raise RuntimeError(f"GPU index {index} is unavailable")


def runtime_preflight(minimum_free_mib: int = 8192) -> dict[str, Any]:
    if minimum_free_mib < 1024:
        raise ValueError("minimum_free_mib must be at least 1024")
    gpu = gpu_inventory(1)
    allowed = int(gpu["free_mib"]) >= minimum_free_mib
    return {
        "schema_version": 1,
        "status": "pass" if allowed else "blocked_vram",
        "phase": "B",
        "phase_b_runtime_allowed": allowed,
        "gpu": gpu,
        "minimum_for_attempt_free_mib": minimum_free_mib,
        "verified_safe_free_vram_mib": None,
        "threshold_basis": (
            "conservative unverified minimum for an isolated attempt; an actual successful "
            "peak measurement with headroom has not yet been obtained"
        ),
        "shortfall_mib": max(0, minimum_free_mib - int(gpu["free_mib"])),
        "automatic_container_stop": False,
        "required_user_authorization": (
            None
            if allowed
            else "Temporarily stop an existing GPU1 NIM service, then restore it after the SDK run."
        ),
    }


def _cuda_link_state() -> dict[str, Any]:
    path = Path("/usr/local/cuda")
    if not path.exists() and not path.is_symlink():
        return {"exists": False}
    stat = path.lstat()
    return {
        "exists": True,
        "is_symlink": path.is_symlink(),
        "target": os.readlink(path) if path.is_symlink() else None,
        "inode": stat.st_ino,
        "mode": stat.st_mode,
    }


def host_snapshot() -> dict[str, Any]:
    containers = []
    for line in _run(["docker", "ps", "--format", "{{json .}}"] ).splitlines():
        if line:
            record = json.loads(line)
            container_id = record.get("ID")
            inspection = json.loads(_run(["docker", "inspect", container_id]))[0]
            containers.append(
                {
                    "name": record.get("Names"),
                    "id": inspection.get("Id"),
                    "image": inspection.get("Config", {}).get("Image"),
                    "image_id": inspection.get("Image"),
                    "state": inspection.get("State", {}).get("Status"),
                    "running": inspection.get("State", {}).get("Running"),
                    "restart_count": inspection.get("RestartCount"),
                }
            )
    unreal_processes = []
    query = subprocess.run(
        ["pgrep", "-af", "[U]nrealEditor"], capture_output=True, text=True, timeout=10
    )
    if query.returncode == 0:
        for line in query.stdout.splitlines():
            pid, _, command = line.partition(" ")
            unreal_processes.append({"pid": int(pid), "command": command})
    return {
        "schema_version": 1,
        "status": "pass",
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "gpu0": gpu_inventory(0),
        "gpu1": gpu_inventory(1),
        "nvcc": _run(["nvcc", "--version"]),
        "cuda_link": _cuda_link_state(),
        "host_tensorrt_python_available": importlib.util.find_spec("tensorrt") is not None,
        "running_containers": sorted(containers, key=lambda item: str(item["name"])),
        "unreal_processes": unreal_processes,
        "selected_environment": {
            name: os.environ.get(name)
            for name in ("CUDA_HOME", "CUDA_PATH", "TENSORRT_ROOT_DIR")
        },
    }


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    stable_fields = ("nvcc", "cuda_link", "host_tensorrt_python_available", "selected_environment")
    mismatches = {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in stable_fields
        if before.get(field) != after.get(field)
    }
    for field in ("gpu0", "gpu1"):
        identity_fields = ("index", "name", "compute_capability", "total_mib", "driver_version")
        before_identity = {key: before.get(field, {}).get(key) for key in identity_fields}
        after_identity = {key: after.get(field, {}).get(key) for key in identity_fields}
        if before_identity != after_identity:
            mismatches[field] = {"before": before_identity, "after": after_identity}
    if before.get("unreal_processes", []) != after.get("unreal_processes", []):
        mismatches["unreal_processes"] = {
            "before": before.get("unreal_processes", []),
            "after": after.get("unreal_processes", []),
        }
    before_containers = {
        item["name"]: item for item in before.get("running_containers", [])
    }
    after_containers = {
        item["name"]: item for item in after.get("running_containers", [])
    }
    before_names = set(before_containers)
    after_names = set(after_containers)
    missing_containers = sorted(before_names - after_names)
    compared_container_fields = (
        "id", "image", "image_id", "state", "running", "restart_count"
    )
    container_mismatches = {}
    for name in sorted(before_names & after_names):
        before_state = {
            key: before_containers[name].get(key) for key in compared_container_fields
        }
        after_state = {
            key: after_containers[name].get(key) for key in compared_container_fields
        }
        if before_state != after_state:
            container_mismatches[name] = {
                "before": before_state,
                "after": after_state,
            }
    return {
        "schema_version": 1,
        "status": (
            "pass"
            if not mismatches and not missing_containers and not container_mismatches
            else "changed"
        ),
        "host_state_mismatches": mismatches,
        "container_state_mismatches": container_mismatches,
        "preexisting_containers_missing": missing_containers,
        "global_paths_unchanged": not mismatches,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_phase_a_result(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("phase") != "A" or payload.get("status") != "pass":
        raise ValueError("Phase A result must have phase=A and status=pass")
    if payload.get("phase_b_allowed") is not True:
        raise ValueError("Phase A result does not allow Phase B")
    shared_curve = payload.get("shared_curve_sha256")
    if not isinstance(shared_curve, str) or len(shared_curve) != 64:
        raise ValueError("Phase A shared curve SHA-256 is missing")
    required_roles = ("elderly_asian_male", "elderly_asian_female")
    avatars = payload.get("avatars", {})
    if set(required_roles) - set(avatars):
        raise ValueError("Phase A result is missing one or more required avatar roles")
    names = [avatars[role].get("name") for role in required_roles]
    ids = [avatars[role].get("character_id") for role in required_roles]
    if len(set(names)) != len(names) or len(set(ids)) != len(ids):
        raise ValueError("Phase A avatar roles must reference distinct characters")
    checked_artifacts: list[dict[str, Any]] = []
    for role in required_roles:
        avatar = avatars[role]
        for field in ("manifest", "avatar_mp4", "triptych_mp4"):
            path = Path(avatar.get(field, "")).expanduser().resolve()
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"Phase A {role} {field} is missing: {path}")
            checked_artifacts.append(
                {"role": role, "field": field, "path": str(path), "sha256": _sha256(path)}
            )
        manifest = json.loads(Path(avatar["manifest"]).read_text())
        lineage = manifest.get("motion_artifacts", {}).get("lineage", {})
        expected = {
            "curve_source_sha256": shared_curve,
            "model_id": "v3.0-diffusion",
            "nim_model_id": "multi_v3.2",
        }
        mismatches = {
            key: {"expected": value, "actual": lineage.get(key)}
            for key, value in expected.items()
            if lineage.get(key) != value
        }
        if mismatches:
            raise ValueError(f"Phase A {role} lineage mismatch: {mismatches}")
    benchmark = payload.get("benchmark", {})
    benchmark_path = Path(benchmark.get("path", "")).expanduser().resolve()
    if not benchmark_path.is_file() or _sha256(benchmark_path) != benchmark.get("sha256"):
        raise ValueError("Phase A benchmark is missing or its SHA-256 does not match")
    return {
        "schema_version": 1,
        "status": "pass",
        "phase": "A",
        "phase_b_allowed": True,
        "required_roles": list(required_roles),
        "avatar_names": names,
        "shared_curve_sha256": shared_curve,
        "benchmark": {"path": str(benchmark_path), "sha256": _sha256(benchmark_path)},
        "checked_artifacts": checked_artifacts,
    }


def _safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved != OUTPUT_ROOT and OUTPUT_ROOT not in resolved.parents:
        raise ValueError(f"output must stay under {OUTPUT_ROOT}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _write(path: Path, payload: dict[str, Any]) -> None:
    path = _safe_output(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--output", type=Path, required=True)
    preflight_parser.add_argument("--minimum-free-mib", type=int, default=8192)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--before", type=Path, required=True)
    compare_parser.add_argument("--after", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    phase_a_parser = subparsers.add_parser("phase-a")
    phase_a_parser.add_argument("--input", type=Path, required=True)
    phase_a_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        report = host_snapshot()
    elif args.command == "preflight":
        report = runtime_preflight(args.minimum_free_mib)
    elif args.command == "compare":
        report = compare_snapshots(
            json.loads(args.before.read_text()), json.loads(args.after.read_text())
        )
    else:
        report = validate_phase_a_result(json.loads(args.input.read_text()))
    _write(args.output, report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") in {"pass"} else 42


if __name__ == "__main__":
    raise SystemExit(main())
