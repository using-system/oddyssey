#!/usr/bin/env python3
"""Answer, in one call, everything a mission's preflight reads off the machine.

A preflight asks the same questions every time: which CLIs are installed,
what is running, what the repository's state is, what the memory already
holds, and - when a stored benchmark is named - what its manifest targets.
None of it takes judgment, and none of it needs a turn each. This gathers
all of it concurrently and prints one block.

It deliberately does NOT resolve the stack or read the backend's
configuration: those come from the MCP tools and the backend's own
reference, which is the part of the preflight that is not mechanical.

    preflight.py
    preflight.py --benchmark .odd/benchmarks/<name> --containers llmbench
    preflight.py --json

Exit 0 always: an absent CLI or a missing directory is an answer, not a
failure - the caller decides what to do about it.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

CLIS = {
    "gcx": ["gcx", "version"],
    "k6": ["k6", "version"],
    "docker": ["docker", "--version"],
}
ODD_STORES = (
    ".odd/observe-run-reports",
    ".odd/otel-instrumentation-reports",
    ".odd/benchmarks",
    ".odd/observability-stacks",
)


def run(args: list[str], cwd: Path | None = None, timeout: int = 20) -> str:
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return p.stdout.strip()


def cli(name: str) -> dict:
    """Present or absent, and the version string when present."""
    if shutil.which(name) is None:
        return {"present": False}
    first = (run(CLIS[name]) or "").splitlines()
    return {"present": True, "version": first[0].strip() if first else ""}


def containers(name_filter: str | None) -> list[dict]:
    if shutil.which("docker") is None:
        return []
    args = ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"]
    if name_filter:
        args += ["--filter", f"name={name_filter}"]
    rows = []
    for line in (run(args) or "").splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append({"name": parts[0], "status": parts[1], "image": parts[2]})
    return rows


def porcelain_path(line: str) -> str:
    """The path a `git status --porcelain` entry is about.

    A rename arrives as `old -> new`: the caller judges an entry by
    whether that path can change runtime behavior, so a rename reported
    by its source reads as documentation when a file landed under the
    code.
    """
    path = line[2:].lstrip()
    if " -> " in path:
        return path.split(" -> ", 1)[1]
    return path


def repo(root: Path) -> dict:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    head = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
    dirty = run(["git", "status", "--porcelain"], cwd=root)
    paths = [porcelain_path(ln) for ln in dirty.splitlines()] if dirty else []
    return {
        "branch": branch or "unknown",
        "head": head or "unknown",
        "clean": not paths,
        "dirty_paths": len(paths),
        # The paths themselves, not only how many: a caller ruling on
        # whether code changed cannot do it from a count, and would run
        # `git status` again to get them.
        "dirty": paths[:40],
        "dirty_truncated": max(0, len(paths) - 40),
    }


def stores(root: Path) -> dict:
    out: dict[str, dict] = {}
    for rel in ODD_STORES:
        path = root / rel
        if not path.is_dir():
            out[rel] = {"exists": False, "count": 0, "newest": []}
            continue
        entries = sorted(
            (e for e in path.iterdir() if not e.name.startswith(".")),
            key=lambda e: e.name,
            reverse=True,
        )
        out[rel] = {
            "exists": True,
            "count": len(entries),
            "newest": [e.name for e in entries[:3]],
        }
    return out


def benchmark(directory: Path) -> dict:
    """What a replay needs off a stored benchmark, without a YAML dependency."""
    manifest = directory / "manifest.yaml"
    script = directory / "script.js"
    if not manifest.is_file():
        return {"exists": False, "path": str(directory)}
    text = manifest.read_text()

    def field(key: str) -> str | None:
        """Manifest scalars sit at any nesting depth: match the key, not a column."""
        m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
        if not m:
            return None
        return m.group(1).split("#")[0].strip().strip("'\"") or None

    envs = re.findall(r"^\s*(\w*base_url_env):\s*(\S+)", text, re.MULTILINE)
    defaults = re.findall(r"^\s*(\w*base_url_default):\s*(\S+)", text, re.MULTILINE)
    targets = {
        name: value.split("#")[0].strip()
        for (_, name), (_, value) in zip(envs, defaults)
    }
    return {
        "exists": True,
        "path": str(directory),
        "name": field("name"),
        "service": field("service"),
        "run_slug_env": field("run_slug_env"),
        "targets": targets,
        "script": script.is_file(),
    }


def render(report: dict) -> str:
    lines = [f"preflight at {report['now']}   repo {report['root']}"]
    tools = "  ".join(
        f"{n}={'yes' if v['present'] else 'ABSENT'}" for n, v in report["clis"].items()
    )
    lines.append(f"  clis       {tools}")
    for name, value in report["clis"].items():
        if value.get("version"):
            lines.append(f"             {name}: {value['version']}")
    r = report["repo"]
    state = "clean" if r["clean"] else f"dirty ({r['dirty_paths']} paths)"
    lines.append(f"  repo       branch {r['branch']}  head {r['head']}  {state}")
    for path in r.get("dirty", []):
        lines.append(f"             {path}")
    if r.get("dirty_truncated"):
        lines.append(f"             ... and {r['dirty_truncated']} more")
    if report["containers"]:
        lines.append("  containers")
        for c in report["containers"]:
            lines.append(f"             {c['name']}  {c['status']}")
    else:
        lines.append("  containers none running")
    lines.append("  memory")
    for rel, s in report["stores"].items():
        if not s["exists"]:
            lines.append(f"             {rel}: absent")
        else:
            newest = ", ".join(s["newest"]) if s["newest"] else "empty"
            lines.append(f"             {rel}: {s['count']}  newest: {newest}")
    b = report.get("benchmark")
    if b:
        if not b["exists"]:
            lines.append(f"  benchmark  NOT FOUND at {b['path']}")
        else:
            targets = "  ".join(f"{k}={v}" for k, v in b["targets"].items())
            lines.append(
                f"  benchmark  {b['name']}  service={b['service']}  "
                f"slug_env={b['run_slug_env']}  script={'yes' if b['script'] else 'MISSING'}"
            )
            if targets:
                lines.append(f"             targets    {targets}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--benchmark", help="a stored benchmark's directory")
    ap.add_argument("--containers", help="only containers whose name matches this")
    ap.add_argument("--root", default=".", help="repository root (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    with ThreadPoolExecutor(max_workers=8) as pool:
        f_clis = {name: pool.submit(cli, name) for name in CLIS}
        f_containers = pool.submit(containers, args.containers)
        f_repo = pool.submit(repo, root)
        f_stores = pool.submit(stores, root)
        f_bench = (
            pool.submit(benchmark, (root / args.benchmark).resolve())
            if args.benchmark
            else None
        )
        report = {
            "now": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "root": str(root),
            "clis": {name: f.result() for name, f in f_clis.items()},
            "containers": f_containers.result(),
            "repo": f_repo.result(),
            "stores": f_stores.result(),
        }
    if f_bench is not None:
        report["benchmark"] = f_bench.result()

    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
