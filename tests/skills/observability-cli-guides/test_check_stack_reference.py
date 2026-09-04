"""Tests for the observability-cli-guides skill's contract checker.

The script has two callers: CI, on the built-in references (no
argument), and the backend-configuration skill's switch, on a custom
stack file (``--declaration``). Both read the same contract block.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".apm/skills/observability-cli-guides/scripts/check_stack_reference.py"
)
REFERENCES = SCRIPT.parent.parent / "references"
GIT_ENV = {
    "PATH": os.environ["PATH"],
    "HOME": os.environ.get("HOME", ""),
    "GIT_AUTHOR_NAME": "example-user",
    "GIT_AUTHOR_EMAIL": "example-user@example.test",
    "GIT_COMMITTER_NAME": "example-user",
    "GIT_COMMITTER_EMAIL": "example-user@example.test",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _load():
    spec = importlib.util.spec_from_file_location("check_stack_reference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load()
REQUIRED = checker.required_headings((REFERENCES / "CONTRACT.md").read_text())


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def conforming_body() -> str:
    """A body carrying every heading the contract requires, nothing else."""
    lines = []
    for section, subsections in REQUIRED.items():
        lines.append(f"## {section}\n\nprose\n")
        for subsection in subsections:
            lines.append(f"### {subsection}\n\nprose\n")
    return "\n".join(lines)


def custom_file(tmp_path: Path, name="seq", frontmatter=None, body=None) -> Path:
    if frontmatter is None:
        frontmatter = f"---\nstack: {name}\nstack_config_fields: [base_url]\n---\n"
    path = tmp_path / f"{name}.md"
    path.write_text(frontmatter + (conforming_body() if body is None else body))
    return path


# --- the contract block ------------------------------------------------


def test_contract_block_lists_sections_with_their_subsections():
    assert "CLI binary" in REQUIRED
    assert REQUIRED["Configuration display"] == [
        "Display",
        "Connection proof",
        "Change-request phrasing",
    ]
    assert REQUIRED["What to persist"] == [
        "What stack_config holds",
        "Where each value comes from",
        "What to ask the user",
    ]


def test_builtin_references_follow_the_contract():
    result = _run()
    assert result.returncode == 0, result.stderr
    assert "follow the contract" in result.stderr
    assert result.stdout == ""


# --- headings ------------------------------------------------------------


def test_a_missing_section_is_named():
    body = conforming_body().replace("## Planning notes", "## Notes")
    assert checker.check_headings(body, REQUIRED) == ["missing `## Planning notes`"]


def test_a_subsection_under_another_section_is_misplaced():
    body = conforming_body().replace("### Connection proof\n\nprose\n", "")
    body += "\n## Extra\n\n### Connection proof\n\nprose\n"
    assert checker.check_headings(body, REQUIRED) == [
        "missing `### Connection proof` under `## Configuration display`"
    ]


def test_headings_inside_fences_do_not_count():
    body = conforming_body().replace(
        "## Setup\n", "## Setup-notes\n\n```text\n## Setup\n```\n"
    )
    assert checker.check_headings(body, REQUIRED) == ["missing `## Setup`"]


def test_order_is_free_and_extra_sections_are_allowed():
    sections = conforming_body().split("\n## ")
    sections[0] = sections[0].removeprefix("## ")
    body = "## " + "\n## ".join(reversed(sections))
    body += "\n## Remote targeting\n\nprose\n"
    assert checker.check_headings(body, REQUIRED) == []


def test_a_custom_file_without_declaration_flag_checks_headings_only(tmp_path):
    path = custom_file(tmp_path, frontmatter="")
    result = _run(str(path))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    broken = custom_file(tmp_path, name="broken", body="## CLI binary\n")
    result = _run(str(broken))
    assert result.returncode == 1
    assert "missing `## Setup`" in result.stderr


# --- the declaration ---------------------------------------------------


def test_declaration_is_printed_as_the_odd_config_set_payload(tmp_path):
    # The whole config argument of the switch's odd_config_set call, so
    # the skill passes it verbatim and never rebuilds the shape by hand.
    path = custom_file(tmp_path)
    result = _run("--declaration", str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "stack": "seq",
        "custom": {"seq": {"stack_config_fields": ["base_url"]}},
    }


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ("[]", []),
        ("[base_url, api_key_name]", ["base_url", "api_key_name"]),
        ("[\"base_url\", 'workspace']", ["base_url", "workspace"]),
        ("\n  - base_url\n  - workspace", ["base_url", "workspace"]),
    ],
)
def test_declaration_reads_flow_and_block_lists(tmp_path, fields, expected):
    path = custom_file(
        tmp_path, frontmatter=f"---\nstack: seq\nstack_config_fields: {fields}\n---\n"
    )
    result = _run("--declaration", str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["custom"]["seq"] == {
        "stack_config_fields": expected
    }


def test_declaration_reads_the_contracts_own_example(tmp_path):
    # CONTRACT.md shows the frontmatter with trailing YAML comments; a file
    # copied from it must declare cleanly.
    contract = (REFERENCES / "CONTRACT.md").read_text()
    example = re.search(r"```yaml\n(.*?)```", contract, re.DOTALL).group(1)
    frontmatter = example.replace("<name>", "seq")
    assert "#" in frontmatter
    path = custom_file(tmp_path, frontmatter=frontmatter)
    result = _run("--declaration", str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "stack": "seq",
        "custom": {"seq": {"stack_config_fields": []}},
    }


def test_declaration_refuses_a_builtin_name(tmp_path):
    # A learning about a stack the package ships is a package issue, never
    # a custom file: refused at the check, before the server ever sees it.
    path = custom_file(
        tmp_path,
        name="grafana",
        frontmatter="---\nstack: grafana\nstack_config_fields: []\n---\n",
    )
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert result.stdout == ""
    assert "is a built-in stack" in result.stderr


def test_declaration_forwards_only_the_two_keys(tmp_path):
    # The server accepts exactly {"stack_config_fields": [...]} under the
    # stack's name (#228): a verified note or any other frontmatter key
    # belongs to the file and never reaches odd_config_set.
    path = custom_file(
        tmp_path,
        frontmatter=(
            "---\nstack: seq\nverified: 2026-09-04 against a scratch instance\n"
            "stack_config_fields: [base_url]\nsource: none\n---\n"
        ),
    )
    result = _run("--declaration", str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "stack": "seq",
        "custom": {"seq": {"stack_config_fields": ["base_url"]}},
    }


@pytest.mark.parametrize(
    ("frontmatter", "problem"),
    [
        ("", "no frontmatter"),
        ("---\nstack_config_fields: []\n---\n", "missing `stack: <name>`"),
        ("---\nstack: Seq\nstack_config_fields: []\n---\n", "kebab-case"),
        ("---\nstack: seq_prod\nstack_config_fields: []\n---\n", "kebab-case"),
        ("---\nstack: uptrace\nstack_config_fields: []\n---\n", "does not match"),
        ("---\nstack: seq\n---\n", "missing `stack_config_fields"),
        ("---\nstack: seq\nstack_config_fields: base_url\n---\n", "must be a list"),
        ("---\nstack: seq\nstack_config_fields:\n---\n", "must be a list"),
        ("---\nstack: seq\nstack_config_fields: [Base-URL]\n---\n", "snake_case"),
        ("---\nstack: seq\nstack_config_fields: [a, a]\n---\n", "duplicate"),
    ],
)
def test_declaration_rejects_a_malformed_frontmatter(tmp_path, frontmatter, problem):
    path = custom_file(tmp_path, frontmatter=frontmatter)
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert result.stdout == ""
    assert problem in result.stderr


def test_declaration_also_fails_on_a_broken_body(tmp_path):
    path = custom_file(tmp_path, body="## CLI binary\n")
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert result.stdout == ""
    assert "missing `## Setup`" in result.stderr


def test_declaration_takes_exactly_one_file(tmp_path):
    a = custom_file(tmp_path, name="a")
    b = custom_file(tmp_path, name="b")
    assert _run("--declaration", str(a), str(b)).returncode == 2
    assert _run("--declaration").returncode == 2


def test_an_unreadable_file_is_a_named_failure(tmp_path):
    result = _run(str(tmp_path / "missing.md"))
    assert result.returncode == 1
    assert "cannot read" in result.stderr


def test_a_builtin_reference_carries_no_declaration():
    # No frontmatter on the package's own references: the switch never
    # asks them for one, and the check must not require it there.
    for path in REFERENCES.glob("*.md"):
        assert not path.read_text().startswith("---\n"), path.name


# --- a linked guide (issue #323) ----------------------------------------


def linked_file(tmp_path: Path, source_lines: str, name="seq", body="") -> Path:
    path = tmp_path / f"{name}.md"
    path.write_text(
        f"---\nstack: {name}\nstack_config_fields: []\n{source_lines}\n---\n{body}"
    )
    return path


def test_linked_guide_by_url_is_fetched_and_checked(tmp_path):
    guide = tmp_path / "guides" / "seq-guide.md"
    guide.parent.mkdir()
    guide.write_text("# Seq\n\n" + conforming_body())
    fetch_dir = tmp_path / "fetched"
    path = linked_file(tmp_path, f"source_url: {guide.as_uri()}")
    result = _run("--declaration", "--fetch-dir", str(fetch_dir), str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "stack": "seq",
        "custom": {"seq": {"stack_config_fields": []}},
    }
    # The fetched copy lands at a deterministic path the skills read.
    assert (fetch_dir / "seq.md").read_text() == guide.read_text()


def test_linked_guide_by_repo_is_cloned_and_checked(tmp_path):
    # The guide may itself be a full custom stack file in another
    # repository (frontmatter included): its headings are what is checked.
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "stacks").mkdir()
    (origin / "stacks" / "seq.md").write_text(
        "---\nstack: seq\nstack_config_fields: []\n---\n" + conforming_body()
    )
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "guide"],
    ):
        subprocess.run(command, cwd=origin, check=True, env=GIT_ENV)
    fetch_dir = tmp_path / "fetched"
    path = linked_file(
        tmp_path, f"source_repo: {origin}\nsource_path: stacks/seq.md\nsource_ref: main"
    )
    result = _run("--declaration", "--fetch-dir", str(fetch_dir), str(path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["stack"] == "seq"
    assert "## CLI binary" in (fetch_dir / "seq.md").read_text()


def test_linked_guide_reports_where_the_copy_landed(tmp_path):
    guide = tmp_path / "guide.md"
    guide.write_text(conforming_body())
    fetch_dir = tmp_path / "fetched"
    path = linked_file(tmp_path, f"source_url: {guide.as_uri()}")
    result = _run("--declaration", "--fetch-dir", str(fetch_dir), str(path))
    assert result.returncode == 0, result.stderr
    assert f"fetched {guide.as_uri()} to {fetch_dir / 'seq.md'}" in result.stderr
    # Without --fetch-dir the copy lands in a temporary directory, still named.
    result = _run("--declaration", str(path))
    assert result.returncode == 0, result.stderr
    assert "fetched " in result.stderr and "/seq.md" in result.stderr


def test_a_link_to_a_pointer_is_refused(tmp_path):
    pointer = tmp_path / "pointer.md"
    pointer.write_text(
        "---\nstack: seq\nstack_config_fields: []\nsource_url: file:///x\n---\n"
    )
    path = linked_file(tmp_path, f"source_url: {pointer.as_uri()}")
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert "itself a link" in result.stderr
    assert "missing `##" not in result.stderr


def test_linked_guide_with_a_local_body_is_refused(tmp_path):
    guide = tmp_path / "guide.md"
    guide.write_text(conforming_body())
    path = linked_file(tmp_path, f"source_url: {guide.as_uri()}", body="## Notes\n")
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert "carries no body" in result.stderr


def test_linked_guide_that_breaks_the_contract_fails_naming_the_heading(tmp_path):
    guide = tmp_path / "guide.md"
    guide.write_text(conforming_body().replace("## Setup", "## Install"))
    path = linked_file(tmp_path, f"source_url: {guide.as_uri()}")
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert "missing `## Setup`" in result.stderr


def test_linked_guide_that_cannot_be_fetched_is_a_named_failure(tmp_path):
    path = linked_file(tmp_path, f"source_url: {(tmp_path / 'absent.md').as_uri()}")
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert "cannot fetch" in result.stderr
    missing = linked_file(
        tmp_path, f"source_repo: {tmp_path / 'no-repo'}\nsource_path: x.md", name="b"
    )
    result = _run("--declaration", str(missing))
    assert result.returncode == 1
    assert "cannot clone" in result.stderr


@pytest.mark.parametrize(
    ("source_lines", "problem"),
    [
        ("source_repo: /somewhere", "needs `source_path`"),
        ("source_path: stacks/seq.md", "needs `source_repo`"),
        (
            "source_url: file:///x\nsource_repo: /y\nsource_path: z",
            "exclude each other",
        ),
        ("source_url:", "is empty"),
    ],
)
def test_linked_guide_with_malformed_source_keys_is_refused(
    tmp_path, source_lines, problem
):
    path = linked_file(tmp_path, source_lines)
    result = _run("--declaration", str(path))
    assert result.returncode == 1
    assert problem in result.stderr
    # The real cause alone - no phantom missing-heading lines for a
    # file that is a pointer by intent.
    assert "missing `##" not in result.stderr


def test_help_prints_usage():
    result = _run("--help")
    assert result.returncode == 0
    assert result.stdout.startswith("usage:")
