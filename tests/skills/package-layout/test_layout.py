"""Tests for the package-layout skill's installation map.

The script is loaded from its packaged location so the tests exercise
the very file the skill ships. Its one claim is that the answer comes
from the script's own position: a copy elsewhere describes that copy's
installation, not this repository's.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3] / ".apm/skills/package-layout/scripts/layout.py"
)


def load():
    spec = importlib.util.spec_from_file_location("layout", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def layout():
    return load()


def install(root: Path, skills: dict[str, dict]) -> Path:
    """Build a throwaway installation and return its skills root."""
    skills_root = root / "install" / "skills"
    for name, parts in skills.items():
        skill = skills_root / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}\n")
        for reference in parts.get("references", []):
            (skill / "references").mkdir(exist_ok=True)
            (skill / "references" / f"{reference}.md").write_text("x")
        for script in parts.get("scripts", []):
            (skill / "scripts").mkdir(exist_ok=True)
            (skill / "scripts" / script).write_text("x")
    return skills_root


def deploy(skills_root: Path) -> Path:
    """Put the real script where a package-layout skill would sit."""
    scripts = skills_root / "package-layout" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (skills_root / "package-layout" / "SKILL.md").write_text("# package-layout\n")
    copy = scripts / "layout.py"
    copy.write_text(SCRIPT.read_text())
    return copy


def run(copy: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(copy), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_root_is_the_scripts_own_installation(layout):
    root = layout.skills_root()
    assert root.name == "skills"
    assert (root / "package-layout" / "SKILL.md").is_file()


def test_a_copy_describes_its_own_installation_not_this_one(tmp_path):
    skills_root = install(tmp_path, {"alpha": {"references": ["one"]}})
    copy = deploy(skills_root)
    p = run(copy, "--json")
    assert p.returncode == 0, p.stderr
    report = json.loads(p.stdout)
    assert report["skills_root"] == str(skills_root)
    assert {s["name"] for s in report["skills"]} == {"alpha", "package-layout"}


def test_references_and_scripts_are_listed_per_skill(tmp_path):
    skills_root = install(
        tmp_path,
        {"alpha": {"references": ["two", "one"], "scripts": ["b.py", "a.py"]}},
    )
    copy = deploy(skills_root)
    report = json.loads(run(copy, "--skill", "alpha", "--json").stdout)
    alpha = next(s for s in report["skills"] if s["name"] == "alpha")
    assert alpha["references"] == ["one", "two"]
    assert alpha["scripts"] == ["a.py", "b.py"]
    assert alpha["skill_md"].endswith("alpha/SKILL.md")


def test_a_skill_without_references_or_scripts_shows_none(tmp_path):
    skills_root = install(tmp_path, {"bare": {}})
    copy = deploy(skills_root)
    report = json.loads(run(copy, "--skill", "bare", "--json").stdout)
    bare = next(s for s in report["skills"] if s["name"] == "bare")
    assert bare["references"] == [] and bare["scripts"] == []
    assert bare["references_dir"] is None and bare["scripts_dir"] is None


def test_a_directory_without_a_skill_md_is_not_a_skill(tmp_path):
    skills_root = install(tmp_path, {"alpha": {}})
    (skills_root / "not-a-skill").mkdir()
    copy = deploy(skills_root)
    report = json.loads(run(copy, "--json").stdout)
    assert "not-a-skill" not in {s["name"] for s in report["skills"]}


def test_the_install_siblings_are_reported_when_they_exist(tmp_path):
    skills_root = install(tmp_path, {"alpha": {}})
    (skills_root.parent / "agents").mkdir()
    (skills_root.parent / "prompts").mkdir()
    copy = deploy(skills_root)
    report = json.loads(run(copy, "--json").stdout)
    assert set(report["siblings"]) == {"agents", "prompts"}


def test_an_unknown_skill_exits_naming_what_is_installed(tmp_path):
    skills_root = install(tmp_path, {"alpha": {}})
    copy = deploy(skills_root)
    p = run(copy, "--skill", "nope")
    assert p.returncode == 1
    assert "alpha" in p.stderr


def test_the_human_rendering_names_the_roots(tmp_path):
    skills_root = install(tmp_path, {"alpha": {"scripts": ["a.py"]}})
    copy = deploy(skills_root)
    out = run(copy).stdout
    assert f"skills   {skills_root}" in out
    assert "alpha" in out and "a.py" in out
