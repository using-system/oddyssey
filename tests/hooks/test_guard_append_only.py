"""Tests for the .odd/ append-only guard hook.

The hook is loaded from its packaged location so the tests exercise the
very file apm deploys. Before a tool runs, it reads the host's JSON
payload on stdin and refuses - exit 2, one line on stderr naming the
file and the rule - a file tool about to modify a stored report that
HEAD already holds under ``.odd/observe-run-reports/`` or
``.odd/otel-instrumentation-reports/``, any file tool aimed at the two
ruling ledgers (``.odd/decisions.md``, ``.odd/entry-classifications.md``
- their script is the only writer), and a shell command that names one
of those files together with a write shape. A report not yet committed
stays the agent's to write, rewrite or remove, a read passes, the
living-source stores pass, and so does every payload the hook does not
understand: it fails open.
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
    / "guard_append_only.py"
)

SECRET_TEXT = "hunter2-this-line-never-reaches-stderr"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "example-user",
    "GIT_AUTHOR_EMAIL": "example-user@example.com",
    "GIT_COMMITTER_NAME": "example-user",
    "GIT_COMMITTER_EMAIL": "example-user@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _load_module():
    sys.dont_write_bytecode = True  # never leave a __pycache__ in the package
    spec = importlib.util.spec_from_file_location("guard_append_only", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load_module()


class Memory:
    """A throwaway repository whose .odd/ tree holds one committed report of
    each kind and both ledgers; ``git=False`` builds the same tree with no
    repository around it."""

    def __init__(self, root: Path, git: bool = True):
        self.root = root
        self.observation = (
            root / ".odd" / "observe-run-reports" / "2026-08-22-orders-api.md"
        )
        self.instrumentation = (
            root / ".odd" / "otel-instrumentation-reports" / "2026-08-20-orders-api.md"
        )
        self.decisions = root / ".odd" / "decisions.md"
        self.classifications = root / ".odd" / "entry-classifications.md"
        self.benchmark = root / ".odd" / "benchmarks" / "orders" / "manifest.yaml"
        self.stack = root / ".odd" / "observability-stacks" / "contoso.md"
        for path in (
            self.observation,
            self.instrumentation,
            self.benchmark,
            self.stack,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"stored\n{SECRET_TEXT}\n")
        self.decisions.write_text("| Date | Finding | Verdict | Rationale |\n")
        self.classifications.write_text("| Date | Entry | Class | Rationale |\n")
        if git:
            self.git("init", "-q", "-b", "main")
            self.commit()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=self.root,
            env={**os.environ, **GIT_ENV},
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "docs(odd): stored records")

    def new_report(self, name: str = "2026-08-23-orders-api.md") -> Path:
        """A report just written by a run and not committed yet."""
        path = self.observation.parent / name
        path.write_text(f"fresh\n{SECRET_TEXT}\n")
        return path

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(tmp_path)


def run_hook(payload, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the hook as a host would: JSON on stdin, exit code and stderr out."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "PreToolUse"],
        input=stdin,
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        capture_output=True,
        text=True,
        check=False,
    )


def edit_payload(path: str | Path, cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(path),
            "old_string": "stored",
            "new_string": f"rewritten {SECRET_TEXT}",
        },
        "cwd": str(cwd),
    }


def write_payload(path: str | Path, cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": f"new {SECRET_TEXT}\n"},
        "cwd": str(cwd),
    }


def shell_payload(command: str, cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


def assert_refused(result: subprocess.CompletedProcess, named: str) -> None:
    assert result.returncode == 2, result.stderr
    assert "odd-guards:" in result.stderr
    assert named in result.stderr
    assert SECRET_TEXT not in result.stderr  # never echo what the tool carries
    assert result.stdout == ""


def assert_passed(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == ""


# --- the payload shapes the hosts send -----------------------------------


def test_reads_the_claude_codex_gemini_cursor_kiro_shape(guard):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": ".odd/decisions.md",
            "old_string": "",
            "new_string": "x",
        },
    }
    assert guard.written_paths(payload) == [".odd/decisions.md"]
    assert guard.written_paths({"tool_input": {"command": "rm .odd/decisions.md"}}) == [
        ".odd/decisions.md"
    ]


def test_reads_the_copilot_shape(guard):
    payload = {"toolName": "edit", "toolArgs": {"path": ".odd/decisions.md"}}
    assert guard.written_paths(payload) == [".odd/decisions.md"]
    payload = {"toolName": "bash", "toolArgs": {"command": "rm .odd/decisions.md"}}
    assert guard.written_paths(payload) == [".odd/decisions.md"]


def test_reads_the_windsurf_shape(guard):
    payload = {
        "agent_action_name": "pre_write_code",
        "tool_info": {"file_path": ".odd/decisions.md", "cwd": "/tmp"},
    }
    assert guard.written_paths(payload) == []  # a bare path is a read on every host
    payload["tool_info"]["text"] = "x"
    assert guard.written_paths(payload) == [".odd/decisions.md"]
    assert guard.payload_cwd(payload) == "/tmp"
    payload = {"tool_info": {"command_line": "rm .odd/decisions.md", "cwd": "/tmp"}}
    assert guard.written_paths(payload) == [".odd/decisions.md"]


def test_a_notebook_edit_names_its_notebook(guard):
    payload = {
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": ".odd/observe-run-reports/r.ipynb"},
    }
    assert guard.written_paths(payload) == [".odd/observe-run-reports/r.ipynb"]


def test_a_read_tool_names_nothing(guard):
    assert (
        guard.written_paths(
            {"tool_name": "Read", "tool_input": {"file_path": ".odd/decisions.md"}}
        )
        == []
    )
    assert guard.written_paths({"tool_input": {"file_path": ".odd/decisions.md"}}) == []
    assert guard.written_paths({}) == []
    assert guard.written_paths({"tool_input": "not an object"}) == []


# --- which paths the rule governs ----------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/repo/.odd/observe-run-reports/2026-08-22-x.md", "report"),
        ("/repo/.odd/otel-instrumentation-reports/2026-08-22-x.md", "report"),
        ("/repo/.odd/observe-run-reports/nested/x.md", "report"),
        ("/repo/.odd/observe-run-reports", "report"),
        ("/repo/.odd/decisions.md", "ledger"),
        ("/repo/.odd/entry-classifications.md", "ledger"),
        ("/repo/.odd/benchmarks/orders/manifest.yaml", None),
        ("/repo/.odd/observability-stacks/contoso.md", None),
        ("/repo/.odd/inbox/2026-08-22-x.md", None),
        ("/repo/.odd/notes.md", None),
        ("/repo/.odd", None),
        ("/repo/docs/observe-run-reports/x.md", None),
        ("/repo/src/.oddities/decisions.md", None),
        ("/repo/.odd/decisions.md.bak", None),
    ],
)
def test_classifies_only_the_report_stores_and_the_ledgers(guard, path, expected):
    assert guard.classify(Path(path)) == expected


# --- which files a shell line writes -------------------------------------


@pytest.mark.parametrize(
    "command, expected",
    [
        (
            "cat > .odd/observe-run-reports/x.md <<'EOF'\nhi\nEOF",
            [".odd/observe-run-reports/x.md"],
        ),
        ("printf 'x' >> .odd/decisions.md", [".odd/decisions.md"]),
        ("echo x >| .odd/decisions.md", [".odd/decisions.md"]),
        ("echo x | tee -a .odd/decisions.md", [".odd/decisions.md"]),
        ("cp a.md /repo/.odd/decisions.md && ls", ["/repo/.odd/decisions.md"]),
        ("mv tmp.md .odd/observe-run-reports/x.md", [".odd/observe-run-reports/x.md"]),
        (
            "mv .odd/observe-run-reports/x.md /tmp/x.md",
            [".odd/observe-run-reports/x.md"],
        ),
        (
            "sed -i 's/a/b/' .odd/observe-run-reports/x.md",
            [".odd/observe-run-reports/x.md"],
        ),
        (
            "sed -i '' 's/a/b/' .odd/observe-run-reports/x.md",
            [".odd/observe-run-reports/x.md"],
        ),
        ("sed -i.bak -e 's/a/b/' .odd/decisions.md", [".odd/decisions.md"]),
        ("sed --in-place=.bak 's/a/b/' .odd/decisions.md", [".odd/decisions.md"]),
        ("rm .odd/observe-run-reports/x.md", [".odd/observe-run-reports/x.md"]),
        ("rm -rf .odd/observe-run-reports", [".odd/observe-run-reports"]),
        ("rm -- .odd/decisions.md", [".odd/decisions.md"]),
        ("git rm .odd/observe-run-reports/x.md", [".odd/observe-run-reports/x.md"]),
        ("git rm -q --cached .odd/decisions.md", [".odd/decisions.md"]),
        ("git -C /repo rm .odd/decisions.md", ["/repo/.odd/decisions.md"]),
        ("cd /repo && rm .odd/decisions.md", ["/repo/.odd/decisions.md"]),
        ("cd sub; rm ../.odd/decisions.md", ["sub/../.odd/decisions.md"]),
        ("mv /tmp/new.md .odd/observe-run-reports/", [".odd/observe-run-reports/"]),
        ("rm -rf .odd", [".odd"]),
        ("rm .odd/observe-run-reports/*.md", [".odd/observe-run-reports/*.md"]),
        ("rm -f .odd/observe-run-reports/*", [".odd/observe-run-reports/*"]),
        (
            "cp -t .odd/observe-run-reports /tmp/a.md b.md",
            [".odd/observe-run-reports/a.md", ".odd/observe-run-reports/b.md"],
        ),
        (
            "cp --target-directory=.odd/observe-run-reports a.md",
            [".odd/observe-run-reports/a.md"],
        ),
        ("mv -t .odd/observe-run-reports /tmp/a.md", [".odd/observe-run-reports/a.md"]),
        ("mv -t /tmp .odd/observe-run-reports/a.md", [".odd/observe-run-reports/a.md"]),
        (
            "git checkout -- .odd/observe-run-reports/x.md",
            [".odd/observe-run-reports/x.md"],
        ),
        ("git checkout HEAD~1 -- .odd/decisions.md", [".odd/decisions.md"]),
        ("git checkout HEAD~1 .odd/decisions.md", [".odd/decisions.md"]),
        (
            "git restore .odd/observe-run-reports/x.md",
            [".odd/observe-run-reports/x.md"],
        ),
        (
            "git restore --source=HEAD~1 --staged .odd/decisions.md",
            [".odd/decisions.md"],
        ),
        ("git restore -s HEAD~1 .odd/decisions.md", [".odd/decisions.md"]),
        ("git checkout -b work", []),
        ("git checkout main", []),
        ("sudo rm .odd/decisions.md", [".odd/decisions.md"]),
        ("sudo -u example-user rm .odd/decisions.md", [".odd/decisions.md"]),
        ("env FOO=1 rm .odd/decisions.md", [".odd/decisions.md"]),
        ("FOO=1 BAR=2 sed -i 's/a/b/' .odd/decisions.md", [".odd/decisions.md"]),
        ("cmd &> .odd/decisions.md", [".odd/decisions.md"]),
        ("cmd &>> .odd/decisions.md", [".odd/decisions.md"]),
        (
            "git mv .odd/observe-run-reports/x.md .odd/observe-run-reports/y.md",
            [".odd/observe-run-reports/x.md", ".odd/observe-run-reports/y.md"],
        ),
        ('cat > "$repo"/.odd/decisions.md <<EOF\nx\nEOF', ["$repo/.odd/decisions.md"]),
        ("sed -n '1,40p' .odd/observe-run-reports/x.md", []),
        ("sed 's/a/b/' .odd/observe-run-reports/x.md > /tmp/out.md", []),
        ("cat .odd/decisions.md; ls .odd/", []),
        ("grep -rn 'x' .odd/observe-run-reports/ | head", []),
        ("cp .odd/observe-run-reports/x.md /tmp/copy.md", []),
        ("git add .odd/observe-run-reports/x.md && git commit -m x", []),
        ("git rm --cached src/x.py", []),
        ("git status", []),
        (
            "python3 .apm/skills/odd-memory/scripts/odd_ledger.py --repo . decide r/F1 wontfix --rationale 'x'",
            [],
        ),
        (
            "cat <<'EOF' > /tmp/notes.md\nrm .odd/observe-run-reports/x.md\n>> .odd/decisions.md\nEOF",
            [],
        ),
        ("echo 'sed -i x .odd/decisions.md'", []),
    ],
)
def test_reads_only_the_governed_paths_a_shell_command_writes(guard, command, expected):
    assert guard.written_paths({"tool_input": {"command": command}}) == expected


# --- the decision, end to end: file tools ----------------------------------


def test_an_edit_on_a_stored_report_is_refused_naming_the_file(memory):
    result = run_hook(edit_payload(memory.observation, memory.root), memory.root)
    assert_refused(result, memory.rel(memory.observation))
    assert "new run" in result.stderr
    assert result.stderr.count("\n") == 1
    result = run_hook(edit_payload(memory.instrumentation, memory.root), memory.root)
    assert_refused(result, memory.rel(memory.instrumentation))


def test_a_write_over_a_stored_report_is_refused(memory):
    result = run_hook(write_payload(memory.observation, memory.root), memory.root)
    assert_refused(result, memory.rel(memory.observation))


def test_a_report_not_committed_yet_stays_the_agents_to_rewrite(memory):
    """The scan hook's repair loop: a report just written, flagged for an
    identifier, is edited or rewritten before its commit."""
    fresh = memory.new_report()
    assert_passed(run_hook(edit_payload(fresh, memory.root), memory.root))
    assert_passed(run_hook(write_payload(fresh, memory.root), memory.root))
    rel = memory.rel(fresh)
    for command in (f"sed -i 's/fresh/clean/' {rel}", f"rm {rel}", f"echo x >> {rel}"):
        assert_passed(run_hook(shell_payload(command, memory.root), memory.root))
    memory.git("add", rel)  # staged, still not committed
    assert_passed(run_hook(edit_payload(fresh, memory.root), memory.root))
    memory.commit()
    assert_refused(run_hook(edit_payload(fresh, memory.root), memory.root), rel)
    assert_refused(run_hook(shell_payload(f"rm {rel}", memory.root), memory.root), rel)


def test_a_committed_report_edited_in_the_working_tree_is_still_refused(memory):
    memory.observation.write_text("edited by hand\n")
    rel = memory.rel(memory.observation)
    assert_refused(
        run_hook(edit_payload(memory.observation, memory.root), memory.root), rel
    )


def test_outside_a_repository_a_stored_report_passes_and_a_ledger_is_refused(tmp_path):
    memory = Memory(tmp_path / "loose", git=False)
    assert_passed(run_hook(edit_payload(memory.observation, memory.root), memory.root))
    rel = memory.rel(memory.observation)
    assert_passed(run_hook(shell_payload(f"rm {rel}", memory.root), memory.root))
    assert_refused(
        run_hook(write_payload(memory.decisions, memory.root), memory.root),
        memory.rel(memory.decisions),
    )


def test_without_git_on_the_path_the_hook_fails_open(memory, tmp_path):
    bare = tmp_path / "bare-bin"
    bare.mkdir()
    payload = edit_payload(memory.observation, memory.root)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "PreToolUse"],
        input=json.dumps(payload),
        cwd=memory.root,
        env={**GIT_ENV, "PATH": str(bare), "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_a_write_creating_a_new_report_passes(memory):
    new = memory.observation.parent / "2026-08-23-orders-api.md"
    assert_passed(run_hook(write_payload(new, memory.root), memory.root))
    new = memory.root / ".odd" / "otel-instrumentation-reports" / "2026-08-23-x.md"
    assert_passed(run_hook(write_payload(new, memory.root), memory.root))


def test_a_relative_path_resolves_against_the_payload_cwd(memory, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    payload = edit_payload(memory.rel(memory.observation), memory.root)
    result = run_hook(payload, elsewhere)
    assert_refused(result, memory.rel(memory.observation))
    del payload["cwd"]
    assert_refused(run_hook(payload, memory.root), memory.rel(memory.observation))
    assert_passed(run_hook(payload, elsewhere))  # nothing stored there


def test_an_edit_under_the_living_source_stores_passes(memory):
    assert_passed(run_hook(edit_payload(memory.benchmark, memory.root), memory.root))
    assert_passed(run_hook(edit_payload(memory.stack, memory.root), memory.root))
    assert_passed(run_hook(write_payload(memory.benchmark, memory.root), memory.root))


def test_a_file_outside_odd_passes(memory):
    readme = memory.root / "README.md"
    readme.write_text("x\n")
    assert_passed(run_hook(edit_payload(readme, memory.root), memory.root))


@pytest.mark.parametrize("ledger", ["decisions", "classifications"])
def test_every_file_tool_write_to_a_ledger_is_refused(memory, ledger):
    path = getattr(memory, ledger)
    result = run_hook(write_payload(path, memory.root), memory.root)
    assert_refused(result, memory.rel(path))
    assert "odd_ledger.py" in result.stderr  # the one legitimate writer
    assert_refused(
        run_hook(edit_payload(path, memory.root), memory.root), memory.rel(path)
    )


def test_a_ledger_that_does_not_exist_yet_is_refused_too(memory):
    memory.decisions.unlink()
    result = run_hook(write_payload(memory.decisions, memory.root), memory.root)
    assert_refused(result, memory.rel(memory.decisions))


def test_an_append_shaped_edit_to_a_ledger_is_refused_as_well(memory):
    payload = edit_payload(memory.decisions, memory.root)
    payload["tool_input"]["old_string"] = ""
    payload["tool_input"]["new_string"] = "| 2026-08-22 | r/F1 | wontfix | x |\n"
    assert_refused(run_hook(payload, memory.root), memory.rel(memory.decisions))


def test_a_read_of_a_stored_report_passes(memory):
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(memory.observation)},
        "cwd": str(memory.root),
    }
    assert_passed(run_hook(payload, memory.root))


def test_a_multi_edit_on_a_stored_report_is_refused(memory):
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(memory.observation),
            "edits": [{"old_string": "stored", "new_string": SECRET_TEXT}],
        },
        "cwd": str(memory.root),
    }
    assert_refused(run_hook(payload, memory.root), memory.rel(memory.observation))


# --- the decision, end to end: shell commands ------------------------------


def test_the_ledger_script_passes(memory):
    command = (
        "python3 /repo/.apm/skills/odd-memory/scripts/odd_ledger.py --repo . "
        "decide 2026-08-22-orders-api/F1 wontfix --rationale 'not worth it'"
    )
    assert_passed(run_hook(shell_payload(command, memory.root), memory.root))


@pytest.mark.parametrize(
    "template",
    [
        "printf '| row |\\n' >> {report}",
        "cat > {report} <<'EOF'\nreplaced\nEOF",
        "sed -i 's/stored/edited/' {report}",
        "sed -i '' 's/stored/edited/' {report}",
        "rm {report}",
        "rm -f {report}",
        "git rm {report}",
        "git rm -q {report} && git commit -m 'drop'",
        "mv /tmp/new.md {report}",
        "mv {report} /tmp/away.md",
        "cp /tmp/new.md {report}",
        "echo x | tee {report}",
    ],
)
def test_a_shell_write_onto_a_stored_report_is_refused(memory, template):
    rel = memory.rel(memory.observation)
    result = run_hook(
        shell_payload(template.format(report=rel), memory.root), memory.root
    )
    assert_refused(result, rel)
    absolute = template.format(report=str(memory.observation))
    assert_refused(run_hook(shell_payload(absolute, memory.root), memory.root), rel)


def test_a_cd_earlier_on_the_line_moves_the_base(memory, tmp_path):
    (memory.root / "sub").mkdir()
    rel = memory.rel(memory.observation)
    command = f"cd sub && rm ../{rel}"
    assert_refused(run_hook(shell_payload(command, memory.root), memory.root), rel)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    command = f"cd {memory.root} && sed -i 's/a/b/' {rel}"
    assert_refused(run_hook(shell_payload(command, elsewhere), elsewhere), rel)


@pytest.mark.parametrize(
    "template",
    [
        "rm {store}/*.md",
        "rm -f {store}/*",
        "rm -rf {store}/2026-*",
        "git rm {store}/*.md",
    ],
)
def test_a_glob_under_a_store_is_refused_for_a_removal(memory, template):
    store = memory.rel(memory.observation.parent)
    result = run_hook(
        shell_payload(template.format(store=store), memory.root), memory.root
    )
    assert_refused(result, f"{store}/")


def test_a_copy_or_move_into_a_store_is_judged_by_the_name_it_lands_on(
    memory, tmp_path
):
    store = memory.rel(memory.observation.parent)
    colliding = tmp_path / "elsewhere" / memory.observation.name
    colliding.parent.mkdir()
    colliding.write_text("x\n")
    fresh = colliding.parent / "2026-08-23-orders-api.md"
    fresh.write_text("x\n")
    rel = memory.rel(memory.observation)
    for command in (
        f"cp -t {store} {colliding}",
        f"cp --target-directory={store} {colliding}",
        f"mv -t {store} {colliding}",
        f"cp {colliding} {store}/",
        f"mv {colliding} {store}",
    ):
        assert_refused(run_hook(shell_payload(command, memory.root), memory.root), rel)
    for command in (
        f"cp -t {store} {fresh}",
        f"mv -t {store} {fresh}",
        f"cp {fresh} {store}/",
        f"mv {fresh} {store}",
    ):
        assert_passed(run_hook(shell_payload(command, memory.root), memory.root))


@pytest.mark.parametrize(
    "template",
    [
        "git checkout -- {report}",
        "git checkout HEAD~1 -- {report}",
        "git restore {report}",
        "git restore --source=HEAD~1 {report}",
        "sudo rm {report}",
        "env FOO=1 rm {report}",
        "FOO=1 sed -i 's/a/b/' {report}",
        "cmd &> {report}",
    ],
)
def test_a_rewrite_shape_or_a_prefixed_command_is_refused(memory, template):
    rel = memory.rel(memory.observation)
    result = run_hook(
        shell_payload(template.format(report=rel), memory.root), memory.root
    )
    assert_refused(result, rel)


def test_deleting_a_whole_report_store_is_refused(memory):
    command = "rm -rf .odd/observe-run-reports"
    result = run_hook(shell_payload(command, memory.root), memory.root)
    assert_refused(result, ".odd/observe-run-reports")
    result = run_hook(shell_payload("rm -rf .odd", memory.root), memory.root)
    assert_refused(result, ".odd/observe-run-reports")
    assert ".odd/otel-instrumentation-reports" in result.stderr
    assert ".odd/decisions.md" in result.stderr
    assert ".odd/benchmarks" not in result.stderr


def test_moving_a_new_report_into_a_store_passes(memory):
    command = "mv /tmp/new.md .odd/observe-run-reports/ && cp /tmp/other.md .odd/otel-instrumentation-reports"
    assert_passed(run_hook(shell_payload(command, memory.root), memory.root))
    command = "git add .odd/observe-run-reports/ && git status"
    assert_passed(run_hook(shell_payload(command, memory.root), memory.root))


@pytest.mark.parametrize(
    "template",
    [
        "printf '| row |\\n' >> {ledger}",
        "sed -i 's/wontfix/fixed/' {ledger}",
        "rm {ledger}",
        "git rm {ledger}",
        "cp /tmp/new.md {ledger}",
    ],
)
@pytest.mark.parametrize("ledger", ["decisions", "classifications"])
def test_a_shell_write_onto_a_ledger_is_refused(memory, template, ledger):
    rel = memory.rel(getattr(memory, ledger))
    result = run_hook(
        shell_payload(template.format(ledger=rel), memory.root), memory.root
    )
    assert_refused(result, rel)


def test_a_shell_write_creating_a_new_report_passes(memory):
    command = (
        "cat > .odd/observe-run-reports/2026-08-23-orders-api.md <<'EOF'\nnew\nEOF"
    )
    assert_passed(run_hook(shell_payload(command, memory.root), memory.root))


@pytest.mark.parametrize(
    "template",
    [
        "sed -n '1,40p' {report}",
        "cat {report}",
        "head -20 {report} | grep finding",
        "git add {report}",
        "git add {report} && git commit -q -m 'docs(odd): observation report'",
        "git diff -- {report}",
        "cp {report} /tmp/copy.md",
        "python3 - <<'EOF'\nprint(open('{report}').read())\nEOF",
        "cat <<'EOF' > /tmp/notes.md\nsee {report}\nrm {report}\nEOF",
        'gh issue comment 1 --body "see {report}"',
    ],
)
def test_a_read_or_a_quoted_mention_of_a_stored_report_passes(memory, template):
    command = template.format(report=memory.rel(memory.observation))
    assert_passed(run_hook(shell_payload(command, memory.root), memory.root))


def test_a_shell_write_under_the_living_source_stores_passes(memory):
    command = f"sed -i 's/a/b/' {memory.rel(memory.benchmark)} && rm {memory.rel(memory.stack)}"
    assert_passed(run_hook(shell_payload(command, memory.root), memory.root))


def test_every_refused_file_is_named_once(memory):
    command = (
        f"rm {memory.rel(memory.observation)} {memory.rel(memory.instrumentation)}"
    )
    result = run_hook(shell_payload(command, memory.root), memory.root)
    assert_refused(result, memory.rel(memory.observation))
    assert memory.rel(memory.instrumentation) in result.stderr
    assert result.stderr.count("\n") == 2


def test_the_message_never_shows_a_home_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    memory = Memory(home / "Repos" / "x")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("HOME", str(home))
    payload = edit_payload(memory.observation, elsewhere)
    result = run_hook(payload, elsewhere)
    assert result.returncode == 2
    assert str(home) not in result.stderr
    assert "~/Repos/x/.odd/observe-run-reports/" in result.stderr


# --- failing open ----------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        "null",
        "42",
        json.dumps({"tool_input": {"command": "git status"}}),
        json.dumps({"tool_input": {"command": ""}}),
        json.dumps({"tool_input": {"command": "echo 'unterminated"}}),
        json.dumps(
            {
                "tool_input": {
                    "file_path": "/nonexistent/.odd/observe-run-reports/x.md",
                    "content": "x",
                }
            }
        ),
        json.dumps({"tool_input": {"file_path": 12, "content": "x"}}),
        json.dumps({"tool_input": {"file_path": "", "content": "x"}}),
        json.dumps(
            {"tool_name": "Read", "tool_input": {"file_path": ".odd/decisions.md"}}
        ),
        json.dumps({"tool_input": {"command": "rm .odd/benchmarks/x.md"}, "cwd": 7}),
        json.dumps(
            {
                "tool_input": {"command": "sed -i x .odd/observe-run-reports/x.md"},
                "cwd": "/nonexistent",
            }
        ),
    ],
)
def test_fails_open_on_anything_it_does_not_understand(tmp_path, payload):
    result = run_hook(payload, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_an_unterminated_quote_still_refuses_what_it_can_read(memory):
    command = f"rm {memory.rel(memory.observation)} && echo 'oops"
    result = run_hook(shell_payload(command, memory.root), memory.root)
    assert_refused(result, memory.rel(memory.observation))


def test_the_script_is_standard_library_only():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "python3 >= 3.10" in text
    for name in ("pytest", "yaml", "requests", "click"):
        assert f"import {name}" not in text and f"from {name}" not in text
