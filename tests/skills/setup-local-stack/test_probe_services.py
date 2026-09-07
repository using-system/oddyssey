"""Tests for the setup-local-stack skill's service probe.

The script is loaded from its packaged location so the tests exercise the
very file the skill ships. `gcx` is a fake binary on PATH: the probe's
whole job is composing gcx calls and reducing their output, so a stub
that answers per subcommand is what makes that testable without a stack.
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
    / ".apm/skills/setup-local-stack/scripts/probe_services.py"
)


def load():
    spec = importlib.util.spec_from_file_location("probe_services", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def probe():
    return load()


def fake_gcx(tmp_path: Path, script_body: str) -> Path:
    """Put a `gcx` on PATH that answers from a python snippet."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gcx"
    stub.write_text(
        "#!/usr/bin/env python3\nimport sys\n" + script_body,
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return bin_dir


def prepend(bin_dir: Path) -> str:
    """The stub is a python script: keep the real PATH behind it."""
    return str(bin_dir) + os.pathsep + os.environ["PATH"]


HINT = '{"class":"hint","summary":"use --json list"}'


def test_gcx_strips_the_hint_lines(probe, tmp_path, monkeypatch):
    body = f"print({HINT!r})\nprint('{{\"ok\": true}}')\n"
    monkeypatch.setenv("PATH", prepend(fake_gcx(tmp_path, body)))
    code, data, err = probe.gcx(["anything"])
    assert code == 0
    assert data == {"ok": True}
    assert err == ""


def test_gcx_reports_a_failure_rather_than_parsing_it(probe, tmp_path, monkeypatch):
    body = "print('not json', file=sys.stderr)\nsys.exit(3)\n"
    monkeypatch.setenv("PATH", prepend(fake_gcx(tmp_path, body)))
    code, data, err = probe.gcx(["anything"])
    assert code == 3
    assert data is None
    assert "not json" in err


def test_absent_traces_are_a_result_not_an_error(probe, tmp_path, monkeypatch):
    body = 'print(\'{"n": 0, "roots": []}\')\n'
    monkeypatch.setenv("PATH", prepend(fake_gcx(tmp_path, body)))
    result = probe.probe_traces("svc", "30m")
    assert result == {"present": False, "count": 0, "capped": False, "operations": []}
    assert "error" not in result


def test_a_full_page_of_traces_is_flagged_capped(probe, tmp_path, monkeypatch):
    n = probe.TRACE_LIMIT
    body = f'print(\'{{"n": {n}, "roots": ["GET /"]}}\')\n'
    monkeypatch.setenv("PATH", prepend(fake_gcx(tmp_path, body)))
    result = probe.probe_traces("svc", "30m")
    assert result["present"] and result["capped"] and result["count"] == n


def test_identity_reads_the_resource_attributes_and_dedupes_instances(
    probe, tmp_path, monkeypatch
):
    rows = [
        {
            "service_instance_id": "a",
            "deployment_environment_name": "local",
            "service_version": "0.1.0",
        },
        {
            "service_instance_id": "a",
            "deployment_environment_name": "local",
            "service_version": "0.1.0",
        },
        {
            "service_instance_id": "b",
            "deployment_environment_name": "local",
            "service_version": "0.1.0",
        },
    ]
    body = f"print({json.dumps(json.dumps(rows))})\n"
    monkeypatch.setenv("PATH", prepend(fake_gcx(tmp_path, body)))
    result = probe.probe_identity("svc")
    assert result["present"]
    assert result["instances"] == ["a", "b"]
    assert result["attributes"]["deployment_environment_name"] == "local"


def test_identity_absent_when_no_target_info_series(probe, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", prepend(fake_gcx(tmp_path, "print('[]')\n")))
    assert probe.probe_identity("svc")["present"] is False


@pytest.mark.parametrize(
    "names, expected",
    [
        (["a_bucket", "a_count", "a_sum"], ["a_*"]),
        (["orders_total"], ["orders_total"]),
        (["hits_count"], ["hits_count"]),
        (["a_bucket", "a_count", "a_sum", "orders_total"], ["a_*", "orders_total"]),
    ],
)
def test_a_histogram_collapses_into_one_family(probe, names, expected):
    assert probe.collapse_histograms(names) == expected


def test_baseline_reads_only_cumulative_series(probe, tmp_path, monkeypatch):
    body = (
        "expr = sys.argv[sys.argv.index('query') + 1]\n"
        'print(\'{"data": {"result": [{"value": [0, "7"]}]}}\')\n'
        "open('%s', 'a').write(expr + chr(10))\n" % (tmp_path / "seen.txt")
    )
    monkeypatch.setenv("PATH", prepend(fake_gcx(tmp_path, body)))
    values = probe.probe_baseline(
        "svc", ["orders_total", "lat_bucket", "lat_count", "gauge_now"]
    )
    assert values == {"orders_total": 7.0, "lat_count": 7.0}
    seen = (tmp_path / "seen.txt").read_text()
    assert "lat_bucket" not in seen and "gauge_now" not in seen


def test_render_names_every_absent_signal(probe):
    report = {
        "probed_at": "2026-09-07T00:00:00Z",
        "window": "30m",
        "services": [
            {
                "service": "svc",
                "traces": {"present": False},
                "metrics": {"present": False},
                "logs": {"present": False},
                "identity": {"present": False},
            }
        ],
        "profiles": {"names": []},
        "profile_types": {"types": []},
    }
    out = probe.render(report)
    assert "traces ABSENT" in out
    assert "metrics ABSENT" in out
    assert "logs ABSENT" in out
    assert "profiles ABSENT" in out
    assert "identity   ABSENT" in out


def test_cli_refuses_without_a_gcx_context(tmp_path, monkeypatch):
    env = dict(os.environ)
    env.pop("GCX_CONFIG", None)
    env["PATH"] = str(fake_gcx(tmp_path, "pass\n")) + os.pathsep + env["PATH"]
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "svc"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert p.returncode == 1
    assert "GCX_CONFIG" in p.stderr


def test_cli_renders_json_end_to_end(tmp_path, monkeypatch):
    body = (
        "a = sys.argv\n"
        'if \'traces\' in a: print(\'{"n": 2, "roots": ["GET /"]}\')\n'
        'elif \'list-profile-types\' in a: print(\'{"profileTypes": [{"name": "cpu"}]}\')\n'
        "elif 'profiles' in a: print('{\"names\": [\"svc\"]}')\n"
        "elif 'logs' in a: print('[{\"service_name\": \"svc\"}]')\n"
        "elif 'target_info' in ' '.join(a): print('[{\"service_instance_id\": \"i1\"}]')\n"
        "elif 'series' in a: print('[\"orders_total\"]')\n"
        'else: print(\'{"data": {"result": [{"value": [0, "5"]}]}}\')\n'
    )
    config = tmp_path / "gcx.yaml"
    config.write_text("current-context: local\n")
    env = dict(os.environ)
    env["GCX_CONFIG"] = str(config)
    env["PATH"] = str(fake_gcx(tmp_path, body)) + os.pathsep + env["PATH"]
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "svc", "--json"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    report = json.loads(p.stdout)
    assert report["services"][0]["traces"]["count"] == 2
    assert report["services"][0]["baseline"] == {"orders_total": 5.0}
    assert report["profile_types"]["types"] == ["cpu"]
