#!/usr/bin/env python3
"""
TT-G1.3

Dedicated flow:
1) Open TikTok (after SocksDroid fake IP gate).
2) Swipe home feed 2-3 times.
3) Open Search and search keyword.
4) Return to Home tab, then close TikTok.

This script delegates to TT-G1.2 stage "b1b4" to reuse the stabilized core.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_SERIAL = "127.0.0.1:16448"
DEFAULT_KEYWORD = "bay xay dung"
DEFAULT_DELAY_MULTIPLIER = 1.35


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help="ADB serial. Default: 127.0.0.1:16448")
    parser.add_argument(
        "--keyword",
        default=DEFAULT_KEYWORD,
        help='Search keyword. Default: "bay xay dung"',
    )
    parser.add_argument(
        "--delay-multiplier",
        type=float,
        default=DEFAULT_DELAY_MULTIPLIER,
        help="Scale delays for slower, stable behavior. Default: 1.35",
    )
    args = parser.parse_args()

    if args.delay_multiplier <= 0:
        raise RuntimeError("--delay-multiplier must be > 0")

    target = Path(__file__).with_name("TT-G1.2.py")
    if not target.exists():
        raise FileNotFoundError(f"Missing target script: {target}")

    cmd = [
        sys.executable,
        str(target),
        "--stage",
        "b1b4",
        "--serial",
        args.serial,
        "--keyword",
        args.keyword,
        "--delay-multiplier",
        str(args.delay_multiplier),
    ]
    cp = subprocess.run(cmd)
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
