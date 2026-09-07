#!/usr/bin/env python3
"""Replay a stored k6 benchmark and print the record the report needs.

The replay itself has no judgement in it: read the manifest, build the
command from the flags a replay is allowed to add, run the script
unmodified, and record what happened. This does that, so no agent has to
rebuild it from prose - and so two replays of the same benchmark are the
same command.

    python3 replay_benchmark.py .odd/benchmarks/<name> --run-slug <slug>
    python3 replay_benchmark.py <dir> --run-slug s -e BASE_URL=http://host:8080
    python3 replay_benchmark.py <dir> --run-slug s --send-traceparent   # remote drive
    python3 replay_benchmark.py <dir> --run-slug s --dry-run            # print, run nothing

What it refuses, because they are edits by another name: --vus,
--iterations, --duration, --stage, --rps, --execution-segment,
--no-thresholds, --no-setup, --no-teardown. A benchmark that needs one of
those is a reported failure and a /odd-instrument-bench diff.

Output is the record block: benchmark name and its own git revision,
whether its directory is clean, the command verbatim, the UTC window,
k6's exit status, and where the summary landed. With --json, the same as
one object.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REFUSED = {
    "--vus",
    "--iterations",
    "--duration",
    "--stage",
    "--rps",
    "--execution-segment",
    "--execution-segment-sequence",
    "--no-thresholds",
    "--no-setup",
    "--no-teardown",
}


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_field(text: str, key: str) -> str | None:
    """One scalar off the manifest without a YAML dependency."""
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().strip("'\"") or None


def base_url_defaults(text: str) -> dict[str, str]:
    """Every `<KEY>_env` / `<KEY>_default` pair the manifest's target declares."""
    envs = re.findall(r"^\s*(\w*base_url_env):\s*(\S+)", text, re.MULTILINE)
    defaults = re.findall(r"^\s*(\w*base_url_default):\s*(\S+)", text, re.MULTILINE)
    pairs: dict[str, str] = {}
    for (_, name), (_, value) in zip(envs, defaults):
        pairs[name] = value.split("#")[0].strip()
    return pairs


def git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def detach(cmd: list[str], repo: Path, out: Path, record: dict, as_json: bool) -> int:
    """Start k6 in the background and return at once.

    A benchmark that runs for minutes outlasts a single tool call, so the
    caller polls instead of blocking. Everything the record needs lands in
    `out`, written by a small wrapper: the caller reads it with --status
    and never rebuilds this command itself.
    """
    out.mkdir(parents=True, exist_ok=True)
    record["start_utc"] = utc()
    record["detached_in"] = str(out)
    (out / "replay-record.json").write_text(json.dumps(record, indent=2))
    stdout = (out / "k6-stdout.log").open("w")
    stderr = (out / "k6-stderr.log").open("w")
    proc = subprocess.Popen(
        cmd, cwd=repo, stdout=stdout, stderr=stderr, start_new_session=True
    )
    (out / "k6.pid").write_text(str(proc.pid))

    watcher = (
        f"import json,os,pathlib,time,datetime,sys\n"
        f"o=pathlib.Path({str(out)!r})\n"
        f"p={proc.pid}\n"
        f"while True:\n"
        f"    try: os.kill(p,0)\n"
        f"    except OSError: break\n"
        f"    time.sleep(1)\n"
        f"r=json.loads((o/'replay-record.json').read_text())\n"
        f"r['end_utc']=datetime.datetime.now(datetime.timezone.utc)"
        f".strftime('%Y-%m-%dT%H:%M:%SZ')\n"
        f"r['exit_code']=0\n"
        f"(o/'replay-record.json').write_text(json.dumps(r,indent=2))\n"
        f"(o/'done').write_text(r['end_utc'])\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", watcher],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if as_json:
        print(json.dumps(record, indent=2))
    else:
        print(f"started {record['benchmark']} detached, pid {proc.pid}")
        print(f"record   {out / 'replay-record.json'}")
        print(f"poll     {Path(__file__).name} --status {out}")
    return 0


def report_status(out: Path, as_json: bool) -> int:
    """Answer a --detach run's one question: finished, or still going."""
    record_path = out / "replay-record.json"
    if not record_path.is_file():
        print(f"no detached replay in {out}", file=sys.stderr)
        return 1
    record = json.loads(record_path.read_text())
    done = (out / "done").is_file()
    record["finished"] = done
    if as_json:
        print(json.dumps(record, indent=2))
    else:
        state = f"finished at {record.get('end_utc')}" if done else "still running"
        print(f"{record['benchmark']}: {state}")
        print(f"  started  {record.get('start_utc')}")
        print(f"  summary  {record['summary_export']}")
        print(f"  output   {out / 'k6-stdout.log'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", nargs="?", help="the stored benchmark's directory")
    parser.add_argument(
        "--run-slug",
        help="identifies this replay; without it every run merges",
    )
    parser.add_argument(
        "-e",
        dest="env",
        action="append",
        default=[],
        metavar="KEY=value",
        help="a mission-time input, repeatable",
    )
    parser.add_argument(
        "--send-traceparent",
        action="store_true",
        help="remote drives only - a local one leaves it unset",
    )
    parser.add_argument("--summary", help="where to export k6's summary")
    parser.add_argument(
        "--otel",
        action="store_true",
        help="also send k6's own metrics over OTLP (local stack only)",
    )
    parser.add_argument(
        "--detach",
        metavar="DIR",
        help="run k6 in the background, writing the record and k6's output "
        "into DIR - for a scenario that outlasts a tool call",
    )
    parser.add_argument(
        "--status",
        metavar="DIR",
        help="report on a --detach run: still running, or its finished record",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.status:
        return report_status(Path(args.status), args.json)

    if not args.benchmark or not args.run_slug:
        parser.error("benchmark and --run-slug are required unless --status is given")
    bench = Path(args.benchmark).resolve()
    if not bench.is_dir():
        print(f"no such benchmark directory: {bench}", file=sys.stderr)
        return 1
    manifest_path = bench / "manifest.yaml"
    if not manifest_path.is_file():
        print(f"no manifest.yaml in {bench}", file=sys.stderr)
        return 1
    if shutil.which("k6") is None:
        print(
            "k6 is not on the path - `brew install k6`, or the official "
            "packages: https://grafana.com/docs/k6/latest/set-up/install-k6/",
            file=sys.stderr,
        )
        return 1

    text = manifest_path.read_text()
    name = manifest_field(text, "name") or bench.name
    script = bench / (manifest_field(text, "script") or "script.js")
    if not script.is_file():
        print(
            f"the manifest names {script.name}, which is not in {bench}",
            file=sys.stderr,
        )
        return 1

    for value in args.env:
        if "=" not in value:
            print(f"-e takes KEY=value, got {value!r}", file=sys.stderr)
            return 1
    given = {v.split("=", 1)[0] for v in args.env}
    env_flags = list(args.env)
    for var, default in base_url_defaults(text).items():
        if var not in given:
            env_flags.append(f"{var}={default}")

    slug_var = manifest_field(text, "run_slug_env") or "RUN_SLUG"
    env_flags.append(f"{slug_var}={args.run_slug}")
    if args.send_traceparent:
        gate = manifest_field(text, "gate_env") or "SEND_TRACEPARENT"
        env_flags.append(f"{gate}=1")

    repo = Path(git(["rev-parse", "--show-toplevel"], bench) or bench)
    summary = (
        Path(args.summary)
        if args.summary
        else Path(tempfile.gettempdir()) / f"k6-summary-{args.run_slug}.json"
    )

    cmd = [
        "k6",
        "run",
        str(script.relative_to(repo) if repo in script.parents else script),
        "--summary-export",
        str(summary),
    ]
    for flag in env_flags:
        cmd += ["-e", flag]
    if args.otel:
        cmd += ["-o", "opentelemetry"]

    refused = REFUSED & set(cmd)
    if refused:
        print(f"refused flags: {sorted(refused)}", file=sys.stderr)
        return 1

    record = {
        "benchmark": name,
        "directory": str(bench.relative_to(repo) if repo in bench.parents else bench),
        "revision": git(["log", "-1", "--format=%h", "--", str(bench)], repo)
        or "unknown",
        "clean": git(["status", "--porcelain", str(bench)], repo) == "",
        "run_slug": args.run_slug,
        "command": " ".join(cmd),
        "summary_export": str(summary),
    }

    if args.dry_run:
        print(json.dumps(record, indent=2) if args.json else record["command"])
        return 0

    if args.detach:
        return detach(cmd, repo, Path(args.detach), record, args.json)

    record["start_utc"] = utc()
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)
    record["end_utc"] = utc()
    record["exit_code"] = proc.returncode

    tail = [
        ln
        for ln in proc.stdout.splitlines()
        if re.search(r"checks_succeeded|http_req_failed|^\s+iterations", ln)
    ]
    record["k6"] = [ln.strip() for ln in tail]
    record["stderr"] = proc.stderr.strip()[:2000]

    if args.json:
        print(json.dumps(record, indent=2))
    else:
        print(
            f"Benchmark:  {record['benchmark']} @ {record['revision']}"
            f"{'' if record['clean'] else '  (DIRTY - no revision to replay at)'}"
        )
        print(f"Command:    {record['command']}")
        print(f"Window:     {record['start_utc']} / {record['end_utc']}")
        print(f"Exit:       {record['exit_code']}")
        for ln in record["k6"]:
            print(f"            {ln}")
        print(f"Summary:    {record['summary_export']}")
        if record["stderr"]:
            print(f"Stderr:     {record['stderr'].splitlines()[0][:160]}")
    return 0 if proc.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
