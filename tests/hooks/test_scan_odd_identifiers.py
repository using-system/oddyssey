"""Tests for the .odd/ identifier scan hook.

The hook is loaded from its packaged location so the tests exercise the
very file apm deploys. After a tool wrote a file under ``.odd/``, it
scans that file for what AGENTS.md's no-secrets rule keeps out of a
committed report - GUIDs, home-directory paths, and the identifiers the
global configuration's ``stack_config`` carries - and exits 2 with one
stderr line per finding so the agent replaces them before persisting.
Obviously fake placeholders pass, and so does everything the hook does
not understand: it fails open.
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
    Path(__file__).resolve().parents[2]
    / ".apm"
    / "hooks"
    / "scripts"
    / "scan_odd_identifiers.py"
)

REAL_GUID = "3f2a9c1e-7b4d-4e8a-9c21-5d6e7f8a9b0c"
FAKE_CONFIG = {
    "stack": "azure-monitor",
    "local": {"grafana_port": 3000},
    "stack_config": {
        "azure-monitor": {
            "subscription": "Contoso-Prod",
            "workspace": REAL_GUID,
            "resource_group": "contoso-observability-rg",
        },
        "cloudwatch": {
            "profile": "contoso-admin",
            "region": "eu-central-1",
            "log_group": "/contoso-playground/logs",
        },
        "local": {"GF_LOG_LEVEL": "debug"},
    },
}


def _load_module():
    sys.dont_write_bytecode = True  # never leave a __pycache__ in the package
    spec = importlib.util.spec_from_file_location("scan_odd_identifiers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scan_odd_identifiers"] = module  # dataclasses resolve the module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scan():
    return _load_module()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A fake HOME carrying the global configuration the hook reads."""
    config = tmp_path / "home" / ".oddyssey" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(FAKE_CONFIG))
    return tmp_path / "home"


def run_hook(payload, cwd: Path, home: Path) -> subprocess.CompletedProcess:
    """Run the hook as a host would: JSON on stdin, exit code and stderr out."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "PostToolUse"],
        input=stdin,
        cwd=cwd,
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        check=False,
    )


def write_payload(path: Path, cwd: Path) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": "..."},
        "cwd": str(cwd),
    }


# --- which files the payload names ---------------------------------------


def test_reads_the_file_path_the_hosts_send(scan):
    assert scan.written_paths(
        {"tool_input": {"file_path": ".odd/a.md", "content": ""}}
    ) == [".odd/a.md"]
    assert scan.written_paths({"toolArgs": {"path": ".odd/a.md", "content": ""}}) == [
        ".odd/a.md"
    ]
    assert scan.written_paths(
        {"tool_info": {"file_path": ".odd/a.md", "content": ""}}
    ) == [".odd/a.md"]


@pytest.mark.parametrize(
    "command, expected",
    [
        (
            "cat > .odd/observe-run-reports/x.md <<'EOF'\nhi\nEOF",
            [".odd/observe-run-reports/x.md"],
        ),
        ("printf 'x' >> .odd/decisions.md", [".odd/decisions.md"]),
        ("cp a.md /repo/.odd/decisions.md && ls", ["/repo/.odd/decisions.md"]),
        (
            "mv tmp.md .odd/benchmarks/b/manifest.yaml",
            [".odd/benchmarks/b/manifest.yaml"],
        ),
        ("echo x | tee -a .odd/r.md", [".odd/r.md"]),
        ('cat > "$repo"/.odd/r.md <<EOF\nx\nEOF', ["$repo/.odd/r.md"]),
        ("sed -n '1,40p' .odd/observe-run-reports/r.md", []),
        ("grep -rn 'x' .odd/observe-run-reports/r.md | head", []),
        ("cat .odd/decisions.md; ls .odd/", []),
        ("cp .odd/r.md /tmp/copy.md", []),
        ("git add .odd/r.md && git commit -m x", []),
    ],
)
def test_reads_only_the_odd_paths_a_shell_command_writes(scan, command, expected):
    assert scan.written_paths({"tool_input": {"command": command}}) == expected


def test_a_file_tool_payload_counts_as_a_write_only_with_content(scan):
    assert scan.written_paths({"tool_input": {"file_path": ".odd/a.md"}}) == []
    assert (
        scan.written_paths(
            {"tool_name": "Read", "tool_input": {"file_path": ".odd/a.md"}}
        )
        == []
    )
    assert scan.written_paths(
        {"tool_input": {"file_path": ".odd/a.md", "content": "x"}}
    ) == [".odd/a.md"]
    assert scan.written_paths(
        {"tool_input": {"file_path": ".odd/a.md", "old_string": "a", "new_string": "b"}}
    ) == [".odd/a.md"]
    assert scan.written_paths(
        {"tool_name": "write_file", "tool_input": {"file_path": ".odd/a.md"}}
    ) == [".odd/a.md"]
    assert scan.written_paths(
        {"tool_name": "edit", "toolArgs": {"path": ".odd/a.md"}}
    ) == [".odd/a.md"]


def test_ignores_files_outside_odd(scan, tmp_path):
    assert scan.in_odd(tmp_path / "README.md") is False
    assert scan.in_odd(tmp_path / ".odd" / "decisions.md") is True
    assert scan.in_odd(tmp_path / ".odd" / "observe-run-reports" / "r.md") is True
    assert scan.in_odd(tmp_path / "src" / ".oddities" / "x") is False


# --- what the scan finds ---------------------------------------------------


def test_finds_a_real_guid_and_passes_a_patterned_one(scan):
    text = f"workspace {REAL_GUID}\nzeroed 00000000-0000-0000-0000-000000000000\n"
    text += "patterned 11111111-1111-1111-1111-111111111111\n"
    text += "sequential 12345678-1234-1234-1234-123456789abc\n"
    text += "trace 3f2a9c1e7b4d4e8a9c215d6e7f8a9b0c and anchor 5ea231f0c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8\n"
    findings = scan.scan_text(text, forbidden=[])
    assert [(f.line, f.kind) for f in findings] == [(1, "GUID")]


def test_finds_home_directory_paths(scan):
    text = "a /Users/someone/Repos/x\nb /home/someone/x\nc C:\\Users\\someone\\x\nd <scratchpad>/x\n"
    text += "e /home/runner/work/x\nf /Users/<user>/x\ng /root/x\n"
    findings = scan.scan_text(text, forbidden=[])
    assert [(f.line, f.kind) for f in findings] == [
        (1, "home path"),
        (2, "home path"),
        (3, "home path"),
    ]


def test_finds_the_stack_config_identifiers(scan):
    forbidden = scan.forbidden_values(FAKE_CONFIG)
    assert "Contoso-Prod" in forbidden
    assert "contoso-observability-rg" in forbidden
    assert "contoso-admin" in forbidden
    assert "/contoso-playground/logs" in forbidden
    assert "eu-central-1" not in forbidden  # a region identifies nothing
    assert (
        "debug" not in forbidden
    )  # the local stack carries container env, not identifiers
    text = "subscription Contoso-Prod\nlog group /contoso-playground/logs\nregion eu-central-1\n"
    findings = scan.scan_text(text, forbidden=forbidden)
    assert [(f.line, f.kind) for f in findings] == [
        (1, "stack_config value"),
        (2, "stack_config value"),
    ]


def test_matching_is_whole_word_and_case_sensitive(scan):
    forbidden = ["zefactory"]
    assert scan.scan_text("profile zefactory-export\n", forbidden) == []
    assert scan.scan_text("profile ZeFactory\n", forbidden) == []
    assert [f.line for f in scan.scan_text("profile zefactory\n", forbidden)] == [1]


def test_short_or_placeholder_values_are_never_forbidden(scan):
    config = {
        "stack_config": {
            "x": {"tenant": "abc", "name": "Contoso", "login": "example-user"}
        }
    }
    assert scan.forbidden_values(config) == []


# --- the decision, end to end -------------------------------------------


def test_flags_a_report_carrying_a_real_guid(tmp_path, home):
    report = tmp_path / ".odd" / "observe-run-reports" / "r.md"
    report.parent.mkdir(parents=True)
    report.write_text(f"---\nservices: [x]\n---\nworkspace {REAL_GUID}\n")
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 2
    assert ".odd/observe-run-reports/r.md:4" in result.stderr
    assert "GUID" in result.stderr
    assert REAL_GUID not in result.stderr  # never echo the value back
    assert "placeholder" in result.stderr
    assert "service.instance.id" in result.stderr  # the agent tells the two apart


def test_flags_the_live_stack_config_values(tmp_path, home):
    report = tmp_path / ".odd" / "decisions.md"
    report.parent.mkdir(parents=True)
    report.write_text("| F1 | wontfix | seen on Contoso-Prod |\n")
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 2
    assert "stack_config value" in result.stderr
    assert "Contoso-Prod" not in result.stderr


def test_a_clean_report_passes(tmp_path, home):
    report = tmp_path / ".odd" / "observe-run-reports" / "r.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "revision: 2299d4c\nwindow: 2026-08-22T10:04:12Z/2026-08-22T10:05:03Z\n"
        "tenant <guid>, workspace 00000000-0000-0000-0000-000000000000, region eu-central-1\n"
        "path <scratchpad>/drive.py, user example-user, http://localhost:3000\n"
    )
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 0
    assert result.stderr == ""


def test_the_message_never_shows_a_home_directory(tmp_path):
    home = tmp_path / "home"
    report = home / "Repos" / "x" / ".odd" / "r.md"
    report.parent.mkdir(parents=True)
    report.write_text("see /home/someone/repo\n")
    (tmp_path / "elsewhere").mkdir()
    result = run_hook(
        write_payload(report, tmp_path / "elsewhere"), tmp_path / "elsewhere", home
    )
    assert result.returncode == 2
    assert str(home) not in result.stderr
    assert "~/Repos/x/.odd/r.md:1" in result.stderr


def test_a_file_outside_odd_is_never_scanned(tmp_path, home):
    other = tmp_path / "notes.md"
    other.write_text(f"{REAL_GUID} /Users/someone/x\n")
    result = run_hook(write_payload(other, tmp_path), tmp_path, home)
    assert result.returncode == 0


def test_a_shell_write_into_odd_is_scanned(tmp_path, home):
    report = tmp_path / ".odd" / "observe-run-reports" / "r.md"
    report.parent.mkdir(parents=True)
    report.write_text("see /home/someone/repo\n")
    payload = {
        "tool_input": {"command": f"cat > {report} <<'EOF'\nx\nEOF"},
        "cwd": str(tmp_path),
    }
    result = run_hook(payload, tmp_path, home)
    assert result.returncode == 2
    assert "home path" in result.stderr
    read = {"tool_input": {"command": f"sed -n '1,40p' {report}"}, "cwd": str(tmp_path)}
    assert run_hook(read, tmp_path, home).returncode == 0


def test_findings_are_capped_and_counted(tmp_path, home):
    report = tmp_path / ".odd" / "r.md"
    report.parent.mkdir(parents=True)
    report.write_text("".join(f"line /Users/someone/{i}\n" for i in range(25)))
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 2
    assert result.stderr.count("\n") <= 12
    assert "25 finding" in result.stderr


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        json.dumps({"tool_input": {"command": "git status"}}),
        json.dumps({"tool_input": {"file_path": "/nonexistent/.odd/x.md"}}),
        json.dumps(
            {"tool_name": "Read", "tool_input": {"file_path": ".odd/decisions.md"}}
        ),
    ],
)
def test_fails_open_on_anything_it_does_not_understand(tmp_path, home, payload):
    result = run_hook(payload, tmp_path, home)
    assert result.returncode == 0


def test_a_missing_or_broken_configuration_still_scans_the_rest(tmp_path):
    home = tmp_path / "home"
    (home / ".oddyssey").mkdir(parents=True)
    (home / ".oddyssey" / "config.json").write_text("{not json")
    report = tmp_path / ".odd" / "r.md"
    report.parent.mkdir(parents=True)
    report.write_text(f"id {REAL_GUID}\n")
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 2
    assert "GUID" in result.stderr
    result = run_hook(write_payload(report, tmp_path), tmp_path, tmp_path / "nohome")
    assert result.returncode == 2
