"""Tests for the setup-local-stack skill's gcx bootstrap.

The script is loaded from its packaged location so the tests exercise the
very file the skill ships. Its two claims are that the ports are read
from the global configuration rather than assumed, and that the context
is rewritten whole - a patched `server:` line leaves gcx's credential
binding stale, which is the bug the script exists to prevent.
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
    / ".apm/skills/setup-local-stack/scripts/gcx_local.py"
)


def load(monkeypatch, home: Path, tmpdir: Path):
    monkeypatch.setenv("TMPDIR", str(tmpdir))
    monkeypatch.setenv("HOME", str(home))
    spec = importlib.util.spec_from_file_location("gcx_local", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CONFIG_PATH = home / ".oddyssey" / "config.json"
    return module


def write_config(home: Path, local: dict) -> None:
    path = home / ".oddyssey"
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(json.dumps({"local": local}))


def test_ports_default_when_no_configuration_exists(monkeypatch, tmp_path):
    module = load(monkeypatch, tmp_path / "home", tmp_path / "tmp")
    assert module.ports() == module.DEFAULT_PORTS


def test_ports_come_from_the_global_configuration(monkeypatch, tmp_path):
    home = tmp_path / "home"
    module = load(monkeypatch, home, tmp_path / "tmp")
    write_config(home, {"grafana_port": 3001, "otlp_http_port": 4319})
    resolved = module.ports()
    assert resolved["grafana_port"] == 3001
    assert resolved["otlp_http_port"] == 4319
    assert resolved["pyroscope_port"] == module.DEFAULT_PORTS["pyroscope_port"]


@pytest.mark.parametrize("bad", [0, 65536, -1, "3000", None, 3.5])
def test_an_invalid_port_falls_back_to_the_default(monkeypatch, tmp_path, bad):
    home = tmp_path / "home"
    module = load(monkeypatch, home, tmp_path / "tmp")
    write_config(home, {"grafana_port": bad})
    assert module.ports()["grafana_port"] == module.DEFAULT_PORTS["grafana_port"]


def test_a_corrupt_configuration_is_not_fatal(monkeypatch, tmp_path):
    home = tmp_path / "home"
    module = load(monkeypatch, home, tmp_path / "tmp")
    (home / ".oddyssey").mkdir(parents=True)
    (home / ".oddyssey" / "config.json").write_text("{not json")
    assert module.ports() == module.DEFAULT_PORTS


def test_the_context_path_is_stable_under_tmpdir(monkeypatch, tmp_path):
    tmpdir = tmp_path / "tmp"
    module = load(monkeypatch, tmp_path / "home", tmpdir)
    first, second = module.config_path(), module.config_path()
    assert first == second
    assert first == tmpdir / "oddyssey" / "gcx-local.yaml"


def test_the_context_is_rewritten_whole_on_a_port_change(monkeypatch, tmp_path):
    module = load(monkeypatch, tmp_path / "home", tmp_path / "tmp")
    module.write_context(3000)
    target = module.write_context(3001)
    body = target.read_text()
    assert "http://localhost:3001" in body
    assert "3000" not in body
    assert body.count("current-context: local") == 1


def test_the_context_names_all_four_datasources(monkeypatch, tmp_path):
    module = load(monkeypatch, tmp_path / "home", tmp_path / "tmp")
    body = module.write_context(3000).read_text()
    for uid in ("prometheus", "loki", "tempo", "pyroscope"):
        assert f"-datasource: {uid}" in body


def test_cli_refuses_when_gcx_is_absent(tmp_path):
    env = dict(os.environ)
    env["PATH"] = str(tmp_path / "empty")
    env["TMPDIR"] = str(tmp_path)
    p = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert p.returncode == 1
    assert "gcx is not on the path" in p.stderr
