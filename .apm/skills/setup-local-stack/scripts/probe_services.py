#!/usr/bin/env python3
"""Inventory what the local stack holds for a set of services, in one call.

Answers the two questions every observation asks before it drives anything:
which of the four signals each service actually carries (and under which
identity), and what its counters read right now — the baseline a later query
subtracts from.

The queries are mechanical: service names plus a window determine every one of
them, so an agent gains nothing by writing them itself. Reports presence and
absence with equal weight — a signal that is genuinely absent is a result, not
a failure — and never interprets what it finds.

    probe_services.py llmbench-api llmbench-mcp --since 30m
    probe_services.py llmbench-api --json

Reads GCX_CONFIG (see gcx_local.py, which writes it). Exit 0 when every probe
ran, 1 when the gcx context is unusable, 2 when a probe failed outright.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TIMEOUT = 60
TRACE_LIMIT = 200
# The two suffixes a cumulative reading carries: OTel counters and the count
# bucket of a histogram. Anything else has no baseline to subtract.
COUNTER_SUFFIXES = ("_total", "_count")


def gcx(args: list[str]) -> tuple[int, object | None, str]:
    """Run one gcx command; return (exit code, parsed payload, stderr).

    gcx prefixes its output with advisory `{"class":"hint"}` lines and may
    pretty-print the payload across several lines, so the payload is whatever
    survives dropping the hints.
    """
    try:
        p = subprocess.run(
            ["gcx", *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, None, f"timed out after {TIMEOUT}s"
    kept = [
        ln
        for ln in p.stdout.splitlines()
        if '"class":"hint"' not in ln and '"class": "hint"' not in ln
    ]
    body = "\n".join(kept).strip()
    if not body:
        return p.returncode, None, p.stderr.strip()
    try:
        return p.returncode, json.loads(body), p.stderr.strip()
    except json.JSONDecodeError:
        return p.returncode, None, (p.stderr.strip() or body[:200])


def probe_traces(svc: str, since: str) -> dict:
    code, data, err = gcx(
        [
            "traces",
            "query",
            f'{{ resource.service.name = "{svc}" }}',
            "--since",
            since,
            "--limit",
            str(TRACE_LIMIT),
            "-d",
            "tempo",
            "--jq",
            "{n:(.traces|length), roots:([.traces[].rootTraceName]|unique)}",
        ]
    )
    if code != 0 or not isinstance(data, dict):
        return {"present": False, "error": err or f"exit {code}"}
    n = data.get("n") or 0
    return {
        "present": n > 0,
        "count": n,
        "capped": n >= TRACE_LIMIT,
        "operations": data.get("roots") or [],
    }


def probe_metrics(svc: str) -> dict:
    code, data, err = gcx(
        [
            "metrics",
            "series",
            f'{{service_name="{svc}"}}',
            "-d",
            "prometheus",
            "--jq",
            "[.data[].__name__]|unique",
        ]
    )
    if code != 0 or not isinstance(data, list):
        return {"present": False, "error": err or f"exit {code}"}
    names = [n for n in data if isinstance(n, str)]
    return {"present": bool(names), "names": names}


def probe_identity(svc: str) -> dict:
    """target_info is the one series carrying a service's resource attributes."""
    code, data, err = gcx(
        [
            "metrics",
            "series",
            f'target_info{{service_name="{svc}"}}',
            "-d",
            "prometheus",
            "--jq",
            ".data",
        ]
    )
    if code != 0 or not isinstance(data, list) or not data:
        return {"present": False, "error": err or f"exit {code}"}
    keep = (
        "deployment_environment_name",
        "service_instance_id",
        "service_namespace",
        "service_version",
        "telemetry_sdk_language",
        "telemetry_sdk_name",
    )
    rows = [
        {k: r.get(k) for k in keep if r.get(k)} for r in data if isinstance(r, dict)
    ]
    return {
        "present": True,
        "instances": sorted({r.get("service_instance_id", "") for r in rows} - {""}),
        "attributes": rows[0] if rows else {},
    }


def probe_logs(svc: str) -> dict:
    code, data, err = gcx(
        [
            "logs",
            "series",
            "-M",
            f'{{service_name="{svc}"}}',
            "-d",
            "loki",
            "--jq",
            ".data",
        ]
    )
    if code != 0 or not isinstance(data, list):
        return {"present": False, "error": err or f"exit {code}"}
    return {
        "present": bool(data),
        "streams": len(data),
        "labels": sorted(data[0].keys()) if data and isinstance(data[0], dict) else [],
    }


def probe_profile_services(since: str) -> dict:
    """One store-wide call: profile labels carry no per-service selector worth
    one call each."""
    code, data, err = gcx(
        [
            "profiles",
            "labels",
            "-l",
            "service_name",
            "--since",
            since,
            "-d",
            "pyroscope",
        ]
    )
    if code != 0 or not isinstance(data, dict):
        return {"error": err or f"exit {code}", "names": []}
    return {"names": data.get("names") or []}


def probe_profile_types() -> dict:
    code, data, err = gcx(["profiles", "list-profile-types", "-d", "pyroscope"])
    if code != 0 or not isinstance(data, dict):
        return {"error": err or f"exit {code}", "types": []}
    types = data.get("profileTypes") or []
    return {
        "types": sorted(
            {t.get("name", "") for t in types if isinstance(t, dict)} - {""}
        )
    }


def probe_baseline(svc: str, names: list[str]) -> dict:
    """The current reading of every cumulative series the service carries."""
    counters = [n for n in names if n.endswith(COUNTER_SUFFIXES)]
    out: dict[str, object] = {}

    def one(name: str) -> tuple[str, object]:
        code, data, _ = gcx(
            [
                "metrics",
                "query",
                f'sum({name}{{service_name="{svc}"}})',
                "-d",
                "prometheus",
            ]
        )
        if code != 0 or not isinstance(data, dict):
            return name, None
        result = (data.get("data") or {}).get("result") or []
        if not result:
            return name, None
        value = result[0].get("value") or [None, None]
        try:
            return name, float(value[1])
        except (TypeError, ValueError):
            return name, None

    if counters:
        with ThreadPoolExecutor(max_workers=len(counters)) as pool:
            for name, value in pool.map(one, counters):
                if value is not None:
                    out[name] = value
    return out


def collapse_histograms(names: list[str]) -> list[str]:
    """`foo_bucket`/`foo_count`/`foo_sum` is one histogram, not three metrics."""
    families: dict[str, set[str]] = {}
    plain: list[str] = []
    for n in names:
        for suffix in ("_bucket", "_count", "_sum"):
            if n.endswith(suffix):
                families.setdefault(n[: -len(suffix)], set()).add(suffix)
                break
        else:
            plain.append(n)
    collapsed = [f"{base}_*" for base, parts in families.items() if "_bucket" in parts]
    singles = [
        f"{base}{s}"
        for base, parts in families.items()
        if "_bucket" not in parts
        for s in sorted(parts)
    ]
    return sorted(plain + collapsed + singles)


def probe_service(svc: str, since: str, baseline: bool) -> dict:
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_traces = pool.submit(probe_traces, svc, since)
        f_metrics = pool.submit(probe_metrics, svc)
        f_identity = pool.submit(probe_identity, svc)
        f_logs = pool.submit(probe_logs, svc)
        result = {
            "service": svc,
            "traces": f_traces.result(),
            "metrics": f_metrics.result(),
            "identity": f_identity.result(),
            "logs": f_logs.result(),
        }
    if baseline and result["metrics"].get("present"):
        result["baseline"] = probe_baseline(svc, result["metrics"]["names"])
    return result


def render(report: dict) -> str:
    lines: list[str] = []
    services = [s["service"] for s in report["services"]]
    lines.append(
        f"probe: {', '.join(services)}   window={report['window']}"
        f"   at={report['probed_at']}"
    )
    profiled = set(report["profiles"].get("names") or [])
    for s in report["services"]:
        svc = s["service"]
        tr, me, lo, idn = s["traces"], s["metrics"], s["logs"], s["identity"]
        flags = [
            f"traces {str(tr.get('count', 0)) + ('+' if tr.get('capped') else '')}"
            if tr.get("present")
            else "traces ABSENT",
            f"metrics {len(me.get('names', []))}"
            if me.get("present")
            else "metrics ABSENT",
            f"logs {lo.get('streams', 0)}" if lo.get("present") else "logs ABSENT",
            "profiles yes" if svc in profiled else "profiles ABSENT",
        ]
        lines.append("")
        lines.append(f"{svc}  |  " + "  ".join(flags))
        if idn.get("present"):
            attrs = idn.get("attributes") or {}
            ident = "  ".join(
                f"{k.replace('service_', '').replace('telemetry_sdk_', 'sdk_')}={v}"
                for k, v in attrs.items()
                if k != "service_instance_id"
            )
            inst = idn.get("instances") or []
            lines.append(
                f"  identity   instances={len(inst)} "
                f"[{', '.join(i[:8] for i in inst)}]  {ident}"
            )
        else:
            lines.append("  identity   ABSENT (no target_info series)")
        if tr.get("operations"):
            lines.append(f"  operations {', '.join(tr['operations'])}")
        if me.get("names"):
            lines.append(f"  metrics    {', '.join(collapse_histograms(me['names']))}")
        if lo.get("labels"):
            lines.append(f"  log labels {', '.join(lo['labels'])}")
        if s.get("baseline"):
            readings = "  ".join(f"{k}={v:g}" for k, v in sorted(s["baseline"].items()))
            lines.append(f"  baseline   {readings}")
        for probe in ("traces", "metrics", "logs", "identity"):
            if s[probe].get("error"):
                lines.append(f"  ! {probe}: {s[probe]['error']}")
    lines.append("")
    types = report["profile_types"].get("types") or []
    lines.append(f"store      profile types: {', '.join(types) if types else 'none'}")
    lines.append(
        f"           services pushing profiles: "
        f"{', '.join(sorted(profiled)) if profiled else 'none'}"
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("services", nargs="+", help="service names to probe")
    ap.add_argument("--since", default="30m", help="lookback window (default 30m)")
    ap.add_argument(
        "--no-baseline",
        action="store_true",
        help="skip the counter readings (presence and identity only)",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if not shutil.which("gcx"):
        print("gcx is not installed (brew install gcx)", file=sys.stderr)
        return 1
    config = os.environ.get("GCX_CONFIG")
    if not config or not Path(config).is_file():
        print(
            "GCX_CONFIG is unset or missing — run this skill's gcx_local.py first",
            file=sys.stderr,
        )
        return 1

    from datetime import datetime, timezone

    with ThreadPoolExecutor(max_workers=len(args.services) + 2) as pool:
        f_profiles = pool.submit(probe_profile_services, args.since)
        f_types = pool.submit(probe_profile_types)
        f_services = [
            pool.submit(probe_service, svc, args.since, not args.no_baseline)
            for svc in args.services
        ]
        report = {
            "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": args.since,
            "services": [f.result() for f in f_services],
            "profiles": f_profiles.result(),
            "profile_types": f_types.result(),
        }

    print(json.dumps(report, indent=2) if args.json else render(report))
    failed = any(
        s[p].get("error")
        for s in report["services"]
        for p in ("traces", "metrics", "logs", "identity")
    )
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
