#!/usr/bin/env python3
"""Build and lineage-bind a batch-one TensorRT engine from official A2F metadata."""

from __future__ import annotations

import argparse
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_shapes(values: str) -> dict[str, tuple[int, ...]]:
    result: dict[str, tuple[int, ...]] = {}
    for definition in values.split(","):
        name, shape = definition.split(":", 1)
        result[name] = tuple(int(item) for item in shape.split("x"))
    return result


def parse_trtexec_size(value: str) -> int:
    """Parse trtexec sizes; an omitted suffix means MiB, not GiB."""
    suffixes = {"B": 1, "K": 1 << 10, "M": 1 << 20, "G": 1 << 30}
    suffix = value[-1].upper() if value[-1].isalpha() else "M"
    number = value[:-1] if value[-1].isalpha() else value
    if suffix not in suffixes:
        raise ValueError(f"unsupported trtexec size suffix: {value}")
    return int(Decimal(number) * suffixes[suffix])


def resolve_build_options(
    info: dict[str, Any],
    batch_size: int = 1,
    precision_profile: str = "official",
) -> dict[str, Any]:
    defaults = dict(info.get("defaults", {}))
    defaults.update(MAX_BATCH_SIZE=batch_size, OPT_BATCH_SIZE=batch_size)
    rendered_args: list[str] = []
    for values in info.get("trt_build_param", {}).values():
        rendered_args.extend(value.format(**defaults) for value in values)

    shapes: dict[str, dict[str, tuple[int, ...]]] = {}
    memory_pools: dict[str, int] = {}
    precision_flags: list[str] = []
    for value in rendered_args:
        if value.startswith(("--minShapes=", "--optShapes=", "--maxShapes=")):
            key, definitions = value[2:].split("=", 1)
            shapes[key] = parse_shapes(definitions)
        elif value.startswith("--memPoolSize="):
            definitions = value.split("=", 1)[1]
            for definition in definitions.split(","):
                name, size = definition.split(":", 1)
                memory_pools[name] = parse_trtexec_size(size)
        elif value in {"--fp16", "--bf16", "--int8", "--fp8"}:
            precision_flags.append(value[2:])
        else:
            raise ValueError(f"unsupported official TensorRT build option: {value}")
    if precision_profile not in {"official", "nim-fp16"}:
        raise ValueError(f"unsupported precision profile: {precision_profile}")
    if precision_profile == "nim-fp16":
        if precision_flags and precision_flags != ["fp16"]:
            raise ValueError("NIM FP16 profile conflicts with official precision flags")
        precision_flags = ["fp16"]
    if len(precision_flags) > 1:
        raise ValueError(f"multiple precision modes are unsupported: {precision_flags}")
    for required in ("minShapes", "optShapes", "maxShapes"):
        if required not in shapes:
            raise ValueError(f"missing official {required} build option")
    return {
        "official_rendered_args": rendered_args,
        "precision": precision_flags[0] if precision_flags else "fp32",
        "precision_profile": precision_profile,
        "precision_source": (
            "explicit-nim-comparison-profile"
            if precision_profile == "nim-fp16"
            else "official-trt-info"
        ),
        "memory_pools": memory_pools,
        "shapes": shapes,
        "batch_size": batch_size,
    }


def engine_manifest_payload(
    *,
    onnx: Path,
    trt_info: Path,
    engine: Path,
    build_options: dict[str, Any],
    tensorrt_version: str,
    compute_capability: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "pass",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sdk_commit": "1ca0f02535ed774f5dbcd724a31cd486368dc783",
        "model_revision": "Audio2Face-3D-v3.0-b741327/multi_v3.2",
        "onnx_sha256": sha256(onnx),
        "trt_info_sha256": sha256(trt_info),
        "engine_sha256": sha256(engine),
        "engine_size_bytes": engine.stat().st_size,
        "tensorrt_version": tensorrt_version,
        "compute_capability": compute_capability,
        "build_options": build_options,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def verify_engine_manifest(
    *, onnx: Path, trt_info: Path, engine: Path, manifest: Path
) -> dict[str, Any]:
    if not manifest.is_file() or not engine.is_file():
        raise RuntimeError("engine and engine manifest must both exist")
    payload = json.loads(manifest.read_text())
    expected = {
        "onnx_sha256": sha256(onnx),
        "trt_info_sha256": sha256(trt_info),
        "engine_sha256": sha256(engine),
        "engine_size_bytes": engine.stat().st_size,
    }
    mismatches = {
        key: {"manifest": payload.get(key), "actual": value}
        for key, value in expected.items()
        if payload.get(key) != value
    }
    if mismatches:
        raise RuntimeError("engine lineage mismatch: " + ", ".join(sorted(mismatches)))
    return {"status": "pass", "manifest": str(manifest), **expected}


def _compute_capability() -> str:
    return subprocess.check_output(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader,nounits"],
        text=True,
    ).strip().splitlines()[0]


def build_engine(
    *,
    onnx: Path,
    trt_info: Path,
    output: Path,
    manifest: Path,
    precision_profile: str = "official",
) -> dict[str, Any]:
    import tensorrt as trt

    info = json.loads(trt_info.read_text())
    options = resolve_build_options(
        info, batch_size=1, precision_profile=precision_profile
    )
    logger = trt.Logger(trt.Logger.INFO)
    builder = trt.Builder(logger)
    network = builder.create_network(
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    )
    onnx_parser = trt.OnnxParser(network, logger)
    if not onnx_parser.parse(onnx.read_bytes()):
        errors = [str(onnx_parser.get_error(index)) for index in range(onnx_parser.num_errors)]
        raise RuntimeError("ONNX parse failed: " + " | ".join(errors))
    config = builder.create_builder_config()
    precision = options["precision"]
    if precision == "fp16":
        config.set_flag(trt.BuilderFlag.FP16)
    elif precision != "fp32":
        raise RuntimeError(f"unsupported TensorRT Python precision mode: {precision}")
    pool_types = {"tacticSharedMem": trt.MemoryPoolType.TACTIC_SHARED_MEMORY}
    for name, size_bytes in options["memory_pools"].items():
        if name not in pool_types:
            raise RuntimeError(f"unsupported TensorRT memory pool: {name}")
        config.set_memory_pool_limit(pool_types[name], size_bytes)
    profile = builder.create_optimization_profile()
    shapes = options["shapes"]
    for name in shapes["minShapes"]:
        profile.set_shape(
            name,
            shapes["minShapes"][name],
            shapes["optShapes"][name],
            shapes["maxShapes"][name],
        )
    config.add_optimization_profile(profile)
    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        raise RuntimeError("TensorRT engine build returned no serialized network")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(bytes(serialized))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output)
    payload = engine_manifest_payload(
        onnx=onnx,
        trt_info=trt_info,
        engine=output,
        build_options=options,
        tensorrt_version=trt.__version__,
        compute_capability=_compute_capability(),
    )
    _atomic_json(manifest, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    children = {}
    for command in ("build", "verify"):
        child = subparsers.add_parser(command)
        children[command] = child
        child.add_argument("--onnx", type=Path, required=True)
        child.add_argument("--trt-info", type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
        child.add_argument("--manifest", type=Path, required=True)
    children["build"].add_argument(
        "--precision-profile", choices=("official", "nim-fp16"), default="official"
    )
    args = parser.parse_args()
    if args.command == "build":
        report = build_engine(
            onnx=args.onnx,
            trt_info=args.trt_info,
            output=args.output,
            manifest=args.manifest,
            precision_profile=args.precision_profile,
        )
    else:
        report = verify_engine_manifest(
            onnx=args.onnx,
            trt_info=args.trt_info,
            engine=args.output,
            manifest=args.manifest,
        )
        import tensorrt as trt

        payload = json.loads(args.manifest.read_text())
        if payload.get("tensorrt_version") != trt.__version__:
            raise RuntimeError("engine TensorRT runtime version mismatch")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
