import json

import pytest

from oddyssey_mcp.baseline import load_baseline, save_baseline
from oddyssey_mcp.errors import BaselineMissingError


def test_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("ODD_DIR", str(tmp_path / "state"))
    report = {"odd_version": "1", "service": "demo", "metrics": {"x": 1}}
    path = save_baseline(report)
    assert path == tmp_path / "state" / "baseline.json"
    assert json.loads(path.read_text()) == report
    assert load_baseline() == report


def test_missing_baseline_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ODD_DIR", str(tmp_path))
    with pytest.raises(BaselineMissingError, match="odd_baseline"):
        load_baseline()
