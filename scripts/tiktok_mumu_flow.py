#!/usr/bin/env python3
"""
Compatibility wrapper.
Primary script moved to TT-G1.1.py.
"""

from pathlib import Path
import runpy

TARGET = Path(__file__).with_name("TT-G1.1.py")
if not TARGET.exists():
    raise FileNotFoundError(f"Missing target script: {TARGET}")

runpy.run_path(str(TARGET), run_name="__main__")
