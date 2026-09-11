#!/usr/bin/env python3
"""Run a study's samples in order, each on its lab branch, and journal them.

    python3 run_samples.py --lab <clone> --fake-home <dir> --out <study dir> \\
      --cli opencode --model google/gemini-3.7-flash --phase whole \\
      base1=lab-main:mission.txt after1=lab-after:mission.txt base2=lab-main:mission.txt

One sample is `<tag>=<lab branch>:<mission file>`. For each, in order:
the lab is put on the branch and cleared of
what the previous run left (a report branch, a report commit after the
tip recorded at the chain's start, an untracked report, a rewritten
opencode.json), `--scratch` is cleared when given; the fake user scope is
synced from the branch's deploy (`--scope` pairs; opencode's are the
default) and checked identical; `--before` runs; the measurement is
launched (`--alongside` starts right after it and is waited for); the
analysis runs; `--after` runs; one `SAMPLE DONE <tag> <wall>` or
`SAMPLE FAILED <tag> (<why>)` line goes to `<out>/samples.log`, then
`SAMPLE CHAIN DONE <n> of <m>` (or `SAMPLE CHAIN ABORTED at <tag>: <why>` when
a sample is refused before its launch) - the lines a monitor watches. The hooks
receive SAMPLE_TAG, SAMPLE_BRANCH, SAMPLE_OUT, SAMPLE_MISSION, LAB and
FAKE_HOME in their environment. Exit 0 when every sample was measured, 1
otherwise - a refused sample never launches.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# what the opencode deploy in the lab writes, and where the fake user scope
# expects it (launch-llms-benchmark step 3 states the scopes per CLI); the
# other CLIs' scopes are passed as --scope <lab path>:<fake-home path>
DEFAULT_SCOPES = {
    "opencode": [
        (".agents/skills", ".claude/skills"),
        (".opencode/agents", ".claude/agents"),
    ],
}
CLIS = ("opencode", "claude", "copilot")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(lab: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=lab,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} in {lab}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def parse_sample(spec: str) -> tuple[str, str, Path]:
    if "=" not in spec or ":" not in spec.split("=", 1)[1]:
        raise SystemExit(f"a sample is tag=branch:mission - got {spec!r}")
    tag, rest = spec.split("=", 1)
    branch, mission = rest.split(":", 1)
    if not tag or not branch or not mission:
        raise SystemExit(f"a sample is tag=branch:mission - got {spec!r}")
    return tag, branch, Path(mission)


def journal(out: Path, line: str) -> None:
    with (out / "samples.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{utc()} {line}\n")
    print(line, flush=True)


def clear_lab(lab: Path, branch: str, tip: str, out: Path) -> None:
    """The branch under measurement at the tip recorded when the chain
    started, with nothing a run left after it."""
    git(lab, "checkout", "-q", "--", "opencode.json", check=False)
    git(lab, "checkout", "-q", branch)
    cleared = []
    while git(lab, "rev-parse", "HEAD") != tip and git(
        lab, "log", "-1", "--format=%s"
    ).startswith("docs(odd)"):
        git(lab, "reset", "-q", "--hard", "HEAD~1")
        cleared.append("a report commit")
    for name in git(lab, "branch", "--format=%(refname:short)").splitlines():
        if name.startswith("docs/odd-") and "-report-" in name:
            git(lab, "branch", "-D", name)
            cleared.append(f"branch {name}")
    untracked = git(lab, "ls-files", "--others", "--exclude-standard", ".odd/")
    for rel in untracked.splitlines():
        (lab / rel).unlink(missing_ok=True)
        cleared.append(rel)
    if git(lab, "status", "--porcelain"):
        raise SystemExit(
            f"{lab} is not clean on {branch}:\n{git(lab, 'status', '--porcelain')}"
        )
    if cleared:
        journal(out, f"cleared before {branch}: {', '.join(cleared)}")


def sync_scope(lab: Path, home: Path, scopes: list[tuple[str, str]]) -> None:
    """The fake user scope carries the branch's deploy, and nothing else."""
    for src, dst in scopes:
        source, target = lab / src, home / dst
        if not source.is_dir():
            raise SystemExit(
                f"{source} is not deployed in the lab: the branch's deploy is "
                "incomplete, or the scope pair is wrong"
            )
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        diff = subprocess.run(
            ["diff", "-rq", "-x", "__pycache__", str(source), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if diff.returncode != 0:
            raise SystemExit(
                f"the fake user scope differs from {source}:\n{diff.stdout}"
            )


def run_hook(
    command: str | None, env: dict, out: Path, tag: str, name: str
) -> subprocess.Popen | None:
    if not command:
        return None
    log = (out / f"{tag}.{name}.log").open("a", encoding="utf-8")
    return subprocess.Popen(
        command, shell=True, env=env, stdout=log, stderr=subprocess.STDOUT
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("samples", nargs="+", metavar="tag=branch:mission")
    ap.add_argument("--lab", required=True, help="the lab clone the runs launch in")
    ap.add_argument("--fake-home", required=True, help="the HOME the runs see")
    ap.add_argument("--out", required=True, help="the study directory")
    ap.add_argument("--cli", default="opencode", choices=CLIS)
    ap.add_argument(
        "--scope",
        action="append",
        metavar="LAB_PATH:HOME_PATH",
        help="a deployed directory to sync into the fake home, both paths relative "
        "(repeatable; the opencode pairs are the default, the other CLIs need theirs stated)",
    )
    ap.add_argument(
        "--scratch",
        metavar="DIR",
        help="the CLI's scratch directory to clear before each sample (none by default)",
    )
    ap.add_argument("--model", default="google/gemini-3.7-flash")
    ap.add_argument(
        "--phase",
        default="whole",
        choices=["preflight", "drive", "observation", "whole"],
    )
    ap.add_argument(
        "--end-pattern",
        help="passed to the measurement, for a phase with its own marker",
    )
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--timeout", type=int, default=2700)
    ap.add_argument(
        "--before",
        help="a command run before each launch (the demo stack, a traffic burst)",
    )
    ap.add_argument(
        "--alongside",
        help="a command started right after each launch and waited for (a driver)",
    )
    ap.add_argument("--after", help="a command run after each analysis")
    ap.add_argument(
        "--pause", type=float, default=10.0, help="seconds between two samples"
    )
    ap.add_argument("--measure-script", default=str(HERE / "measure_phase.py"))
    ap.add_argument("--analyze-script", default=str(HERE / "analyze_run.py"))
    args = ap.parse_args()

    lab = Path(args.lab).resolve()
    home = Path(args.fake_home).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    samples = [parse_sample(s) for s in args.samples]
    for _, _, mission in samples:
        if not mission.is_file():
            raise SystemExit(f"no such mission file: {mission}")
    scopes = list(DEFAULT_SCOPES.get(args.cli, []))
    for pair in args.scope or []:
        if ":" not in pair:
            raise SystemExit(f"--scope takes <lab path>:<fake-home path>, got {pair!r}")
        src, dst = pair.split(":", 1)
        for part in (src, dst):
            if not part or Path(part).is_absolute() or ".." in Path(part).parts:
                raise SystemExit(
                    f"--scope paths are relative to the lab and to the fake home, "
                    f"never absolute, never through ..: got {pair!r}"
                )
        scopes.append((src, dst))
    if not scopes:
        raise SystemExit(f"--cli {args.cli} needs its --scope pairs stated")
    branches = git(lab, "branch", "--format=%(refname:short)").splitlines()
    tips: dict[str, str] = {}
    for _, branch, _ in samples:
        if branch not in branches:
            raise SystemExit(f"no such lab branch: {branch}")
        tips[branch] = git(lab, "rev-parse", branch)
    done = 0
    for index, (tag, branch, mission) in enumerate(samples):
        if index:
            time.sleep(args.pause)
        try:
            clear_lab(lab, branch, tips[branch], out)
            sync_scope(lab, home, scopes)
        except SystemExit as why:
            journal(out, f"SAMPLE CHAIN ABORTED at {tag}: {why}")
            raise
        if args.scratch and Path(args.scratch).is_dir():
            shutil.rmtree(args.scratch, ignore_errors=True)
        env = {
            **os.environ,
            "SAMPLE_TAG": tag,
            "SAMPLE_BRANCH": branch,
            "SAMPLE_OUT": str(out),
            "SAMPLE_MISSION": str(mission.resolve()),
            "LAB": str(lab),
            "FAKE_HOME": str(home),
        }
        before = run_hook(args.before, env, out, tag, "before")
        if before is not None and before.wait() != 0:
            journal(out, f"SAMPLE FAILED {tag} (before hook exit {before.returncode})")
            continue
        (out / f"{tag}.start.txt").write_text(utc() + "\n")
        started = time.monotonic()
        measure_cmd = [
            sys.executable,
            args.measure_script,
            "--cli",
            args.cli,
            "--model",
            args.model,
            "--tag",
            tag,
            "--phase",
            args.phase,
            "--effort",
            args.effort,
            "--timeout",
            str(args.timeout),
            "--prompt-file",
            str(mission.resolve()),
            "--out",
            str(out),
        ]
        if args.end_pattern:
            measure_cmd += ["--end-pattern", args.end_pattern]
        with (out / f"{tag}.measure.log").open("w", encoding="utf-8") as log:
            measure = subprocess.Popen(
                measure_cmd,
                cwd=lab,
                env={**env, "HOME": str(home)},
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            alongside = run_hook(args.alongside, env, out, tag, "alongside")
            code = measure.wait()
            if alongside is not None:
                alongside.wait()
        wall = int(time.monotonic() - started)
        (out / f"{tag}.branch.txt").write_text(
            f"{git(lab, 'branch', '--show-current')}\n{git(lab, 'log', '-1', '--oneline')}\n"
        )
        record = out / f"{tag}.record.json"
        if code != 0 or not record.is_file():
            why = (
                f"measure exit {code}" if code != 0 else "measure exit 0 but no record"
            )
            journal(out, f"SAMPLE FAILED {tag} ({why})")
            after = run_hook(args.after, env, out, tag, "after")
            if after is not None:
                after.wait()
            continue
        with (out / f"{tag}.analysis.txt").open("w", encoding="utf-8") as log:
            subprocess.run(
                [sys.executable, args.analyze_script, "--record", str(record)],
                env={**env, "HOME": str(home)},
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        after = run_hook(args.after, env, out, tag, "after")
        if after is not None:
            after.wait()
        done += 1
        journal(out, f"SAMPLE DONE {tag} {wall // 60}m{wall % 60:02d}s on {branch}")
    git(lab, "checkout", "-q", "--", "opencode.json", check=False)
    journal(out, f"SAMPLE CHAIN DONE {done} of {len(samples)}")
    return 0 if done == len(samples) else 1


if __name__ == "__main__":
    sys.exit(main())
