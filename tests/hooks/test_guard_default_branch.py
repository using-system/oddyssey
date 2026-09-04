"""Tests for the default-branch guard hook.

The hook is loaded from its packaged location so the tests exercise the
very file apm deploys. It reads one JSON payload on stdin, the shape
each host gives its pre-tool hook, and blocks - exit 2, one line on
stderr - a ``git commit`` or a ``git push`` aimed at the repository's
default branch while that branch is checked out. Everything else, and
every payload it does not understand, passes with exit 0: a hook that
fails open never breaks a host on a shape nobody foresaw.
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
    / "guard_default_branch.py"
)

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
    spec = importlib.util.spec_from_file_location("guard_default_branch", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load_module()


class Repo:
    """A throwaway git repository with one commit on its initial branch."""

    def __init__(self, root: Path, branch: str = "main"):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", branch)
        (root / "README.md").write_text("probe\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=self.root,
            env={**os.environ, **GIT_ENV},
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()


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


def claude_payload(command: str, cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


# --- the payload shapes the hosts send -----------------------------------


def test_reads_the_claude_codex_gemini_cursor_kiro_shape(guard):
    payload = {"tool_input": {"command": "git status"}}
    assert guard.read_command(payload) == "git status"


def test_reads_the_copilot_shape(guard):
    payload = {"toolName": "bash", "toolArgs": {"command": "git status"}}
    assert guard.read_command(payload) == "git status"


def test_reads_the_windsurf_shape(guard):
    payload = {
        "agent_action_name": "pre_run_command",
        "tool_info": {"command_line": "git status", "cwd": "/tmp"},
    }
    assert guard.read_command(payload) == "git status"


def test_a_payload_without_a_command_reads_as_none(guard):
    assert guard.read_command({"tool_input": {"file_path": "x"}}) is None
    assert guard.read_command({}) is None
    assert guard.read_command({"tool_input": "not an object"}) is None


# --- what the command asks git to do -------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'x'",
        "git add -A && git commit -q -m x",
        "git -c commit.gpgsign=false commit -m x",
        "cd sub; git commit --amend --no-edit",
        "git   commit",
    ],
)
def test_detects_a_commit(guard, command):
    assert guard.git_operations(command) == [("commit", (), None)]


@pytest.mark.parametrize(
    "command, expected",
    [
        ("git push", ()),
        ("git push origin main", ("main",)),
        ("git push -u origin feature", ("feature",)),
        ("git push origin HEAD", ("HEAD",)),
        ("git push origin feature:main", ("main",)),
        ("git push --force-with-lease origin main", ("main",)),
        ("git push origin --delete old", ("old",)),
        ("git push origin :main", ("main",)),
        ("git push origin +main", ("main",)),
        ("git push origin main -o ci.skip", ("main",)),
        ("git push origin main --push-option=ci.skip", ("main",)),
        ("git push -o ci.skip origin main dev", ("main", "dev")),
        ("git push origin refs/heads/main", ("main",)),
    ],
)
def test_detects_a_push_and_its_targets(guard, command, expected):
    assert guard.git_operations(command) == [("push", expected, None)]


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git log --oneline -3",
        "git commit-tree abc",
        "echo 'git commit' > notes.txt",
        "ls",
        "npm test",
        "gh pr create --title 'git commit fix'",
        'echo "git add x && git commit -m msg"',
        'printf "%s\\n" "a && git commit -m x" > f',
        "cat > doc.md <<'EOF'\nrun `git add -A && git commit -m x` then\nEOF",
        "cat <<EOF > doc.md\ngit commit -m x\nEOF\ngit status",
        "cat > d.md <<'EOF-1'\ngit commit -m x\nEOF-1",
        "cat <<-EOF\n\tgit commit -m x\n\tEOF",
    ],
)
def test_ignores_everything_else(guard, command):
    assert guard.git_operations(command) == []


def test_a_command_after_a_heredoc_is_still_read(guard):
    command = "cat <<'EOF' > f\ngit commit -m inside\nEOF\ngit commit -m real"
    assert guard.git_operations(command) == [("commit", (), None)]


def test_reads_the_repository_from_git_dash_c_per_invocation(guard):
    assert guard.git_operations("git -C /some/where commit -m x") == [
        ("commit", (), "/some/where")
    ]
    assert guard.git_operations("git -C/other push origin main && git commit") == [
        ("push", ("main",), "/other"),
        ("commit", (), None),
    ]


# --- the default branch -------------------------------------------------


def test_default_branch_falls_back_to_main(guard, tmp_path):
    repo = Repo(tmp_path)
    assert guard.default_branch(repo.root) == "main"
    assert guard.current_branch(repo.root) == "main"


def test_default_branch_is_master_when_master_is_checked_out(guard, tmp_path):
    repo = Repo(tmp_path, branch="master")
    assert guard.default_branch(repo.root) == "master"


def test_default_branch_comes_from_origin_head_when_set(guard, tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "trunk", str(remote)],
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    repo = Repo(tmp_path / "work", branch="trunk")
    repo.git("remote", "add", "origin", str(remote))
    repo.git("push", "-q", "-u", "origin", "trunk")
    repo.git("remote", "set-head", "origin", "trunk")
    repo.git("checkout", "-q", "-b", "main")
    assert guard.default_branch(repo.root) == "trunk"
    assert guard.current_branch(repo.root) == "main"


def test_outside_a_repository_there_is_no_branch(guard, tmp_path):
    assert guard.current_branch(tmp_path) is None


# --- the decision, end to end -------------------------------------------


def test_blocks_a_commit_on_the_default_branch(tmp_path):
    repo = Repo(tmp_path)
    result = run_hook(claude_payload("git add -A && git commit -m x", repo.root))
    assert result.returncode == 2
    assert "default branch" in result.stderr
    assert "main" in result.stderr
    assert result.stderr.count("\n") == 1


def test_allows_a_commit_on_a_work_branch(tmp_path):
    repo = Repo(tmp_path)
    repo.git("checkout", "-q", "-b", "docs/odd-observe-run-report-x")
    result = run_hook(claude_payload("git commit -m x", repo.root))
    assert result.returncode == 0
    assert result.stderr == ""


def test_blocks_a_push_of_the_default_branch(tmp_path):
    repo = Repo(tmp_path)
    for command in ("git push", "git push origin main", "git push origin HEAD"):
        result = run_hook(claude_payload(command, repo.root))
        assert result.returncode == 2, command
    repo.git("checkout", "-q", "-b", "feature")
    assert (
        run_hook(claude_payload("git push -u origin feature", repo.root)).returncode
        == 0
    )
    assert run_hook(claude_payload("git push origin main", repo.root)).returncode == 2
    assert (
        run_hook(claude_payload("git push origin feature:main", repo.root)).returncode
        == 2
    )


def test_uses_the_payload_cwd_not_the_process_cwd(tmp_path):
    repo = Repo(tmp_path / "repo")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = run_hook(claude_payload("git commit -m x", repo.root), cwd=elsewhere)
    assert result.returncode == 2


def test_honors_git_dash_c(tmp_path):
    repo = Repo(tmp_path / "repo")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    payload = claude_payload(f"git -C {repo.root} commit -m x", elsewhere)
    assert run_hook(payload, cwd=elsewhere).returncode == 2


def test_a_foreign_dash_c_skips_only_its_own_invocation(tmp_path):
    repo = Repo(tmp_path)
    command = "git -C /nonexistent/elsewhere commit -m x && git commit -m y"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2
    only_foreign = "git -C /nonexistent/elsewhere commit -m x"
    assert run_hook(claude_payload(only_foreign, repo.root)).returncode == 0


def test_a_quoted_or_heredoc_commit_line_passes_on_the_default_branch(tmp_path):
    repo = Repo(tmp_path)
    for command in (
        'echo "git add x && git commit -m msg"',
        "cat > doc.md <<'EOF'\ngit commit -m \"docs(odd): report\"\nEOF",
        'printf "%s\\n" "a && git commit -m x" > f',
    ):
        result = run_hook(claude_payload(command, repo.root))
        assert result.returncode == 0, command


def test_blocks_from_the_copilot_and_windsurf_shapes(tmp_path):
    repo = Repo(tmp_path)
    copilot = {
        "toolName": "bash",
        "toolArgs": {"command": "git commit -m x"},
        "cwd": str(repo.root),
    }
    windsurf = {
        "agent_action_name": "pre_run_command",
        "tool_info": {"command_line": "git commit -m x", "cwd": str(repo.root)},
    }
    assert run_hook(copilot).returncode == 2
    assert run_hook(windsurf).returncode == 2


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        json.dumps({"tool_input": {"file_path": "README.md"}}),
        json.dumps(
            {"tool_input": {"command": "git commit -m x"}, "cwd": "/nonexistent/dir"}
        ),
    ],
)
def test_fails_open_on_anything_it_does_not_understand(tmp_path, payload):
    result = run_hook(payload, cwd=tmp_path)
    assert result.returncode == 0


def test_a_non_git_command_on_the_default_branch_passes(tmp_path):
    repo = Repo(tmp_path)
    result = run_hook(claude_payload("npm test && git status", repo.root))
    assert result.returncode == 0
    assert result.stderr == ""
