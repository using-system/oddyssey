"""Baseline storage in the user's project (.odd/baseline.json)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import BaselineMissingError


def _odd_dir() -> Path:
    return Path(os.environ.get("ODD_DIR", ".odd"))


def _baseline_path() -> Path:
    return _odd_dir() / "baseline.json"


def save_baseline(report: dict) -> Path:
    path = _baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return path


def load_baseline() -> dict:
    path = _baseline_path()
    if not path.exists():
        raise BaselineMissingError(
            f"no baseline found at {path}; run the odd_baseline tool first"
        )
    return json.loads(path.read_text())
