#!/usr/bin/env python3
"""List the stored memory a mission's recall should consider, newest first.

A recall used to read every stored report's frontmatter into the
conversation to find one baseline. This script reads them in Python
instead and prints one line per match - the first line is the baseline,
the only file the mission then opens, by section. The matching rules
are the odd-memory references'; the script applies the flags it is
given, and each reference says which flags a mission passes.

Standard library and git only; the report format is read through
odd_report.py beside this file, and no other skill's script.
stdout carries the matches only, one per line, tab-separated. A report
kind prints

    filename  kind  services|project  stack  environment  mode  depth  verifies  workload  repository

(``-`` for an absent value; a plan carries its ``project`` in the third
column and ``-`` in the observation-only ones). A benchmark is a
directory, not a dated file, and it is recalled as a set - the whole
listing is what the mission checks itself against, not just its first
line - so it prints its own five columns, read from the manifest:

    name  service  test_type  executor  authored

Every benchmark directory prints such a line, ``-`` in each column its
manifest could not fill: the listing is what says a name is taken, and
a name dropped from it would read as free.

stderr carries what is not a match: a report the memory contract's
frontmatter checks flag, or a benchmark whose manifest a recall cannot
read (listed all the same, never skipped silently), a newer quick
report a full mission skips, a scope matching nothing and what exists
instead, an absent store. Exit 0 in every one of those cases - a first
run is normal; 2 on a usage error or outside a git repository.

    python3 odd_recall.py [--repo PATH]
                          [--kind observation|instrumentation|benchmark]
                          [--service S ...] [--stack S] [--env E]
                          [--depth quick|full] [--mode M ...] [--project P]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

# The report format is read through odd_report.py beside this file: one
# parser for one format, owned by this skill.
sys.dont_write_bytecode = True  # never leave bytecode in the package
sys.path.insert(0, str(Path(__file__).resolve().parent))
from odd_report import (
    DATE_RE,
    DEPTHS,
    LEGACY_PREFIX,
    as_list,
    check_report,
    parse_value,
    read_report,
)
from odd_report import (
    git_root as _git_root,
)

STORES = {
    "observation": ".odd/observe-run-reports",
    "instrumentation": ".odd/otel-instrumentation-reports",
    "benchmark": ".odd/benchmarks",
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
BENCHMARK_COLUMNS = ("name", "service", "test_type", "executor", "authored")
MANIFEST = "manifest.yaml"
MANIFEST_LINE_RE = re.compile(r"^(\s*)([A-Za-z_][\w.-]*):(.*)$")


# the frontmatter contract's shapes, exactly as get-status's memory invariant
# reads them - a test asserts the two agree on a set of report shapes
class Refusal(Exception):
    """One reason, one stderr line, exit 2."""


def git_root(path: Path) -> Path:
    root = _git_root(path)
    if root is None:
        raise Refusal(f"not a git repository: {path.resolve()}")
    return root


def check(report: dict, stored_names: set[str], root: Path) -> list[str]:
    """What the report lacks against the frontmatter contract - the checks
    get-status's memory invariant makes, minus the legacy note on an absent
    depth (it reads as full, and nothing can change an append-only file)."""
    return [
        p
        for p in check_report(report, stored_names, root)
        if not p.startswith(LEGACY_PREFIX)
    ]


# --- the frontmatter, read as the contract writes it ---------------------------------


# --- the contract's checks, as the memory invariant applies them ---------------------


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


# --- a benchmark, read as its manifest carries it -------------------------------------


def strip_comment(text: str) -> str:
    """The line without its YAML end-of-line comment - a ``#`` opening
    outside quotes, at the start or after a space."""
    quote = None
    for index, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index]
    return text


def read_manifest(text: str) -> dict:
    """The manifest's top-level values, plus the immediate ones of its
    ``profile`` mapping - the one nested block a recall column reads
    (``profile.executor``). Nothing deeper: the manifest's schema belongs
    to the authoring agent, not to the persistence (the benchmark
    reference), so this reads the few keys the listing prints and leaves
    the rest of the file unopened. Values go through the frontmatter's own
    reader, so a flow collection (``service: [a, b]``) is a list here too,
    never the string of its own brackets."""

    def value_of(raw: str) -> Any:
        value = strip_comment(raw).strip()
        # a block scalar (``>``, ``|``) is prose the listing never prints
        return None if not value or value[0] in "|>" else parse_value(value)

    top: dict = {}
    profile: dict = {}
    section: str | None = None
    indent: int | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = MANIFEST_LINE_RE.match(line)
        if match and not match.group(1):
            section, indent = match.group(2), None
            top[section] = value_of(match.group(3))
        elif match and section == "profile":
            width = len(match.group(1))
            if indent is None:
                indent = width
            if width == indent:
                profile[match.group(2)] = value_of(match.group(3))
    top["profile"] = profile
    return top


def read_benchmark(directory: Path) -> dict:
    """One stored benchmark: the directory name is its identity, the
    manifest carries the columns."""
    entry = {"name": directory.name, "kind": "benchmark"}
    path = directory / MANIFEST
    if not path.is_file():
        entry["missing"] = MANIFEST
        return entry
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        entry["unreadable"] = str(exc)
        return entry
    entry["manifest"] = read_manifest(text)
    return entry


def check_benchmark(entry: dict) -> list[str]:
    """What a stored benchmark lacks for this recall to read it: its
    identity, the field the scope matches on, and the field the listing
    orders on. Never more - the manifest's schema is the authoring
    agent's, and the persistence stores whatever shape it has (the
    benchmark reference states this carve-out)."""
    if "missing" in entry:
        return [f"no {entry['missing']} in the directory"]
    if "unreadable" in entry:
        return [f"unreadable {MANIFEST}: {entry['unreadable']}"]
    problems: list[str] = []
    manifest = entry["manifest"]
    declared = manifest.get("name")
    if declared is None or declared == "":
        problems.append("name absent")
    elif str(declared) != entry["name"]:
        problems.append(
            f"manifest name {str(declared)!r} differs from the directory name"
            f" {entry['name']!r}, which is the benchmark's identity"
        )
    if not as_list(manifest.get("service")):
        problems.append("service absent")
    written = manifest.get("authored")
    if written is not None and not DATE_RE.match(str(written)):
        # the listing orders on it as plain text: another shape mis-sorts
        problems.append(f"authored {str(written)!r} is not YYYY-MM-DD")
    return problems


def benchmark_matches(entry: dict, scope: dict) -> bool:
    """A benchmark the scope cannot rule out. A directory whose manifest
    this recall could not read, or that declares no service, is never
    ruled out: the listing is what says a name is taken, and a name it
    drops would read as free."""
    services = as_list(entry.get("manifest", {}).get("service"))
    if not services:
        return True
    return not scope["services"] or bool(set(scope["services"]) & set(services))


def benchmark_line(entry: dict) -> str:
    """Every directory read prints a line - ``-`` in each column its
    manifest could not fill, its problems on stderr beside it."""
    manifest = entry.get("manifest", {})
    return "\t".join(
        [
            entry["name"],
            cell(manifest.get("service")),
            cell(manifest.get("test_type")),
            cell(manifest.get("profile", {}).get("executor")),
            cell(manifest.get("authored")),
        ]
    )


def authored(entry: dict) -> str:
    """The ordering key: the manifest's ``authored`` as plain text (the
    contract's YYYY-MM-DD sorts chronologically), empty when absent so it
    sorts last under the newest-first order."""
    value = entry.get("manifest", {}).get("authored")
    return "" if value is None else str(value)


def recall_benchmarks(root: Path, scope: dict) -> tuple[list[str], list[str]]:
    """The stdout lines and the stderr lines, for the benchmark store.

    A benchmark is living source in a directory, not a dated report file:
    the whole list is the answer (the set that already exists for the
    service), and the name column answers the second step - which stored
    artifact an update rewrites. So every directory read prints a line,
    dashes included: a name the listing drops would read as free."""
    store = root / STORES["benchmark"]
    children = sorted(store.iterdir()) if store.is_dir() else []
    err = [
        f"not a benchmark directory, ignored: {child.name}"
        for child in children
        if not child.is_dir()
    ]
    directories = [child for child in children if child.is_dir()]
    if not directories:
        return [], err + [f"no benchmark under {STORES['benchmark']}/ - a first run"]
    entries = [read_benchmark(d) for d in directories]
    entries.sort(key=lambda e: e["name"])
    entries.sort(key=authored, reverse=True)
    problems = {e["name"]: check_benchmark(e) for e in entries}
    matched = [e for e in entries if benchmark_matches(e, scope)]
    matched_names = {e["name"] for e in matched}
    out = []
    for entry in matched:
        out.append(benchmark_line(entry))
        err.extend(f"{entry['name']}: {p}" for p in problems[entry["name"]])
    for entry in entries:
        if entry["name"] not in matched_names:
            err.extend(
                f"not matched, flagged: {entry['name']}: {p}"
                for p in problems[entry["name"]]
            )
    # what exists is told when the *scope* selected nothing - never gated on
    # the output, which a defective directory joins whatever the scope is
    selected = [e for e in matched if as_list(e.get("manifest", {}).get("service"))]
    if not selected:
        readable = [e for e in entries if "manifest" in e]
        services = sorted(
            {s for e in readable for s in as_list(e["manifest"].get("service"))}
        )
        types = sorted(
            {
                str(e["manifest"]["test_type"])
                for e in readable
                if e["manifest"].get("test_type")
            }
        )
        err.append(
            f"no stored benchmark matches {describe(scope)}; stored: "
            f"services: {', '.join(services) or 'none'}; "
            f"test types: {', '.join(types) or 'none'}"
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
    if args.kind != "instrumentation" and args.project:
        parser.error("--project applies to instrumentation reports only")
    if args.kind == "benchmark" and (args.stack or args.env or args.mode or args.depth):
        parser.error(
            "--stack, --env, --mode and --depth apply to the report kinds only;"
            " a benchmark is recalled by --service and by name"
        )
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
    if args.kind == "benchmark":
        out, err = recall_benchmarks(root, scope)
    else:
        out, err = recall(root, args.kind, scope)
    if out:
        sys.stdout.write("\n".join(out) + "\n")
    if err:
        print("\n".join(err), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
