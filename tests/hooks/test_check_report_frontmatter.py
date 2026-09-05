"""Tests for the report frontmatter check hook.

The hook is loaded from its packaged location so the tests exercise the
very file apm deploys. After a tool wrote a file under
``.odd/observe-run-reports/`` or ``.odd/otel-instrumentation-reports/``,
it checks the file's name and frontmatter against the memory contract -
the filename shape, the required fields of the kind, their values, the
window, the date and slug the filename carries, the stored report a
replay's ``verifies`` names - and exits 2 with one stderr line per
problem so the agent fixes the report before persisting.

The hook carries its own copy of ``get-status``'s ``check_report``: the
two deploy separately and a hook script imports nothing outside itself.
One shared fixture set runs through both checkers, and the agreement
test asserts they return the same problems, so a drift between the two
copies fails here instead of surfacing as a report the hook accepted
and the status flags. The two intended differences are stated there:
at write time a missing ``depth`` is a problem, not a legacy note, and
a file the hook cannot read is passed over (the status lists it as
``unreadable``).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".apm" / "hooks" / "scripts" / "check_report_frontmatter.py"
STATUS_SCRIPT = ROOT / ".apm" / "skills" / "get-status" / "scripts" / "odd_status.py"

OBS = ".odd/observe-run-reports"
INS = ".odd/otel-instrumentation-reports"


def _load(name: str, script: Path):
    sys.dont_write_bytecode = True  # never leave a __pycache__ in the package
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve the module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hook():
    return _load("check_report_frontmatter", SCRIPT)


@pytest.fixture(scope="module")
def odd_status():
    return _load("odd_status", STATUS_SCRIPT)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A fake HOME so the message's path display never reaches the real one."""
    (tmp_path / "home").mkdir()
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


# --- the shared fixture set ----------------------------------------------------

WINDOW = "2026-08-10T10:00:00Z/2026-08-10T10:05:00Z"


def observation(**overrides) -> str:
    """A well-formed observation report; ``field=None`` drops the field."""
    fields = {
        "services": "[checkout]",
        "stack": "local",
        "environment": "local",
        "mode": "drive",
        "depth": "full",
        "window": WINDOW,
        "run_name": "checkout-sweep",
        "date": "2026-08-10",
    }
    fields.update(overrides)
    lines = ["---"]
    lines.extend(
        f"{key}: {value}" for key, value in fields.items() if value is not None
    )
    lines.extend(["---", "", "# Observation report", ""])
    return "\n".join(lines) + "\n"


def instrumentation(**overrides) -> str:
    """A well-formed instrumentation report; ``field=None`` drops the field."""
    fields = {
        "project": "app",
        "stack": "local",
        "run_name": "app",
        "date": "2026-08-09",
    }
    fields.update(overrides)
    lines = ["---"]
    lines.extend(
        f"{key}: {value}" for key, value in fields.items() if value is not None
    )
    lines.extend(["---", "", "# Instrumentation plan", ""])
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Case:
    rel: str
    text: str
    problems: tuple[str, ...]  # exact, in order; empty means the report passes

    @property
    def kind(self) -> str:
        return "observation" if self.rel.startswith(OBS) else "instrumentation"


MODES = "['drive', 'observe', 'post-hoc', 'verify', 're-measure']"
DEPTHS = "['quick', 'full']"

CASES = (
    # well-formed
    Case(f"{OBS}/2026-08-10-1000-checkout-sweep.md", observation(), ()),
    Case(f"{INS}/2026-08-09-1000-app.md", instrumentation(), ()),
    Case(
        f"{OBS}/2026-08-12-1000-verify-checkout-sweep.md",
        observation(
            mode="verify",
            date="2026-08-12",
            verifies="2026-08-10-1000-checkout-sweep.md",
        ),
        (),
    ),
    Case(
        f"{OBS}/2026-08-12-1100-verify-app.md",
        observation(
            mode="verify",
            run_name="app",
            date="2026-08-12",
            verifies=f"{INS}/2026-08-09-1000-app.md",
        ),
        (),
    ),
    Case(
        f"{OBS}/2026-08-13-1000-remeasure-checkout-sweep.md",
        observation(
            mode="re-measure",
            date="2026-08-13",
            verifies="2026-08-10-1000-checkout-sweep.md",
        ),
        (),
    ),
    Case(
        # a quoted scalar and flow mappings: a drift in the copied parser
        # would break the slug match or read the fields as null
        f"{OBS}/2026-08-10-1020-flow-fields.md",
        observation(
            run_name="'flow-fields'",
            workload='"repo under analysis"',
            instance="{checkout: af6070c1, payment: [a1b2c3, d4e5f6]}",
        ),
        (),
    ),
    # each required field of an observation report missing in turn
    Case(
        f"{OBS}/2026-08-10-1001-no-services.md",
        observation(services=None, run_name="no-services"),
        ("services absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1002-no-stack.md",
        observation(stack=None, run_name="no-stack"),
        ("stack absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1003-no-environment.md",
        observation(environment=None, run_name="no-environment"),
        ("environment absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1004-no-mode.md",
        observation(mode=None, run_name="no-mode"),
        ("mode absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1005-no-window.md",
        observation(window=None, run_name="no-window"),
        ("window absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1006-no-run-name.md",
        observation(run_name=None),
        ("run_name absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1007-no-date.md",
        observation(date=None, run_name="no-date"),
        ("date absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1008-empty-services.md",
        observation(services="[]", run_name="empty-services"),
        ("services absent", "services empty"),
    ),
    # at write time depth is required, its value bounded
    Case(
        f"{OBS}/2026-08-10-1009-no-depth.md",
        observation(depth=None, run_name="no-depth"),
        ("depth absent",),
    ),
    Case(
        f"{OBS}/2026-08-10-1010-bad-depth.md",
        observation(depth="deep", run_name="bad-depth"),
        (f"depth 'deep' is not one of {DEPTHS}",),
    ),
    Case(
        f"{OBS}/2026-08-10-1011-bad-mode.md",
        observation(mode="drove", run_name="bad-mode"),
        (f"mode 'drove' is not one of {MODES}",),
    ),
    # the window
    Case(
        f"{OBS}/2026-08-10-1012-window-reversed.md",
        observation(
            window="2026-08-10T10:05:00Z/2026-08-10T10:00:00Z",
            run_name="window-reversed",
        ),
        ("window end precedes its start",),
    ),
    Case(
        f"{OBS}/2026-08-10-1013-window-prose.md",
        observation(window="10:00 to 10:05", run_name="window-prose"),
        ("window is not <start>/<end> in UTC (YYYY-MM-DDTHH:MM:SSZ)",),
    ),
    Case(
        f"{OBS}/2026-08-10-1014-window-offset.md",
        observation(
            window="2026-08-10T10:00:00+02:00/2026-08-10T10:05:00+02:00",
            run_name="window-offset",
        ),
        ("window is not <start>/<end> in UTC (YYYY-MM-DDTHH:MM:SSZ)",),
    ),
    # the date and the slug against the filename
    Case(
        f"{OBS}/2026-08-11-1000-date-off.md",
        observation(run_name="date-off"),
        ("date 2026-08-10 differs from the filename's 2026-08-11",),
    ),
    Case(
        f"{OBS}/2026-08-10-1015-date-prose.md",
        observation(date="10/08/2026", run_name="date-prose"),
        ("date '10/08/2026' is not YYYY-MM-DD",),
    ),
    Case(
        f"{OBS}/2026-08-10-1016-other-slug.md",
        observation(),
        (
            "filename slug 'other-slug' is not 'checkout-sweep' (run_name 'checkout-sweep')",
        ),
    ),
    Case(
        f"{OBS}/2026-08-12-1200-checkout-sweep.md",
        observation(
            mode="verify",
            date="2026-08-12",
            verifies="2026-08-10-1000-checkout-sweep.md",
        ),
        (
            (
                "filename slug 'checkout-sweep' is not 'verify-checkout-sweep'"
                " (run_name 'checkout-sweep' with the verify- prefix)"
            ),
        ),
    ),
    Case(
        f"{OBS}/notes.md",
        observation(run_name="notes"),
        ("filename is not YYYY-MM-DD-HHmm-<run_name>.md",),
    ),
    # verifies: required on a replay, and it must name a stored report
    Case(
        f"{OBS}/2026-08-12-1300-verify-checkout-sweep.md",
        observation(mode="verify", date="2026-08-12"),
        ("verifies absent on a verify report",),
    ),
    Case(
        f"{OBS}/2026-08-13-1100-remeasure-checkout-sweep.md",
        observation(mode="re-measure", date="2026-08-13"),
        ("verifies absent on a re-measure report",),
    ),
    Case(
        f"{OBS}/2026-08-12-1400-verify-ghost.md",
        observation(
            mode="verify",
            run_name="ghost",
            date="2026-08-12",
            verifies="2026-08-01-1000-ghost.md",
        ),
        ("verifies names no stored report: 2026-08-01-1000-ghost.md",),
    ),
    Case(
        f"{OBS}/2026-08-12-1500-verify-plan.md",
        observation(
            mode="verify",
            run_name="plan",
            date="2026-08-12",
            verifies=f"{INS}/2026-08-01-1000-plan.md",
        ),
        (f"verifies names no stored report: {INS}/2026-08-01-1000-plan.md",),
    ),
    Case(
        # a bare filename resolves against observation reports only
        f"{OBS}/2026-08-12-1600-verify-app.md",
        observation(
            mode="verify",
            run_name="app",
            date="2026-08-12",
            verifies="2026-08-09-1000-app.md",
        ),
        ("verifies names no stored report: 2026-08-09-1000-app.md",),
    ),
    # each required field of an instrumentation report missing in turn
    Case(
        f"{INS}/2026-08-09-1001-no-project.md",
        instrumentation(project=None, run_name="no-project"),
        ("project absent",),
    ),
    Case(
        f"{INS}/2026-08-09-1002-no-stack.md",
        instrumentation(stack=None, run_name="no-stack"),
        ("stack absent",),
    ),
    Case(
        f"{INS}/2026-08-09-1003-no-run-name.md",
        instrumentation(run_name=None),
        ("run_name absent",),
    ),
    Case(
        f"{INS}/2026-08-09-1004-no-date.md",
        instrumentation(date=None, run_name="no-date"),
        ("date absent",),
    ),
    Case(
        f"{INS}/2026-08-09-1005-plan-off.md",
        instrumentation(run_name="plan", date="2026-08-08"),
        (
            "date 2026-08-08 differs from the filename's 2026-08-09",
            "filename slug 'plan-off' is not 'plan' (run_name 'plan')",
        ),
    ),
    # a frontmatter the parser cannot read is a problem, not a pass
    Case(
        f"{OBS}/2026-08-10-1017-bare.md",
        "no frontmatter at all\n",
        ("frontmatter: no frontmatter block", "frontmatter absent"),
    ),
    Case(
        f"{OBS}/2026-08-10-1018-unterminated.md",
        "---\nservices: [checkout]\n",
        ("frontmatter: unterminated frontmatter block", "frontmatter absent"),
    ),
    Case(
        f"{OBS}/2026-08-10-1019-block-style.md",
        observation(run_name="block-style").replace(
            "services: [checkout]", "services:\n  - checkout"
        ),
        (
            (
                "frontmatter: services: block-style value (the contract is flow style),"
                " read as null"
            ),
            "services absent",
        ),
    ),
)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """The whole fixture set written under one repository root."""
    for case in CASES:
        path = tmp_path / case.rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(case.text)
    return tmp_path


# --- which files the payload names ---------------------------------------


def test_reads_the_file_path_the_hosts_send(hook):
    assert hook.written_paths(
        {"tool_input": {"file_path": f"{OBS}/a.md", "content": ""}}
    ) == [f"{OBS}/a.md"]
    assert hook.written_paths({"toolArgs": {"path": f"{OBS}/a.md", "content": ""}}) == [
        f"{OBS}/a.md"
    ]
    assert hook.written_paths(
        {"tool_info": {"file_path": f"{OBS}/a.md", "content": ""}}
    ) == [f"{OBS}/a.md"]


@pytest.mark.parametrize(
    "command, expected",
    [
        (f"cat > {OBS}/x.md <<'EOF'\nhi\nEOF", [f"{OBS}/x.md"]),
        (f"printf 'x' >> {INS}/x.md", [f"{INS}/x.md"]),
        (f"cp a.md /repo/{OBS}/x.md && ls", [f"/repo/{OBS}/x.md"]),
        (f"mv tmp.md {OBS}/x.md", [f"{OBS}/x.md"]),
        (f"echo x | tee -a {OBS}/x.md", [f"{OBS}/x.md"]),
        (f"sed -n '1,40p' {OBS}/r.md", []),
        (f"cat {OBS}/r.md; ls {OBS}/", []),
        (f"git add {OBS}/r.md && git commit -m x", []),
    ],
)
def test_reads_only_the_odd_paths_a_shell_command_writes(hook, command, expected):
    assert hook.written_paths({"tool_input": {"command": command}}) == expected


def test_a_file_tool_payload_counts_as_a_write_only_with_content(hook):
    assert hook.written_paths({"tool_input": {"file_path": f"{OBS}/a.md"}}) == []
    assert (
        hook.written_paths(
            {"tool_name": "Read", "tool_input": {"file_path": f"{OBS}/a.md"}}
        )
        == []
    )
    assert hook.written_paths(
        {"tool_input": {"file_path": f"{OBS}/a.md", "content": "x"}}
    ) == [f"{OBS}/a.md"]
    assert hook.written_paths(
        {"tool_name": "write_file", "tool_input": {"file_path": f"{OBS}/a.md"}}
    ) == [f"{OBS}/a.md"]


def test_only_a_report_file_in_the_two_stores_is_in_scope(hook, tmp_path):
    assert hook.report_kind(tmp_path / OBS / "r.md") == "observation"
    assert hook.report_kind(tmp_path / INS / "r.md") == "instrumentation"
    assert hook.report_kind(tmp_path / ".odd" / "decisions.md") is None
    assert hook.report_kind(tmp_path / ".odd" / "benchmarks" / "b" / "r.md") is None
    assert hook.report_kind(tmp_path / OBS / "nested" / "r.md") is None
    assert hook.report_kind(tmp_path / OBS / "notes.txt") is None
    assert hook.report_kind(tmp_path / OBS / "x.md~") is None
    assert hook.report_kind(tmp_path / "observe-run-reports" / "r.md") is None
    assert hook.report_kind(tmp_path / "README.md") is None


# --- the fixture set, end to end -----------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=[Path(c.rel).name for c in CASES])
def test_each_fixture_gets_its_verdict_and_one_line_per_problem(store, home, case):
    result = run_hook(write_payload(store / case.rel, store), store, home)
    if not case.problems:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        return
    assert result.returncode == 2
    lines = result.stderr.splitlines()
    assert lines[0].startswith("odd-guards:")
    assert "reports.md" in lines[0]
    assert lines[1:] == [f"  {case.rel}: {problem}" for problem in case.problems]


def test_a_stray_frontmatter_line_is_reported_without_its_text(tmp_path, home):
    report = tmp_path / OBS / "2026-08-10-1000-checkout-sweep.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        observation().replace("\nstack: local", "\nContoso-Prod token\nstack: local")
    )
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 2
    assert result.stderr.count("\n") == 2
    assert "frontmatter: line 3: no colon-separated key" in result.stderr
    assert "Contoso" not in result.stderr
    assert "kept out" not in result.stderr


def test_a_shell_write_into_a_report_store_is_checked(tmp_path, home):
    report = tmp_path / OBS / "2026-08-10-1000-checkout-sweep.md"
    report.parent.mkdir(parents=True)
    report.write_text(observation(window=None))
    payload = {
        "tool_input": {
            "command": f"cat > {OBS}/2026-08-10-1000-checkout-sweep.md <<'EOF'\nx\nEOF"
        },
        "cwd": str(tmp_path),
    }
    result = run_hook(payload, tmp_path, home)
    assert result.returncode == 2
    assert f"  {OBS}/2026-08-10-1000-checkout-sweep.md: window absent" in result.stderr
    read = {"tool_input": {"command": f"sed -n '1,40p' {report}"}, "cwd": str(tmp_path)}
    assert run_hook(read, tmp_path, home).returncode == 0


def test_a_file_outside_the_two_stores_is_never_checked(tmp_path, home):
    for rel in ("notes.md", ".odd/decisions.md", ".odd/benchmarks/b/README.md"):
        other = tmp_path / rel
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("no frontmatter at all\n")
        result = run_hook(write_payload(other, tmp_path), tmp_path, home)
        assert result.returncode == 0, rel
        assert result.stderr == ""


def test_the_message_never_shows_a_home_directory(tmp_path):
    home = tmp_path / "home"
    report = home / "Repos" / "x" / OBS / "2026-08-10-1000-checkout-sweep.md"
    report.parent.mkdir(parents=True)
    report.write_text(observation(window=None))
    (tmp_path / "elsewhere").mkdir()
    result = run_hook(
        write_payload(report, tmp_path / "elsewhere"), tmp_path / "elsewhere", home
    )
    assert result.returncode == 2
    assert str(home) not in result.stderr
    assert f"~/Repos/x/{OBS}/2026-08-10-1000-checkout-sweep.md: window absent" in (
        result.stderr
    )


def test_problems_are_capped_and_counted(tmp_path, home):
    report = tmp_path / OBS / "2026-08-10-1000-checkout-sweep.md"
    report.parent.mkdir(parents=True)
    stray = "".join(f"stray line {i}\n" for i in range(15))
    report.write_text(observation().replace("\nstack: local", f"\n{stray}stack: local"))
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 2
    assert result.stderr.count("\n") <= 12
    assert "15 problems" in result.stderr


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        json.dumps({"tool_input": {"command": "git status"}}),
        json.dumps({"tool_input": {"file_path": f"/nonexistent/{OBS}/x.md"}}),
        json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": f"/nonexistent/{OBS}/x.md"},
            }
        ),
        json.dumps({"tool_name": "Read", "tool_input": {"file_path": f"{OBS}/x.md"}}),
    ],
)
def test_fails_open_on_anything_it_does_not_understand(tmp_path, home, payload):
    result = run_hook(payload, tmp_path, home)
    assert result.returncode == 0
    assert result.stderr == ""


def test_fails_open_on_a_report_it_cannot_decode(hook, odd_status, tmp_path, home):
    # The status lists such a file as a violation; the hook, unable to
    # read a report, judges nothing - not even its filename.
    report = tmp_path / OBS / "notes.md"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"\xff\xfe\x00 not utf-8")
    result = run_hook(write_payload(report, tmp_path), tmp_path, home)
    assert result.returncode == 0
    assert result.stderr == ""
    assert hook.check_file(report) is None
    status = odd_status.parse_report(tmp_path, f"{OBS}/notes.md", "observation")
    problems = odd_status.check_report(status, set(), tmp_path)
    assert problems[0].startswith("filename is not")
    assert problems[1].startswith("unreadable:")


# --- the hook's checker and get-status's check_report agree ---------------------

LEGACY_DEPTH = "depth absent (predates the field: reads as full)"


def test_the_hook_and_the_status_return_the_same_problems(hook, odd_status, store):
    """One fixture set, two checkers, equal verdicts.

    Two intended differences. get-status reads a report without
    ``depth`` as a legacy file that predates the field, while a report
    being written now has no such excuse - the hook says ``depth absent``.
    And a file get-status cannot read is a violation (``unreadable:
    <error>``, the filename-shape problem kept), while the hook fails open
    on it and returns None - covered by its own test below, never by
    this fixture set, which holds readable files only. Everything else
    must be identical, message for message: a drift between the two
    copies fails here.
    """
    stored = {
        Path(rel).name
        for rel, kind in odd_status.list_reports(store)
        if kind == "observation"
    }
    for case in CASES:
        report = odd_status.parse_report(store, case.rel, case.kind)
        status_problems = odd_status.check_report(report, stored, store)
        expected = ["depth absent" if p == LEGACY_DEPTH else p for p in status_problems]
        assert hook.check_file(store / case.rel) == expected, case.rel
        assert list(case.problems) == expected, case.rel


def test_the_depth_difference_is_the_one_stated(hook, odd_status, store):
    rel = f"{OBS}/2026-08-10-1009-no-depth.md"
    report = odd_status.parse_report(store, rel, "observation")
    assert odd_status.check_report(report, set(), store) == [LEGACY_DEPTH]
    assert hook.check_file(store / rel) == ["depth absent"]
    assert odd_status.LEGACY_PREFIX in LEGACY_DEPTH  # what the status lists as legacy
