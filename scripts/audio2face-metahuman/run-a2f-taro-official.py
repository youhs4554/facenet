#!/usr/bin/env python3
"""Compatibility entry point for the renamed generic MetaHuman CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


CANONICAL = Path(__file__).with_name("run-a2f-metahuman.py")


def main() -> None:
    print(
        "DEPRECATED: run-a2f-taro-official.py; use run-a2f-metahuman.py",
        file=sys.stderr,
        flush=True,
    )
    os.execv(sys.executable, [sys.executable, str(CANONICAL), *sys.argv[1:]])


if __name__ == "__main__":
    main()
