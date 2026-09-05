#!/usr/bin/env python3
"""List the stored reports a mission's recall should consider, newest first.

A recall used to read every stored report's frontmatter into the
conversation to find one baseline. This script reads them in Python
instead and prints one line per match - the first line is the baseline,
the only file the mission then opens, by section. The matching rules
are the odd-memory references'; the script applies the flags it is
given, and each reference says which flags a mission passes.

Standard library and git only; it imports no other skill's script.
stdout carries the matches only, one per line, tab-separated:

    filename  kind  services|project  stack  environment  mode  depth  verifies  workload  repository

(``-`` for an absent value; a plan carries its ``project`` in the third
column and ``-`` in the observation-only ones). stderr carries what is
not a match: a report the memory contract's frontmatter checks flag
(listed all the same, never skipped silently), a newer quick report a
full mission skips, a scope matching nothing and what exists instead,
an absent store. Exit 0 in every one of those cases - a first run is
normal; 2 on a usage error or outside a git repository.

    python3 odd_recall.py [--repo PATH] [--kind observation|instrumentation]
                          [--service S ...] [--stack S] [--env E]
                          [--depth quick|full] [--mode M ...] [--project P]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

STORES = {
    "observation": ".odd/observe-run-reports",
    "instrumentation": ".odd/otel-instrumentation-reports",
}
COLUMNS = (
    "filename",
    "kind",
    "services",
    "stack",
    "environment",
    "mode",
    "depth",
    "verifies",
    "workload",
    "repository",
)
# the frontmatter contract's shapes, exactly as get-status's memory invariant
# reads them - a test asserts the two agree on a set of report shapes
FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z_][\w.-]*):(.*)$")
REPORT_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-\d{4}-([a-z0-9][a-z0-9-]*)\.md$")
WINDOW_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$"
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OBSERVATION_MODES = ("drive", "observe", "post-hoc", "verify", "re-measure")
REPLAY_MODES = ("verify", "re-measure")
DEPTHS = ("quick", "full")


class Refusal(Exception):
    """One reason, one stderr line, exit 2."""


# --- the frontmatter, read as the contract writes it ---------------------------------


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside quotes and outside nested brackets - the
    status script's reading, line for line."""
    parts, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"') and scalar_can_start(buf):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf)
    if tail.strip() or parts:
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def scalar_can_start(buf: list[str]) -> bool:
    before = "".join(buf).rstrip()
    return before == "" or before.endswith(":")


def parse_scalar(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "~", ""):
        return None
    return text


def parse_value(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [parse_value(item) for item in split_top_level(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        mapping = {}
        for item in split_top_level(text[1:-1]):
            key, _, value = item.partition(":")
            mapping[parse_scalar(key)] = parse_value(value)
        return mapping
    return parse_scalar(text)


def split_frontmatter(text: str) -> tuple[dict, list[str]]:
    """The frontmatter mapping and the lines it could not read (block-style
    values are outside the contract: reported, read as null)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["no frontmatter block"]
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, ["unterminated frontmatter block"]
    raw: list[list[Any]] = []
    errors: list[str] = []
    for number, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        match = FRONTMATTER_LINE_RE.match(line)
        if match:
            raw.append([match.group(1), match.group(2), False])
        elif line[0].isspace() and raw:
            stripped = line.strip()
            block = stripped.startswith("- ") or stripped == "-" or ": " in stripped
            if block and not raw[-1][1].strip():
                raw[-1][2] = True
            else:
                raw[-1][1] = raw[-1][1] + " " + stripped
        else:
            errors.append(
                f"line {number}: no colon-separated key, kept out: {line.strip()!r}"
            )
    frontmatter: dict = {}
    for key, value, block_style in raw:
        if block_style:
            errors.append(
                f"{key}: block-style value (the contract is flow style), read as null"
            )
            frontmatter[key] = None
        else:
            frontmatter[key] = parse_value(value)
    return frontmatter, errors


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def read_report(path: Path, kind: str) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"name": path.name, "kind": kind, "unreadable": str(exc)}
    frontmatter, errors = split_frontmatter(text)
    return {
        "name": path.name,
        "kind": kind,
        "frontmatter": frontmatter,
        "frontmatter_errors": errors,
    }


# --- the contract's checks, as the memory invariant applies them ---------------------


def check(report: dict, stored_names: set[str], root: Path) -> list[str]:
    """What the report lacks against the frontmatter contract - the checks
    get-status's memory invariant makes, minus the legacy note on an absent
    depth (it reads as full, and nothing can change an append-only file)."""
    problems: list[str] = []
    match = REPORT_NAME_RE.match(report["name"])
    if not match:
        problems.append("filename is not YYYY-MM-DD-HHmm-<run_name>.md")
    if "unreadable" in report:
        problems.append(f"unreadable: {report['unreadable']}")
        return problems
    fm = report["frontmatter"]
    for error in report["frontmatter_errors"]:
        problems.append(f"frontmatter: {error}")
    if not fm:
        problems.append("frontmatter absent")
        return problems

    def scalar(key: str) -> str | None:
        value = fm.get(key)
        if value is None or value == "" or value == []:
            problems.append(f"{key} absent")
            return None
        return str(value)

    kind = report["kind"]
    required = (
        ("project", "stack", "run_name", "date")
        if kind == "instrumentation"
        else ("services", "stack", "environment", "mode", "window", "run_name", "date")
    )
    values = {key: scalar(key) for key in required}
    if kind == "observation":
        if fm.get("services") is not None and not as_list(fm.get("services")):
            problems.append("services empty")
        mode = values.get("mode")
        if mode is not None and mode not in OBSERVATION_MODES:
            problems.append(f"mode {mode!r} is not one of {list(OBSERVATION_MODES)}")
        depth = fm.get("depth")
        if depth is not None and str(depth) not in DEPTHS:
            problems.append(f"depth {str(depth)!r} is not one of {list(DEPTHS)}")
        window = values.get("window")
        if window is not None:
            wm = WINDOW_RE.match(window)
            if not wm:
                problems.append(
                    "window is not <start>/<end> in UTC (YYYY-MM-DDTHH:MM:SSZ)"
                )
            elif wm.group(2) < wm.group(1):
                problems.append("window end precedes its start")
        verifies = fm.get("verifies")
        if mode in REPLAY_MODES and not verifies:
            problems.append(f"verifies absent on a {mode} report")
        elif verifies:
            target = str(verifies)
            exists = (
                (root / target).is_file() if "/" in target else target in stored_names
            )
            if not exists:
                problems.append(f"verifies names no stored report: {target}")
    date = values.get("date")
    if date is not None and not DATE_RE.match(date):
        problems.append(f"date {date!r} is not YYYY-MM-DD")
    if match:
        if date is not None and DATE_RE.match(date) and date != match.group(1):
            problems.append(f"date {date} differs from the filename's {match.group(1)}")
        run_name = values.get("run_name")
        if run_name is not None:
            mode = fm.get("mode") if kind == "observation" else None
            prefix = {"verify": "verify-", "re-measure": "remeasure-"}.get(
                str(mode), ""
            )
            expected = f"{prefix}{run_name}"
            if match.group(2) != expected:
                with_prefix = f" with the {prefix} prefix" if prefix else ""
                problems.append(
                    f"filename slug {match.group(2)!r} is not {expected!r}"
                    f" (run_name {run_name!r}{with_prefix})"
                )
    return problems


# --- the matching rules, as the references state them --------------------------------


def matches(report: dict, scope: dict) -> bool:
    if "unreadable" in report:
        return False
    fm = report["frontmatter"]
    if scope["stack"] and str(fm.get("stack")) != scope["stack"]:
        return False
    if report["kind"] == "instrumentation":
        project = str(fm.get("project") or "")
        target = scope["project"]
        return not target or target == project or target.startswith(project + "/")
    if scope["services"] and not (
        set(scope["services"]) & set(as_list(fm.get("services")))
    ):
        return False
    if scope["environment"] and str(fm.get("environment")) != scope["environment"]:
        return False
    return not scope["modes"] or str(fm.get("mode")) in scope["modes"]


def cell(value: Any) -> str:
    if value is None or value == "" or value == []:
        return "-"
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    if isinstance(value, dict):
        return ",".join(f"{k}={cell(v)}" for k, v in value.items())
    return str(value).replace("\t", " ")


def line_of(report: dict) -> str:
    fm = report["frontmatter"]
    plan = report["kind"] == "instrumentation"
    return "\t".join(
        [
            report["name"],
            report["kind"],
            cell(fm.get("project") if plan else fm.get("services")),
            cell(fm.get("stack")),
            "-" if plan else cell(fm.get("environment")),
            "-" if plan else cell(fm.get("mode")),
            "-" if plan else cell(fm.get("depth")),
            "-" if plan else cell(fm.get("verifies")),
            "-" if plan else cell(fm.get("workload")),
            cell(fm.get("repository")),
        ]
    )


def git_root(path: Path) -> Path:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise Refusal(f"git is not available: {exc}") from exc
    if proc.returncode != 0:
        raise Refusal(f"not a git repository: {path.resolve()}")
    return Path(proc.stdout.strip())


def describe(scope: dict) -> str:
    parts = []
    for name, value in (
        ("service", ", ".join(scope["services"])),
        ("stack", scope["stack"]),
        ("environment", scope["environment"]),
        ("mode", ", ".join(scope["modes"])),
        ("depth", scope["depth"]),
        ("project", scope["project"]),
    ):
        if value:
            parts.append(f"{name} {value}")
    return ", ".join(parts) or "no scope"


def recall(root: Path, kind: str, scope: dict) -> tuple[list[str], list[str]]:
    """The stdout lines and the stderr lines."""
    store = root / STORES[kind]
    paths = sorted(store.glob("*.md"), reverse=True) if store.is_dir() else []
    if not paths:
        return [], [f"no report under {STORES[kind]}/ - a first run"]
    reports = [read_report(p, kind) for p in paths]
    stored = {r["name"] for r in reports}
    out: list[str] = []
    err: list[str] = []
    # every stored report is checked, matched or not: a flaw in the very
    # field the scope matches on must never hide the report silently
    problems = {r["name"]: check(r, stored, root) for r in reports}
    matched = [r for r in reports if matches(r, scope)]
    if kind == "observation" and scope["depth"] == "full":
        kept, skipped = [], []
        for r in matched:
            depth = r["frontmatter"].get("depth")
            if depth is not None and str(depth) != "full":
                if not kept:  # ahead of the baseline: name the skip
                    skipped.append(r["name"])
                continue
            kept.append(r)
        if kept:
            err.extend(f"newer quick report skipped: {name}" for name in skipped)
        elif skipped:
            err.append(
                f"no full match; {len(skipped)} quick report(s) skipped: "
                + ", ".join(skipped)
            )
        matched = kept
    matched_names = {r["name"] for r in matched}
    for r in matched:
        out.append(line_of(r))
        err.extend(f"{r['name']}: {p}" for p in problems[r["name"]])
    for r in reports:
        if r["name"] not in matched_names:
            err.extend(
                f"not matched, flagged: {r['name']}: {p}" for p in problems[r["name"]]
            )
    if not out:
        readable = [r for r in reports if "unreadable" not in r]
        services = sorted(
            {s for r in readable for s in as_list(r["frontmatter"].get("services"))}
        )
        projects = sorted(
            {
                str(r["frontmatter"]["project"])
                for r in readable
                if r["frontmatter"].get("project")
            }
        )
        stacks = sorted(
            {
                str(r["frontmatter"]["stack"])
                for r in readable
                if r["frontmatter"].get("stack")
            }
        )
        environments = sorted(
            {
                str(r["frontmatter"]["environment"])
                for r in readable
                if r["frontmatter"].get("environment")
            }
        )
        err.append(
            f"no stored report matches {describe(scope)}; stored: "
            + (
                f"projects: {', '.join(projects) or 'none'}; "
                if kind == "instrumentation"
                else f"services: {', '.join(services) or 'none'}; "
            )
            + f"stacks: {', '.join(stacks) or 'none'}; "
            + f"environments: {', '.join(environments) or 'none'}"
        )
    return out, err


# --- cli ---------------------------------------------------------------------------


class OneLineParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(f"{self.prog}: {message} (see --help)", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    parser = OneLineParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".", help="a path inside the repository")
    parser.add_argument(
        "--kind",
        choices=tuple(STORES),
        default="observation",
        help="which store (default: observation)",
    )
    parser.add_argument("--service", action="append", default=[], help="repeatable")
    parser.add_argument("--stack")
    parser.add_argument(
        "--env", help="the detected environment; omit while provisional"
    )
    parser.add_argument("--depth", choices=DEPTHS, help="the mission's depth")
    parser.add_argument("--mode", action="append", default=[], help="repeatable")
    parser.add_argument(
        "--project", help="the scope a plan must cover (instrumentation)"
    )
    args = parser.parse_args(argv)
    if args.kind == "instrumentation" and (
        args.service or args.env or args.mode or args.depth
    ):
        parser.error(
            "--service, --env, --mode and --depth apply to observation reports only"
        )
    if args.kind == "observation" and args.project:
        parser.error("--project applies to instrumentation reports only")
    scope = {
        "services": args.service,
        "stack": args.stack,
        "environment": args.env,
        "depth": args.depth,
        "modes": args.mode,
        "project": args.project,
    }
    try:
        root = git_root(Path(args.repo))
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    out, err = recall(root, args.kind, scope)
    if out:
        sys.stdout.write("\n".join(out) + "\n")
    if err:
        print("\n".join(err), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
