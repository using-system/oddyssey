"""Tests for the backend-configuration skill's machine preflight.

The script is loaded from its packaged location so the tests exercise the
very file the skill ships. Its contract is that nothing it reports is a
failure: an absent CLI, a missing store and a benchmark that is not there
are all answers the caller acts on, so the exit status stays 0.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".apm/skills/backend-configuration/scripts/preflight.py"
)

MANIFEST = """\
name: demo-load
service: demo-api
target:
  base_url_env: API_URL
  base_url_default: http://localhost:8010   # the catalog
  mcp_base_url_env: MCP_BASE_URL
  mcp_base_url_default: http://localhost:8011/mcp
identity:
  run_slug_env: RUN_SLUG   # nested on purpose
"""


def load():
    spec = importlib.util.spec_from_file_location("preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def preflight():
    return load()


def test_an_absent_cli_is_an_answer_not_an_error(preflight, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert preflight.cli("gcx") == {"present": False}


def test_a_present_cli_carries_its_version(preflight, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gcx"
    stub.write_text('#!/bin/sh\necho "gcx v9.9.9"\necho "second line"\n')
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    result = preflight.cli("gcx")
    assert result["present"] is True
    assert result["version"] == "gcx v9.9.9"


def test_a_nested_manifest_key_is_still_found(preflight, tmp_path):
    d = tmp_path / "demo-load"
    d.mkdir()
    (d / "manifest.yaml").write_text(MANIFEST)
    (d / "script.js").write_text("export default function () {}\n")
    result = preflight.benchmark(d)
    assert result["exists"] is True
    assert result["name"] == "demo-load"
    assert result["service"] == "demo-api"
    assert result["run_slug_env"] == "RUN_SLUG"
    assert result["script"] is True


def test_a_trailing_comment_is_not_part_of_a_value(preflight, tmp_path):
    d = tmp_path / "b"
    d.mkdir()
    (d / "manifest.yaml").write_text(MANIFEST)
    assert preflight.benchmark(d)["targets"] == {
        "API_URL": "http://localhost:8010",
        "MCP_BASE_URL": "http://localhost:8011/mcp",
    }


def test_a_benchmark_that_is_not_there_is_reported_not_raised(preflight, tmp_path):
    result = preflight.benchmark(tmp_path / "nope")
    assert result["exists"] is False
    assert "nope" in result["path"]


def test_a_missing_script_is_named(preflight, tmp_path):
    d = tmp_path / "b"
    d.mkdir()
    (d / "manifest.yaml").write_text("name: b\n")
    assert preflight.benchmark(d)["script"] is False


def test_stores_report_absence_and_the_newest_entries(preflight, tmp_path):
    reports = tmp_path / ".odd/observe-run-reports"
    reports.mkdir(parents=True)
    for name in (
        "2026-01-01-a.md",
        "2026-02-01-b.md",
        "2026-03-01-c.md",
        "2026-04-01-d.md",
    ):
        (reports / name).write_text("x")
    (reports / ".hidden").write_text("x")
    result = preflight.stores(tmp_path)
    store = result[".odd/observe-run-reports"]
    assert store["exists"] is True
    assert store["count"] == 4
    assert store["newest"] == ["2026-04-01-d.md", "2026-03-01-c.md", "2026-02-01-b.md"]
    assert result[".odd/benchmarks"] == {"exists": False, "count": 0, "newest": []}


def test_repo_state_outside_a_git_tree_is_unknown_not_fatal(preflight, tmp_path):
    result = preflight.repo(tmp_path)
    assert result["branch"] == "unknown"
    assert result["head"] == "unknown"


def test_repo_state_reads_the_branch_and_cleanliness(preflight, tmp_path):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }
    for args in (
        ["git", "init", "-q", "-b", "work"],
        ["git", "commit", "-q", "--allow-empty", "-m", "c"],
    ):
        subprocess.run(args, cwd=tmp_path, env=env, check=True, capture_output=True)
    clean = preflight.repo(tmp_path)
    assert clean["branch"] == "work"
    assert clean["clean"] is True
    (tmp_path / "new.txt").write_text("x")
    dirty = preflight.repo(tmp_path)
    assert dirty["clean"] is False
    assert dirty["dirty_paths"] == 1


def test_render_names_every_absent_thing(preflight):
    report = {
        "now": "2026-09-07T00:00:00Z",
        "root": "/repo",
        "clis": {"gcx": {"present": False}, "k6": {"present": False}},
        "containers": [],
        "repo": {"branch": "main", "head": "abc", "clean": False, "dirty_paths": 2},
        "stores": {".odd/benchmarks": {"exists": False, "count": 0, "newest": []}},
        "benchmark": {"exists": False, "path": "/repo/nope"},
    }
    out = preflight.render(report)
    assert "gcx=ABSENT" in out
    assert "k6=ABSENT" in out
    assert "containers none running" in out
    assert "dirty (2 paths)" in out
    assert ".odd/benchmarks: absent" in out
    assert "NOT FOUND" in out


def test_cli_exits_zero_even_when_everything_is_missing(tmp_path):
    env = dict(os.environ)
    env["PATH"] = str(tmp_path / "empty")
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    report = json.loads(p.stdout)
    assert report["clis"]["gcx"]["present"] is False
    assert report["containers"] == []
