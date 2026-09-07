#!/usr/bin/env python3
"""Print where this package is installed, and what each part of it is.

A host installs the package wherever it likes, so no path here can be
written down in advance - and an agent left to work one out searches the
filesystem, opens whatever it meets on the way, and pays for it in turns
before any work begins.

This script lives inside the installation, so its own location answers
the question exactly: every skill, its reference files, its scripts, and
the sibling directories the install carries. Nothing is searched for and
no install path is hardcoded anywhere.

    layout.py                    # the whole map
    layout.py --skill odd-memory # one skill's paths, for a mission block
    layout.py --json

Exit 0 always: this describes an installation, it does not judge one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The package's own top-level directory names, beside the skills root.
SIBLINGS = ("agents", "prompts", "commands", "hooks")


def skills_root() -> Path:
    """<root>/<this skill>/scripts/layout.py - so the root is three up."""
    return Path(__file__).resolve().parents[2]


def one_skill(path: Path) -> dict:
    references = path / "references"
    scripts = path / "scripts"
    return {
        "name": path.name,
        "path": str(path),
        "skill_md": str(path / "SKILL.md"),
        "references": sorted(p.stem for p in references.glob("*.md") if p.is_file())
        if references.is_dir()
        else [],
        "references_dir": str(references) if references.is_dir() else None,
        "scripts": sorted(p.name for p in scripts.glob("*.py") if p.is_file())
        if scripts.is_dir()
        else [],
        "scripts_dir": str(scripts) if scripts.is_dir() else None,
    }


def layout() -> dict:
    root = skills_root()
    skills = [
        one_skill(entry)
        for entry in sorted(root.iterdir())
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    ]
    install = root.parent
    siblings = {
        name: str(install / name) for name in SIBLINGS if (install / name).is_dir()
    }
    return {
        "skills_root": str(root),
        "install_root": str(install),
        "siblings": siblings,
        "skills": skills,
    }


def render(report: dict, only: str | None) -> str:
    lines: list[str] = []
    if only is None:
        lines.append(f"skills   {report['skills_root']}")
        for name, path in report["siblings"].items():
            lines.append(f"{name:<8} {path}")
        lines.append("")
    for skill in report["skills"]:
        if only and skill["name"] != only:
            continue
        lines.append(f"{skill['name']}")
        lines.append(f"  SKILL.md    {skill['skill_md']}")
        if skill["references"]:
            lines.append(f"  references  {skill['references_dir']}/<name>.md")
            lines.append(f"              {', '.join(skill['references'])}")
        if skill["scripts"]:
            lines.append(f"  scripts     {skill['scripts_dir']}/<name>")
            lines.append(f"              {', '.join(skill['scripts'])}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skill", help="only this skill's paths")
    ap.add_argument("--json", action="store_true", help="the same, parseable")
    args = ap.parse_args()

    report = layout()
    if args.skill and not any(s["name"] == args.skill for s in report["skills"]):
        known = ", ".join(s["name"] for s in report["skills"])
        print(
            f"no skill named {args.skill!r} is installed here - {known}",
            file=sys.stderr,
        )
        return 1
    if args.json:
        if args.skill:
            report = {
                **report,
                "skills": [s for s in report["skills"] if s["name"] == args.skill],
            }
        print(json.dumps(report, indent=2))
    else:
        print(render(report, args.skill))
    return 0


if __name__ == "__main__":
    sys.exit(main())
