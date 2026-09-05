"""Tests for the default-branch guard hook.

The hook is loaded from its packaged location so the tests exercise the
very file apm deploys. It reads one JSON payload on stdin, the shape
each host gives its pre-tool hook, and blocks - exit 2, one line on
stderr - a ``git commit`` or a ``git push`` aimed at the repository's
default branch - the one checked out, or the one a ``git switch`` or
``git checkout`` earlier on the same line moves to. Everything else, and
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


def remote_only_branch(repo: Repo, remote: str, branch: str) -> None:
    """Publish ``branch`` on a new bare ``remote`` and drop the local copy: the
    state a fresh clone is in before ``git switch <branch>`` guesses it."""
    bare = repo.root.parent / f"{remote}.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", str(bare)],
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    repo.git("remote", "add", remote, str(bare))
    repo.git("branch", branch)
    repo.git("push", "-q", remote, branch)
    repo.git("branch", "-q", "-D", branch)


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


@pytest.mark.parametrize(
    "command, expected",
    [
        ("git switch -c docs/x", [("switch", ("docs/x",), None)]),
        ("git switch -C docs/x", [("switch", ("docs/x",), None)]),
        ("git switch --create docs/x", [("switch", ("docs/x",), None)]),
        ("git switch docs/x", [("unresolved", ("docs/x", "switch"), None)]),
        ("git switch -c docs/x main", [("switch", ("docs/x",), None)]),
        ("git checkout -b docs/x", [("switch", ("docs/x",), None)]),
        ("git checkout -B docs/x origin/main", [("switch", ("docs/x",), None)]),
        ("git checkout --orphan docs/x", [("switch", ("docs/x",), None)]),
        ("git checkout -q -b docs/x", [("switch", ("docs/x",), None)]),
        ("git switch -cdocs/x", [("switch", ("docs/x",), None)]),
        ("git checkout -bdocs/x", [("switch", ("docs/x",), None)]),
        ("git switch --create=docs/x", [("switch", ("docs/x",), None)]),
        ("git checkout --orphan=docs/x", [("switch", ("docs/x",), None)]),
        ("git switch -", [("switch", (), None)]),
        ("git switch --detach", [("switch", (), None)]),
        ("git checkout --detach HEAD~1", [("switch", (), None)]),
        ("git checkout -t origin/docs/x", [("switch", (), None)]),
        ("git switch --track=origin/docs/x", [("switch", (), None)]),
        ("git checkout -torigin/docs/x", [("switch", (), None)]),
        ("git checkout docs/x", [("unresolved", ("docs/x", "checkout"), None)]),
        (
            "git switch --no-guess docs/x",
            [("unresolved", ("docs/x", "switch", "--no-guess"), None)],
        ),
        (
            "git checkout --no-guess docs/x",
            [("unresolved", ("docs/x", "checkout", "--no-guess"), None)],
        ),
        (
            "git switch --no-guess --guess docs/x",
            [("unresolved", ("docs/x", "switch"), None)],
        ),
        ("git switch -qc docs/x", [("switch", ("docs/x",), None)]),
        ("git checkout -qb docs/x", [("switch", ("docs/x",), None)]),
        ("git checkout -qbdocs/x", [("switch", ("docs/x",), None)]),
        ("git branch docs/x", [("branch", ("docs/x",), None)]),
        ("git branch docs/x main", [("branch", ("docs/x",), None)]),
        ("git branch -d docs/x", []),
        ("git branch -m docs/x docs/y", []),
        ("git branch --list", []),
        ("git branch", []),
        ("git checkout -- README.md", []),
        ("git checkout main -- README.md", []),
        ("git checkout", []),
        ("git switch", []),
        (
            "git -C /r switch -c docs/x && git -C /r commit -m x",
            [("switch", ("docs/x",), "/r"), ("commit", (), "/r")],
        ),
        (
            "git switch -c docs/x && git add -A && git commit -m x",
            [("switch", ("docs/x",), None), ("commit", (), None)],
        ),
        (
            "git switch -c docs/x || git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git switch -c docs/x || \\\n  git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git switch -c docs/x || true && git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git switch docs/x || git switch -c docs/x; git commit -m x",
            [
                ("unresolved", ("docs/x", "switch"), None),
                ("||", (), None),
                ("switch", ("docs/x",), None),
                ("commit", (), None),
            ],
        ),
        (
            "git switch -c docs/x || git switch -c docs/y; git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git branch docs/x || git switch -c docs/x",
            [("branch", ("docs/x",), None), ("||", (), None)],
        ),
        (
            "git switch -c docs/x || exit 1; git commit -m x",
            [("switch", ("docs/x",), None), ("commit", (), None)],
        ),
        (
            "git switch -c docs/x || return 1\ngit commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git switch -c docs/x || (exit 1); git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git switch -c docs/x ||(exit 1); git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "(git switch -c docs/x || exit 1); git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git switch -c docs/x || { exit 1; }; git commit -m x",
            [("switch", ("docs/x",), None), ("||", (), None), ("commit", (), None)],
        ),
        (
            "git fetch || git switch -c docs/x && git commit -m x",
            [("||", (), None), ("commit", (), None)],
        ),
        ("git fetch || git status", [("||", (), None)]),
        ("git fetch || exit 1", []),
    ],
)
def test_detects_a_branch_switch_before_a_commit(guard, command, expected):
    assert guard.git_operations(command) == expected


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


@pytest.mark.parametrize(
    "command",
    [
        "git switch -c docs/odd-stack-seq && git add .odd && git commit -m x",
        "git checkout -b docs/x && git add -A && git commit -q -m x",
        "git switch docs/x ; git commit -m x",
        "git switch -c docs/x && git commit -m x && git push -u origin docs/x",
        "git switch -c docs/x\ngit add -A\ngit commit -m x",
        "git -C . switch -c docs/x && git -C . commit -m x",
    ],
)
def test_allows_a_commit_after_a_switch_to_a_work_branch_on_the_same_line(
    tmp_path, command
):
    repo = Repo(tmp_path)
    repo.git("branch", "docs/x")  # the plain `git switch docs/x` form needs it
    result = run_hook(claude_payload(command, repo.root))
    assert result.returncode == 0, command
    assert result.stderr == ""


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m x && git switch -c docs/x",
        "git switch -c docs/x && git commit -m x && git switch main && git commit -m y",
        "git switch -c docs/x && git commit -m x && git push origin main",
        "git checkout README.md && git commit -m x",
        "git checkout -- README.md && git commit -m x",
        "git switch no-such-branch ; git commit -m x",
        'git switch "$branch" && git commit -m x',
        "git checkout $branch && git commit -m x",
    ],
)
def test_still_blocks_a_commit_that_lands_on_the_default_branch(tmp_path, command):
    repo = Repo(tmp_path)
    result = run_hook(claude_payload(command, repo.root))
    assert result.returncode == 2, command
    assert "default branch" in result.stderr


def test_a_branch_created_earlier_on_the_line_is_a_valid_destination(tmp_path):
    repo = Repo(tmp_path)
    for command in (
        "git branch docs/x && git switch docs/x && git commit -m x",
        "git branch docs/x main && git checkout docs/x && git add -A && git commit -m x",
    ):
        assert run_hook(claude_payload(command, repo.root)).returncode == 0, command
    command = "git branch docs/x && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2


def test_a_detaching_checkout_lets_the_commit_through(tmp_path):
    repo = Repo(tmp_path)
    repo.git("tag", "v1")
    sha = repo.git("rev-parse", "HEAD")
    for command in (
        "git checkout v1 && git commit -m x",
        f"git checkout {sha} && git commit -m x",
        "git switch --detach v1 && git commit -m x",
    ):
        assert run_hook(claude_payload(command, repo.root)).returncode == 0, command
    command = "git checkout v1 && git push origin main"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2


def test_restoring_a_deleted_file_is_not_a_branch_switch(tmp_path):
    repo = Repo(tmp_path)
    (repo.root / "README.md").unlink()
    command = "git checkout README.md && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2


def test_a_switch_in_another_repository_does_not_move_this_one(tmp_path):
    repo = Repo(tmp_path / "repo")
    other = Repo(tmp_path / "other")
    command = f"git -C {other.root} switch -c docs/x && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2
    command = f"git switch -c docs/x && git -C {other.root} commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        "git switch --detach && git push origin main",
        "git switch - && git push origin main",
        "git checkout -t origin/docs/x && git push origin HEAD:main",
        "git switch -c docs/x && git push origin main",
        "git switch -c docs/x && git push --force origin main",
    ],
)
def test_a_push_whose_refspec_names_the_default_branch_blocks_after_any_switch(
    tmp_path, command
):
    repo = Repo(tmp_path)
    result = run_hook(claude_payload(command, repo.root))
    assert result.returncode == 2, command
    assert "never push" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git switch - && git commit -m x",
        "git switch --detach && git commit -m x",
        "git checkout -t origin/docs/x && git commit -m x",
    ],
)
def test_a_switch_only_git_can_resolve_lets_the_commit_through(tmp_path, command):
    repo = Repo(tmp_path)
    assert run_hook(claude_payload(command, repo.root)).returncode == 0, command


def test_a_branch_only_one_remote_carries_is_a_valid_destination(tmp_path):
    repo = Repo(tmp_path / "repo")
    remote_only_branch(repo, "origin", "feature")
    for command in (
        "git switch feature && git commit -m x",
        "git checkout feature && git add -A && git commit -m x",
        "git switch --no-guess feature || git switch feature && git commit -m x",
    ):
        assert run_hook(claude_payload(command, repo.root)).returncode == 0, command
    for command in (
        "git switch --no-guess feature && git commit -m x",
        "git checkout --no-guess feature && git commit -m x",
        "git switch feature && git push origin main",
    ):
        assert run_hook(claude_payload(command, repo.root)).returncode == 2, command


def test_a_branch_several_remotes_carry_moves_nowhere_without_a_default_remote(
    tmp_path,
):
    repo = Repo(tmp_path / "repo")
    remote_only_branch(repo, "origin", "feature")
    remote_only_branch(repo, "second", "feature")
    command = "git switch feature && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2
    repo.git("config", "checkout.defaultRemote", "second")
    assert run_hook(claude_payload(command, repo.root)).returncode == 0


def test_a_remote_tracking_ref_of_no_configured_remote_is_not_a_destination(
    tmp_path,
):
    repo = Repo(tmp_path)
    repo.git("update-ref", "refs/remotes/nowhere/ghost", "HEAD")
    command = "git switch ghost && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2


def test_a_branch_homonymous_with_a_directory_is_still_a_branch(tmp_path):
    repo = Repo(tmp_path)
    repo.git("branch", "docs")
    (repo.root / "docs").mkdir()
    (repo.root / "docs" / "guide.md").write_text("probe\n")
    for command in (
        "git switch docs && git commit -m x",
        "git checkout docs && git commit -m x",
    ):
        assert run_hook(claude_payload(command, repo.root)).returncode == 0, command


def test_the_default_branch_homonymous_with_a_file_still_blocks(tmp_path):
    repo = Repo(tmp_path)
    repo.git("checkout", "-q", "-b", "docs/x")
    (repo.root / "main").write_text("probe\n")
    for command in (
        "git checkout main && git commit -m x",
        "git switch main && git commit -m x",
    ):
        assert run_hook(claude_payload(command, repo.root)).returncode == 2, command


def test_a_remote_only_branch_homonymous_with_a_path_moves_nowhere_under_checkout(
    tmp_path,
):
    repo = Repo(tmp_path / "repo")
    remote_only_branch(repo, "origin", "only")
    (repo.root / "only").mkdir()
    command = "git checkout only && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2
    command = "git switch only && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 0


@pytest.mark.parametrize(
    "command",
    [
        "git switch -c work || git commit -m x",
        "git switch docs/x || git commit -m x",
        "git switch -c work || git add -A || git commit -m x",
        "git fetch -q || git switch -c work; git commit -m x",
        "git switch -c work && git switch main || git commit -m x",
        "git switch -c work || \\\n  git commit -m x",
        "git switch -c work || \\\n  git push",
        "git switch -c work || true && git commit -m x",
        "git switch -c work || git status && git commit -m x",
        "git switch -c work || echo failed; git commit -m x",
        "git switch -c work || git switch -c other; git commit -m x",
        "git switch -c work || { exit 1; }; git commit -m x",
        "git switch -c work && git commit -m a || git commit -m b",
        "git switch work || git branch work; git commit -m x",
        "git branch work || git switch -c work; git commit -m x",
        "git switch -c work || return 1; git commit -m x",
        "git switch -c work || (exit 1); git commit -m x",
        "(git switch -c work || exit 1); git commit -m x",
        "git switch feature || git checkout feature; git commit -m x",
        "git checkout docs || git checkout docs; git commit -m x",
        "git switch --no-guess feature || git switch feature; git commit -m x",
        "git switch nosuch || git switch nosuch; git commit -m x",
    ],
)
def test_a_commit_that_runs_only_if_the_switch_failed_is_judged_where_it_lands(
    tmp_path, command
):
    repo = Repo(tmp_path)
    repo.git("branch", "docs/x")
    (repo.root / "docs").mkdir()  # a directory, and no branch or remote `docs`
    result = run_hook(claude_payload(command, repo.root))
    assert result.returncode == 2, command
    assert "default branch" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git switch -c work || exit 1; git commit -m x",
        "git switch -c work || exit 1\ngit add -A\ngit commit -m x",
        "git switch -c work || git switch work && git commit -m x",
        "git switch docs/x || git switch -c docs/x; git commit -m x",
        "git switch -c work || true; git switch -c other && git commit -m x",
    ],
)
def test_a_switch_guarded_by_an_or_exit_still_moves_the_commit(tmp_path, command):
    repo = Repo(tmp_path)
    repo.git("branch", "docs/x")
    assert run_hook(claude_payload(command, repo.root)).returncode == 0, command


def test_a_switch_recovered_by_creating_the_same_branch_lands_on_it_either_way(
    tmp_path,
):
    repo = Repo(tmp_path)
    command = "git switch docs/x || git switch -c docs/x; git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 0  # absent
    repo.git("branch", "docs/x")
    assert run_hook(claude_payload(command, repo.root)).returncode == 0  # present
    command = "git switch main || git switch -c main; git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2


def test_a_switch_back_to_the_default_branch_blocks_the_commit_after_it(tmp_path):
    repo = Repo(tmp_path)
    repo.git("checkout", "-q", "-b", "docs/x")
    assert run_hook(claude_payload("git commit -m x", repo.root)).returncode == 0
    command = "git switch main && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2
    command = "git checkout main && git commit -m x"
    assert run_hook(claude_payload(command, repo.root)).returncode == 2


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
