#!/usr/bin/env python3
"""The connection proof in two parts, and the bounded landing poll of a driven run.

    cloudwatch-context.py check --profile <profile> --region <region> --log-group <log_group> --metrics-log-group <metrics_log_group>
    cloudwatch-context.py landing --profile <profile> --region <region> --log-group <log_group> --until 2026-09-11T12:30:00Z --service orders-api

Whole surface - check: --profile, --region (both required), --log-group and
--metrics-log-group (each optional: given, the group is proved to resolve;
omitted, that part is skipped and the output says so), --json. landing:
--profile, --region, --log-group (required), --metrics-log-group (optional,
polled the same way as a lower bound only), --until (the RFC 3339 UTC
instant the newest record must reach - the run's end), --service
(repeatable, scopes the probe to resource.service.name), --lookback (how
far back the probe reads, default 15m), --every (seconds between polls,
default 10), --cap (the bound, default 3m), --json. Exit codes - check: 0
connected (identity and every group given), 1 an identity failure or a
rights/network error (the message says what is yours to do), 3 a persisted
group does not resolve (a wrong value: route to the switch), 2 aws refused
the command. landing: 0 landed, 1 the cap was reached (the last newest is
in the output), 3/2 as check.

Identity is `sts get-caller-identity --profile <profile>`: a success proves
the credentials resolve and work, needing no permission. Its failures are
diagnosed: the expired SSO token (`aws sso login --profile <profile>` is
yours to run), a profile the CLI cannot find, no credentials at all (an SSO
setup routinely has no default profile: the persisted profile is the fix,
never `aws login`). Targeting is `describe-log-groups` with the group as
the prefix, the name matched exactly in the answer. The landing proof is
the Logs Insights `stats max(@timestamp)` probe (never a stream's
lastEventTimestamp, which lags by minutes) polled until it reaches --until:
a proof for the log records only - metrics are proven by the metric read
itself (an EMF record landed does not mean the metric is extracted yet), and
traces have no landing proof on this backend (a summary count read once is
an observation, not a proven landing).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloudwatch_aws import (
    commands,
    cw_in,
    emit,
    failures,
    insights_query,
    iso,
    parse_duration,
    parse_ts,
    register_targets,
    render_commands,
    run_aws,
    run_many,
)

DIAGNOSIS = {
    "identity-expired": "the profile's cached SSO token has expired: run aws sso login --profile <profile> (a browser flow, yours to run, never done for you)",
    "no-profile": "the persisted profile does not exist locally: aws configure list-profiles enumerates what does - route to the switch to persist one of them",
    "no-credentials": "no credentials resolve: an SSO setup routinely has no default profile - persist the named profile (aws configure list-profiles) rather than running the aws login the error suggests",
    "rights": "authenticated, but the identity lacks rights on this call - a permissions problem, re-persisting the same value will not fix it",
    "not-found": "the persisted group does not resolve (exit 3) - a wrong value, not a connection problem: route to the switch to correct it",
    "usage": "aws refused the command - a defect in the invocation, never a stored value",
    "missing": "aws is not installed",
}


def _code(kind: str) -> int:
    if kind == "not-found":
        return 3
    if kind == "usage":
        return 2
    return 1


def cmd_check(ns) -> tuple[int, dict]:
    register_targets(log_group=ns.log_group, metrics_log_group=ns.metrics_log_group)
    out: dict = {"identity": {}, "targeting": {}, "connected": False, "commands": []}
    results = []
    ident = run_aws(["sts", "get-caller-identity"], ns.profile, ns.region)
    results.append(ident)
    if not ident.ok:
        out["identity"] = {
            "ok": False,
            "error": ident.error,
            "kind": ident.kind,
            "diagnosis": DIAGNOSIS.get(
                ident.kind,
                "read the error: connection, proxy, throttling or service error - report it verbatim and retry",
            ),
        }
        out["commands"] = commands(results)
        out["failed"] = failures(results)
        return _code(ident.kind), out
    d = ident.data or {}
    arn = d.get("Arn", "")
    parts = arn.split(":")
    out["identity"] = {
        "ok": True,
        "account": d.get("Account"),
        "arn": arn,
        "principal_type": parts[5].split("/")[0] if len(parts) > 5 else "-",
    }
    code = 0
    groups = [("log_group", ns.log_group), ("metrics_log_group", ns.metrics_log_group)]
    calls = [
        ["logs", "describe-log-groups", "--log-group-name-prefix", value]
        for _, value in groups
        if value
    ]
    answers = run_many(calls, ns.profile, ns.region)
    results.extend(answers)
    it = iter(answers)
    for fld, value in groups:
        if not value:
            out["targeting"][fld] = {
                "ok": None,
                "note": f"no {fld} given: skipped, not failed",
            }
            continue
        r = next(it)
        if not r.ok:
            out["targeting"][fld] = {
                "ok": False,
                "error": r.error,
                "kind": r.kind,
                "diagnosis": DIAGNOSIS.get(
                    r.kind, "read the error and report it verbatim"
                ),
            }
            code = code or _code(r.kind)
            continue
        found = [
            g
            for g in (r.data or {}).get("logGroups", [])
            if g.get("logGroupName") == value
        ]
        if not found:
            out["targeting"][fld] = {
                "ok": False,
                "error": "no log group of that exact name (the prefix matched "
                + str(len((r.data or {}).get("logGroups", [])))
                + ")",
                "kind": "not-found",
                "diagnosis": DIAGNOSIS["not-found"],
            }
            code = code or 3
            continue
        g = found[0]
        out["targeting"][fld] = {
            "ok": True,
            "retention_days": g.get("retentionInDays"),
            "stored_bytes": g.get("storedBytes"),
        }
    out["connected"] = code == 0
    out["commands"] = commands(results)
    out["failed"] = failures(results)
    return code, out


def render_check(o: dict) -> str:
    out = []
    i = o["identity"]
    if not i.get("ok"):
        out.append(
            f"identity  NOT connected [{i.get('kind')}] {i.get('error')}\n          {i.get('diagnosis')}"
        )
    else:
        acct = str(i.get("account") or "")
        out.append(
            f"identity  sts get-caller-identity answered: a {i['principal_type']} principal in account ****{acct[-4:]} (the full values are under --json)"
        )
    for fld, t in o["targeting"].items():
        if t.get("ok") is None:
            out.append(f"targeting {fld}: skipped - {t['note']}")
        elif t["ok"]:
            out.append(
                f"targeting {fld}: resolves (retention {t.get('retention_days') or 'never expires'} days, {t.get('stored_bytes')} bytes stored)"
            )
        else:
            out.append(
                f"targeting {fld}: FAILED [{t['kind']}] {t['error']}\n          {t['diagnosis']}"
            )
    out.append("connected" if o["connected"] else "NOT connected")
    out += render_commands(o)
    return "\n".join(out)


def _parse_insights_ts(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S.%f").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        try:
            return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None


def cmd_landing(ns) -> tuple[int, dict]:
    register_targets(log_group=ns.log_group, metrics_log_group=ns.metrics_log_group)
    until = parse_ts(ns.until)
    every = max(1, ns.every)
    cap = parse_duration(ns.cap)
    lookback = parse_duration(ns.lookback)
    query = f"{cw_in('resource.service.name', ns.service or [])}| stats max(@timestamp) as newest, count() as n".lstrip(
        "| "
    )
    if not ns.service:
        query = "stats max(@timestamp) as newest, count() as n"
    out: dict = {
        "until": iso(until),
        "services": ns.service or [],
        "polls": [],
        "landed": False,
        "newest": None,
        "metrics_log_group": None,
        "commands": [],
        "failed": [],
        "notes": [
            "logs: proven when the newest record reaches --until (the Logs Insights max(@timestamp) probe, never a stream's lastEventTimestamp)",
            "metrics: the probe on the EMF group is a lower bound only - the metric read itself (cloudwatch-metrics.py window/series answering datapoints) is the proof",
            "traces: no landing proof exists on this backend - a summary count read once is an observation, not a proven landing; say which in the report",
        ],
    }
    results = []
    started = time.monotonic()
    code = 1
    while True:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        frm = until - timedelta(seconds=lookback)
        r = insights_query(
            [ns.log_group],
            query,
            frm,
            now + timedelta(minutes=1),
            ns.profile,
            ns.region,
        )
        results.append(r)
        elapsed = round(time.monotonic() - started)
        if not r.ok:
            out["polls"].append(
                {"elapsed_s": elapsed, "error": r.error, "kind": r.kind}
            )
            out["failed"] = failures([r])
            code = _code(r.kind)
            break
        rows = r.data or []
        newest = _parse_insights_ts(rows[0].get("newest")) if rows else None
        n = rows[0].get("n", 0) if rows else 0
        out["newest"] = iso(newest) if newest else None
        out["polls"].append(
            {"elapsed_s": elapsed, "newest": out["newest"], "records": n}
        )
        if newest and newest >= until:
            out["landed"] = True
            code = 0
            break
        if time.monotonic() - started + every > cap:
            break
        time.sleep(every)
    if ns.metrics_log_group:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        r = insights_query(
            [ns.metrics_log_group],
            "stats max(@timestamp) as newest, count() as n",
            until - timedelta(seconds=lookback),
            now + timedelta(minutes=1),
            ns.profile,
            ns.region,
        )
        results.append(r)
        if r.ok and r.data:
            newest = _parse_insights_ts(r.data[0].get("newest"))
            out["metrics_log_group"] = {
                "newest": iso(newest) if newest else None,
                "records": r.data[0].get("n", 0),
                "reached_until": bool(newest and newest >= until),
                "lower_bound_only": True,
            }
        else:
            out["metrics_log_group"] = {"error": r.error, "kind": r.kind}
            out.setdefault("failed", []).extend(failures([r]))
    out["commands"] = commands(results)
    return code, out


def render_landing(o: dict) -> str:
    scope = f" of {', '.join(o['services'])}" if o["services"] else ""
    out = [f"landing{scope}: the newest log record must reach {o['until']}"]
    for p in o["polls"]:
        if "error" in p:
            out.append(f"  t+{p['elapsed_s']:>4}s  FAILED [{p['kind']}] {p['error']}")
        else:
            out.append(
                f"  t+{p['elapsed_s']:>4}s  newest {p['newest'] or '-'} ({p['records']} records in the lookback)"
            )
    out.append(
        "landed (logs)"
        if o["landed"]
        else f"NOT landed within the cap: newest {o['newest'] or '-'} - widen --lookback, check the service, or report the shortfall"
    )
    m = o.get("metrics_log_group")
    if m:
        if "error" in m:
            out.append(f"  metrics group: FAILED [{m['kind']}] {m['error']}")
        else:
            out.append(
                f"  metrics group: newest EMF record {m['newest'] or '-'} ({'reached' if m['reached_until'] else 'not yet at'} --until) - a lower bound only, the metric read is the proof"
            )
    out += ["  " + n for n in o["notes"]]
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check")
    a.add_argument("--profile", required=True)
    a.add_argument("--region", required=True)
    a.add_argument("--log-group")
    a.add_argument("--metrics-log-group")
    a.add_argument("--json", action="store_true")
    b = sub.add_parser("landing")
    b.add_argument("--profile", required=True)
    b.add_argument("--region", required=True)
    b.add_argument("--log-group", required=True)
    b.add_argument("--metrics-log-group")
    b.add_argument("--until", required=True)
    b.add_argument("--service", action="append")
    b.add_argument("--lookback", default="15m")
    b.add_argument("--every", type=int, default=10)
    b.add_argument("--cap", default="3m")
    b.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    if ns.cmd == "check":
        code, o = cmd_check(ns)
        emit(o, ns.json, render_check)
    else:
        code, o = cmd_landing(ns)
        emit(o, ns.json, render_landing)
    return code


if __name__ == "__main__":
    sys.exit(main())
