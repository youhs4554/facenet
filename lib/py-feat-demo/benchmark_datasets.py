#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "numpy>=2.0",
#     "opencv-python-headless>=4.10",
#     "py-feat==2.0.3",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Inspect datasets:
#      uv run benchmark_datasets.py inspect --data-root ../../data --output dataset-inventory.json
# 3. Run an AFLFP test-only evaluation:
#      uv run benchmark_datasets.py run --data-root ../../data --dataset aflfp --output-dir output
# 4. Or make executable and run:
#      chmod +x benchmark_datasets.py && ./benchmark_datasets.py --help
# ──────────────────

"""Inspect and benchmark the raw AFLFP and DISFA distributions."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Final

from pyfeat_benchmark_data import inspect_datasets
from pyfeat_benchmark_disfa_runner import (
    disfa_report_dict,
    run_disfa_benchmark,
    write_disfa_report,
)
from pyfeat_benchmark_runner import (
    aflfp_report_dict,
    run_aflfp_benchmark,
    write_aflfp_report,
)


DESCRIPTION: Final = "Inspect raw AFLFP and DISFA datasets for py-feat evaluation."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect", help="Validate raw dataset layout"
    )
    inspect_parser.add_argument("--data-root", type=Path, required=True)
    inspect_parser.add_argument("--output", type=Path, required=True)
    run_parser = subparsers.add_parser(
        "run", help="Run a deterministic test-only evaluation"
    )
    run_parser.add_argument("--data-root", type=Path, required=True)
    run_parser.add_argument("--dataset", choices=("aflfp", "disfa"), required=True)
    run_parser.add_argument("--max-samples", type=int, required=True)
    run_parser.add_argument("--seed", type=int, default=42)
    run_parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
    run_parser.add_argument("--batch-size", type=int, default=1)
    run_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        inventory = inspect_datasets(args.data_root)
        rendered = json.dumps(asdict(inventory), indent=2, sort_keys=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
        print(rendered)
        return 0
    if args.dataset == "aflfp":
        report = run_aflfp_benchmark(
            data_root=args.data_root,
            max_samples=args.max_samples,
            seed=args.seed,
            device=args.device,
            batch_size=args.batch_size,
        )
        json_path, markdown_path, csv_path = write_aflfp_report(
            report, args.output_dir
        )
        report_payload = aflfp_report_dict(report)
    else:
        report = run_disfa_benchmark(
            data_root=args.data_root,
            max_samples=args.max_samples,
            seed=args.seed,
            device=args.device,
            batch_size=args.batch_size,
        )
        json_path, markdown_path, csv_path = write_disfa_report(
            report, args.output_dir
        )
        report_payload = disfa_report_dict(report)
    print(json.dumps(report_payload, indent=2, sort_keys=True))
    print(f"json={json_path}")
    print(f"markdown={markdown_path}")
    print(f"csv={csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
