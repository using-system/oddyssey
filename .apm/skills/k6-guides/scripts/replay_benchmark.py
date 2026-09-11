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
    python3 replay_benchmark.py <dir> --run-slug s --detach <out>       # start, return at once
    python3 replay_benchmark.py --status <out> --wait 20m               # block until finished
    python3 replay_benchmark.py --stages <dir> --first-row <UTC>        # the record's stage lines

What it refuses, because they are edits by another name: --vus,
--iterations, --duration, --stage, --rps, --execution-segment,
--no-thresholds, --no-setup, --no-teardown. A benchmark that needs one of
those is a reported failure and a /odd-instrument-bench diff.

Output is the record block: benchmark name and its own git revision,
whether its directory is clean, the command verbatim, the UTC window,
k6's exit status, and where the summary landed. With --json, the same as
one object.

--stages lays the manifest's stage offsets out in UTC from the run's first
request row - the arithmetic every record redoes - and prints the record's
`Stages (UTC):` and `Warmup:` lines, t0 (the first quoted stage's start),
and a ramp's segments with the offered rate at each midpoint.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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
    """One scalar off the manifest without a YAML dependency.

    A manifest nests: `run_slug_env` sits under an identity block in
    every stored one, so anchoring at column 0 finds none of them and
    the replay falls back to a default variable name without saying so.
    """
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).split("#")[0].strip().strip("'\"") or None


def base_url_defaults(text: str) -> dict[str, str]:
    """Every `<KEY>_env` / `<KEY>_default` pair the manifest's target declares."""
    envs = re.findall(r"^\s*(\w*base_url_env):\s*(\S+)", text, re.MULTILINE)
    defaults = re.findall(r"^\s*(\w*base_url_default):\s*(\S+)", text, re.MULTILINE)
    pairs: dict[str, str] = {}
    for (_, name), (_, value) in zip(envs, defaults):
        pairs[name] = value.split("#")[0].strip()
    return pairs


def otel_env() -> dict:
    """What k6's OTLP output needs to reach the local stack.

    The exporter defaults to requiring TLS, which this stack does not
    serve, and its endpoint is a configured port rather than a fixed
    one - so `-o opentelemetry` on its own connects to nothing and the
    cross-confirmation series silently never lands.
    """
    env = {"K6_OTEL_GRPC_EXPORTER_INSECURE": "true"}
    try:
        stored = json.loads(
            (Path.home() / ".oddyssey" / "config.json").read_text()
        ).get("local", {})
    except (OSError, ValueError):
        stored = {}
    port = stored.get("otlp_grpc_port")
    if isinstance(port, int) and 0 < port < 65536 and port != 4317:
        env["K6_OTEL_GRPC_EXPORTER_ENDPOINT"] = f"localhost:{port}"
    return env


def summarise(stdout: str, stderr: str) -> dict:
    """The evidence lines a record carries, whichever form produced it.

    The foreground and detached paths must yield the same shapes for the
    same keys, or an agent reading --json gets a string here and a list
    there for `stderr`.
    """
    lines = [
        ln.strip()
        for ln in stdout.splitlines()
        if re.search(r"checks_succeeded|http_req_failed|^\s+iterations", ln)
    ]
    return {"k6": lines, "stderr": stderr.strip()[:2000]}


def git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def detach(
    cmd: list[str],
    repo: Path,
    out: Path,
    record: dict,
    as_json: bool,
    child_env: dict | None = None,
) -> int:
    """Start the replay in the background and return at once.

    A benchmark that runs for minutes outlasts a single tool call, so the
    caller waits with --status --wait instead of blocking here. k6 runs as the child of a detached
    wrapper, which is what lets the finished record carry k6's **real**
    exit status - a threshold breach is a 99, and a run that reported it
    as a pass would be worse than no record at all.
    """
    out.mkdir(parents=True, exist_ok=True)
    # A directory reused by a retry, or by a verify replaying the
    # baseline's slug, still holds the previous run's outcome - and
    # --status would report it, confidently, one second after launch.
    for stale in ("done", "k6-exit.code", "k6-stdout.log", "k6-stderr.log"):
        (out / stale).unlink(missing_ok=True)
    record["start_utc"] = utc()
    record["detached_in"] = str(out)
    (out / "replay-record.json").write_text(json.dumps(record, indent=2))

    runner = out / "runner.py"
    runner.write_text(
        "import json, subprocess, pathlib\n"
        f"o = pathlib.Path({str(out)!r})\n"
        f"cmd = {cmd!r}\n"
        "import os\n"
        f"env = {{**os.environ, **{dict(child_env or {})!r}}}\n"
        "so = (o / 'k6-stdout.log').open('w')\n"
        "se = (o / 'k6-stderr.log').open('w')\n"
        f"p = subprocess.run(cmd, cwd={str(repo)!r}, env=env, stdout=so,"
        " stderr=se, check=False)\n"
        "so.close(); se.close()\n"
        "(o / 'k6-exit.code').write_text(str(p.returncode))\n"
        "(o / 'done').write_text('1')\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(runner)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    (out / "runner.pid").write_text(str(proc.pid))

    if as_json:
        print(json.dumps(record, indent=2))
    else:
        print(f"started {record['benchmark']} detached, pid {proc.pid}")
        print(f"record   {out / 'replay-record.json'}")
        print(f"wait     {Path(__file__).name} --status {out} --wait <duration>")
    return 0


def parse_wait(value: str) -> int:
    """A bounded wait as seconds: 20m, 300s, 1h - a bare number is seconds."""
    m = re.fullmatch(r"(\d+)([smh]?)", value.strip())
    if not m:
        raise SystemExit(f"--wait takes <number>[s|m|h], got {value!r}")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


def runner_alive(out: Path) -> bool:
    """Whether the detached runner recorded in runner.pid still exists."""
    try:
        pid = int((out / "runner.pid").read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def report_status(out: Path, as_json: bool, wait: str | None = None) -> int:
    """Answer a --detach run's one question: finished, or still going.

    With --wait, block until the run finishes or the bound passes - the
    wait the contracts describe, shipped instead of authored: exit 0 when
    finished, 3 when still running at the bound, the status printed either
    way.
    """
    record_path = out / "replay-record.json"
    if not record_path.is_file():
        print(f"no detached replay in {out}", file=sys.stderr)
        return 1
    timed_out = False
    if wait is not None:
        limit = parse_wait(wait)
        started = time.monotonic()
        while not (out / "done").is_file():
            if not runner_alive(out) and not (out / "done").is_file():
                print(
                    f"the detached run in {out} is gone without a record - its "
                    "process was killed or the machine restarted; drive again",
                    file=sys.stderr,
                )
                return 1
            if time.monotonic() - started >= limit:
                timed_out = True
                break
            time.sleep(min(5.0, max(limit, 1)))
    record = json.loads(record_path.read_text())
    done = (out / "done").is_file()
    if done and "exit_code" not in record:
        record["end_utc"] = datetime.datetime.fromtimestamp(
            (out / "done").stat().st_mtime, datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        record["exit_code"] = int((out / "k6-exit.code").read_text().strip())
        record.update(
            summarise(
                (out / "k6-stdout.log").read_text(),
                (out / "k6-stderr.log").read_text(),
            )
        )
        record_path.write_text(json.dumps(record, indent=2))
    record["finished"] = done
    if as_json:
        print(json.dumps(record, indent=2))
    else:
        state = f"finished at {record.get('end_utc')}" if done else "still running"
        if done:
            state += f", exit {record.get('exit_code')}"
        print(f"{record['benchmark']}: {state}")
        print(f"  started  {record.get('start_utc')}")
        print(f"  summary  {record['summary_export']}")
        print(f"  output   {out / 'k6-stdout.log'}")
    if timed_out:
        print(
            f"still running after --wait {wait}: the wait is bounded on purpose - "
            "run --status --wait again, or raise the bound",
            file=sys.stderr,
        )
        return 3
    return 0


# --- the stage boundaries a record needs ---------------------------------------


def parse_offset(value: str) -> int:
    """A k6 duration off the manifest as seconds: 30s, 2m, 1h, 1h30m, 0s."""
    text = str(value).strip().strip("'\"")
    total = 0
    matched = False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([smh])", text):
        total += float(num) * {"s": 1, "m": 60, "h": 3600}[unit]
        matched = True
    if not matched:
        raise ValueError(f"not a k6 duration: {value!r}")
    return int(total)


def _number(value) -> float | None:
    """The number a target carries, or None when it is text (`1 per 15s`)."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    return float(text) if re.fullmatch(r"-?\d+(?:\.\d+)?", text) else None


def _leading_number(value) -> float | None:
    text = str(value).strip()
    m = re.match(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def _scalar(text: str):
    text = text.strip()
    if text and text[0] not in "\"'":
        text = text.split(" #")[0].strip()
    text = text.strip("'\"")
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _flow_mapping(text: str) -> dict:
    """`{ name: steady, from: 0s, to: 2m, target: 5, quote: true }`."""
    inner = text.strip()[1:-1]
    out: dict = {}
    for part in re.split(r",(?![^\[]*\])", inner):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = _scalar(v)
    return out


def parse_block(lines: list[str]) -> dict | list:
    """The subset of YAML a manifest's profile uses: nested mappings by
    indentation, lists of mappings (block or flow style), scalars, block
    scalars folded to text. Enough to read the stages; a full parser is a
    dependency the replay does not carry."""
    items: list[tuple[int, str]] = []
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        items.append((len(raw) - len(raw.lstrip()), raw.strip()))
    return _parse(items, 0, len(items))[0]


def _parse(items: list[tuple[int, str]], start: int, end: int):
    if start >= end:
        return {}, start
    base = items[start][0]
    if items[start][1].startswith("- "):
        out_list: list = []
        i = start
        while i < end and items[i][0] == base and items[i][1].startswith("- "):
            body = items[i][1][2:].strip()
            j = i + 1
            while j < end and items[j][0] > base:
                j += 1
            if body.startswith("{"):
                out_list.append(_flow_mapping(body))
            elif ":" in body:
                first = (base + 2, body)
                entry, _ = _parse([first, *items[i + 1 : j]], 0, j - i)
                out_list.append(entry)
            else:
                out_list.append(_scalar(body))
            i = j
        return out_list, i
    out: dict = {}
    i = start
    while i < end and items[i][0] == base:
        line = items[i][1]
        if ":" not in line:
            i += 1
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith("#"):
            value = ""  # a key whose line carries only a comment
        j = i + 1
        while j < end and items[j][0] > base:
            j += 1
        if value in ("", ">", ">-", "|", "|-") or value.startswith(("> ", "| ")):
            if (
                value
                and j > i + 1
                and not items[i + 1][1].startswith("- ")
                and value[0] in ">|"
            ):
                out[key] = " ".join(t for _, t in items[i + 1 : j])
            elif j > i + 1:
                out[key], _ = _parse(items, i + 1, j)
            else:
                out[key] = None
        elif value.startswith("{"):
            out[key] = _flow_mapping(value)
        else:
            out[key] = _scalar(value)
        i = j
    return out, i


def manifest_profile(text: str) -> dict:
    """The manifest's `profile:` block, parsed."""
    lines = text.splitlines()
    start = next((k for k, ln in enumerate(lines) if ln.startswith("profile:")), None)
    if start is None:
        return {}
    end = next(
        (k for k in range(start + 1, len(lines)) if re.match(r"^[A-Za-z_]", lines[k])),
        len(lines),
    )
    parsed = parse_block(lines[start:end])
    return parsed.get("profile") or {} if isinstance(parsed, dict) else {}


def scenario_stages(profile: dict) -> list[tuple[str | None, dict, dict]]:
    """(scenario name, its block, one stage) per stage, in manifest order:
    a profile carries its stages at its top or under `scenarios`."""
    found = []
    for sc in profile.get("scenarios") or []:
        if isinstance(sc, dict):
            for st in sc.get("stages") or []:
                if isinstance(st, dict):
                    found.append(
                        (str(sc.get("scenario") or sc.get("name") or ""), sc, st)
                    )
    for st in profile.get("stages") or []:
        if isinstance(st, dict):
            found.append((None, profile, st))
    return found


def hhmm(ts: str) -> str:
    return ts[11:19]


def stage_layout(text: str, first_row: str, segment: str) -> dict:
    """Every stage in UTC from the first request row, the warmup (the
    unquoted stages before the first quoted one), t0, a ramp's segments."""
    profile = manifest_profile(text)
    found = scenario_stages(profile)
    if not found:
        raise ValueError("no stages under the manifest's profile")
    t_first = datetime.datetime.strptime(first_row, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc
    )
    seg_s = parse_offset(segment)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    stages: list[dict] = []
    segments: list[dict] = []
    previous: dict[str | None, float | None] = {}
    for scenario, block, st in found:
        frm, to = parse_offset(st.get("from", "0s")), parse_offset(st.get("to", "0s"))
        target = st.get("target")
        number = _number(target)
        start = previous.get(scenario)
        if start is None:
            start = _leading_number(block.get("start_vus", block.get("start_rate", "")))
            if start is None:
                start = number
        ramp = number is not None and start is not None and start != number
        entry = {
            "scenario": scenario,
            "name": str(st.get("name") or f"stage {len(stages) + 1}"),
            "from_s": frm,
            "to_s": to,
            "from": (t_first + datetime.timedelta(seconds=frm)).strftime(fmt),
            "to": (t_first + datetime.timedelta(seconds=to)).strftime(fmt),
            "target": target
            if number is None
            else (int(number) if number.is_integer() else number),
            "start_target": None
            if start is None
            else (int(start) if float(start).is_integer() else start),
            "quote": bool(st.get("quote", False)),
            "ramp": ramp,
        }
        stages.append(entry)
        if number is not None:
            previous[scenario] = number
        if ramp and to > frm:
            t = frm
            while t < to:
                u = min(t + seg_s, to)
                mid = (t + u) / 2
                rate = start + (number - start) * (mid - frm) / (to - frm)
                segments.append(
                    {
                        "scenario": scenario,
                        "stage": entry["name"],
                        "from": (t_first + datetime.timedelta(seconds=t)).strftime(fmt),
                        "to": (t_first + datetime.timedelta(seconds=u)).strftime(fmt),
                        "midpoint_rate": round(rate, 3),
                    }
                )
                t = u
    quoted = [s for s in stages if s["quote"]]
    t0 = min((s["from"] for s in quoted), default=None)
    first_quoted_s = min((s["from_s"] for s in quoted), default=None)
    # the warmup is what the manifest schedules before the first quoted
    # stage and does not ramp: a ramp before it is a transition, read in
    # segments, never a warmup
    warm = [
        s["name"]
        for s in stages
        if not s["quote"]
        and not s["ramp"]
        and first_quoted_s is not None
        and s["to_s"] <= first_quoted_s
    ]
    warm_seconds = max((s["to_s"] for s in stages if s["name"] in warm), default=0)
    end = max(s["to"] for s in stages)

    def label(s: dict) -> str:
        name = (
            s["name"]
            if s["scenario"] is None or len({x["scenario"] for x in stages}) == 1
            else f"{s['scenario']} {s['name']}"
        )
        return f"{name} {hhmm(s['from'])}–{hhmm(s['to'])}" + (
            "" if s["quote"] else " (excluded)"
        )

    parts = [label(s) for s in stages]
    line = (
        f"Stages (UTC): offsets converted from the first request row {hhmm(first_row)} — "
        + ", ".join(parts)
    )
    if t0:
        line += (
            f"; t0 (first measured request, where the quoted numbers start) {hhmm(t0)}"
        )
    else:
        line += "; t0: none - no stage is quoted (the per-segment view is the result)"
    ramps = [s for s in stages if s["ramp"]]
    if ramps:
        line += "; " + ", ".join(
            f"{s['name']} {hhmm(s['from'])}–{hhmm(s['to'])} read in {seg_s} s segments, offered rate at each segment's midpoint"
            for s in ramps
        )
    if warm:
        warmup_line = (
            f"Warmup:    the manifest's {' and '.join(warm)} stage{'s' if len(warm) > 1 else ''}, "
            f"{warm_seconds} s (excluded from the quoted numbers); t0 and the first row are {warm_seconds} s apart"
        )
    else:
        warmup_line = (
            "Warmup:    none - the manifest declares no warmup stage, t0 is the first request row"
            if t0 == first_row
            else "Warmup:    none - the manifest declares no warmup stage"
        )
    return {
        "first_row": first_row,
        "t0": t0,
        "end": end,
        "segment": segment,
        "stages": stages,
        "segments": segments,
        "warmup": {"stages": warm, "seconds": warm_seconds},
        "stages_line": line,
        "warmup_line": warmup_line,
    }


def report_stages(bench: Path, first_row: str, segment: str, as_json: bool) -> int:
    manifest_path = bench / "manifest.yaml"
    if not manifest_path.is_file():
        print(f"no manifest.yaml in {bench}", file=sys.stderr)
        return 1
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", first_row):
        print(
            f"--first-row is the run's first request row as RFC3339 UTC "
            f"(YYYY-MM-DDTHH:MM:SSZ), got {first_row!r}",
            file=sys.stderr,
        )
        return 1
    try:
        out = stage_layout(manifest_path.read_text(), first_row, segment)
    except ValueError as exc:
        print(f"{bench}: {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(out, indent=2))
        return 0
    print(out["stages_line"])
    print(out["warmup_line"])
    print(f"t0:  {out['t0'] or 'none'}")
    print(f"end: {out['end']}  (the last stage's end; a run may exit before it)")
    for s in out["segments"]:
        print(
            f"  {s['stage']}: {hhmm(s['from'])}–{hhmm(s['to'])}  offered rate at midpoint {s['midpoint_rate']}"
        )
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
    parser.add_argument(
        "--wait",
        metavar="DURATION",
        help="with --status: block until the run finishes or DURATION "
        "(20m, 300s, 1h) passes - exit 3 when still running at the bound",
    )
    parser.add_argument(
        "--stages",
        metavar="DIR",
        help="print the record's stage lines for the benchmark in DIR, laid "
        "out from --first-row",
    )
    parser.add_argument(
        "--first-row",
        metavar="UTC",
        help="with --stages: the run's first request row, RFC3339 UTC",
    )
    parser.add_argument(
        "--segment",
        default="30s",
        metavar="DURATION",
        help="with --stages: the width a ramp is read in (default 30s)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.stages:
        if not args.first_row:
            parser.error(
                "--stages needs --first-row <the run's first request row, UTC>"
            )
        return report_stages(Path(args.stages), args.first_row, args.segment, args.json)
    if args.first_row:
        parser.error("--first-row goes with --stages")
    if args.wait and not args.status:
        parser.error("--wait goes with --status")
    if args.wait:
        try:
            parse_wait(args.wait)
        except SystemExit as bad:
            parser.error(str(bad))
    if args.status:
        return report_status(Path(args.status), args.json, args.wait)

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
    child_env = {}
    if args.otel:
        cmd += ["-o", "opentelemetry"]
        child_env = otel_env()

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
        "command": " ".join([f"{k}={v}" for k, v in sorted(child_env.items())] + cmd),
        "summary_export": str(summary),
    }

    if args.dry_run:
        print(json.dumps(record, indent=2) if args.json else record["command"])
        return 0

    if args.detach:
        return detach(cmd, repo, Path(args.detach), record, args.json, child_env)

    record["start_utc"] = utc()
    proc = subprocess.run(
        cmd,
        cwd=repo,
        env={**os.environ, **child_env} if child_env else None,
        capture_output=True,
        text=True,
        check=False,
    )
    record["end_utc"] = utc()
    record["exit_code"] = proc.returncode

    record.update(summarise(proc.stdout, proc.stderr))

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
