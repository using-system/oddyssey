#!/usr/bin/env python3
"""The connection proof in two parts, and the bounded landing poll of a driven run.

    azure-monitor-context.py check --subscription <subscription> --resource-group <resource_group> --workspace <workspace> --app <app_insights_app>
    azure-monitor-context.py landing --app <app_insights_app> --identity <user agent> --expect 110 --from ... --to ...

Whole surface - check: --subscription, --resource-group, --workspace (the
customer ID GUID), --app (the appId GUID) - each the resolved entry's value,
each proved when given and named as skipped when not (no --app: the run is
logs-only) - and --json. landing: --app, --identity
(the run's user agent, matched on customDimensions['user_agent.original']),
--expect N (the request count the poll waits for), a window (--from/--to or
--since), --dimension (the customDimensions key the identity is matched on,
default user_agent.original), --service (repeatable, scopes the count to
cloud_RoleName), --every (seconds between polls, default 20), --cap (the
bound, default 3m), --json. Exit codes - check: 0 connected (identity and
every part given, a workspace or a component among them), 1 identity
failure or a rights/network error (the message says what is yours to do),
3 a persisted value does not resolve, or neither a workspace nor a
component is given (identity alone proves nothing the queries read): route
to the switch, 2 az could not parse the command. landing: 0 landed, 1 the
cap was reached (the last count is in the output), 3/2 as check.

Identity is `az account show` (the local profile, no network: a stale token
passes here and fails on the targeting part, which is why both run).
Targeting is `az account show --subscription`, `az group exists`, and
`print 1` against the workspace and the component with the appId alone -
never -g beside it, never --subscription, the data plane needs neither -
run together. The count of the landing poll is
read in json at tables[0].rows[0][0]: `-o tsv` would print 1 whatever the
value (the number of result rows).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from azure_monitor_az import (
    add_window,
    ai_call,
    ai_rows,
    commands,
    emit,
    failures,
    iso,
    kql_in,
    kql_str,
    la_call,
    parse_duration,
    render_commands,
    resolve_window,
    run_az,
    run_many,
)

DIAGNOSIS = {
    "not-found": "the persisted value does not resolve (exit 3) - a wrong value, not a connection problem: route to the switch to correct it",
    "not-an-appid": "the persisted value is not an appId GUID - typically the component's resource name: route to the switch to persist the appId",
    "not-a-workspace-id": "the persisted value is not the workspace's customer ID GUID - typically its resource name: route to the switch to persist the customer ID",
    "identity": "the identity must log in again - az account show reads the local profile and passes on a stale token; az login is yours to run",
    "rights": "authenticated, but the identity lacks query rights on this resource - a permissions problem, re-persisting the same value will not fix it",
    "usage": "az could not parse the command - a defect in the invocation, never a stored value",
    "missing": "az is not installed",
}


def _last_minutes(n: int) -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return iso(now - timedelta(minutes=n)), iso(now)


def _targeting_code(kind: str) -> int:
    if kind in ("not-found", "not-an-appid", "not-a-workspace-id"):
        return 3
    return 2 if kind == "usage" else 1


def cmd_check(ns) -> tuple[int, dict]:
    out: dict = {"identity": {}, "targeting": {}, "connected": False, "commands": []}
    results = []
    acct = run_az(["account", "show"])
    results.append(acct)
    if not acct.ok:
        out["identity"] = {
            "ok": False,
            "error": acct.error,
            "diagnosis": "not logged in: az login is yours to run, never done for you",
        }
        out["commands"] = commands(results)
        out["failed"] = failures(results)
        return 1, out
    d = acct.data or {}
    out["identity"] = {
        "ok": True,
        "subscription_name": d.get("name"),
        "subscription_id": d.get("id"),
        "tenant_id": d.get("tenantId"),
        "user_type": (d.get("user") or {}).get("type"),
        "state": d.get("state"),
    }
    # One bounded call per persisted part, run together; a part not given is
    # named as skipped (#657), never left out of the output.
    frm, to = _last_minutes(5)
    sub = ["--subscription", ns.subscription] if ns.subscription else []
    parts = [
        ("subscription", ns.subscription, ["account", "show", *sub]),
        (
            "resource_group",
            ns.resource_group,
            ["group", "exists", "--resource-group", ns.resource_group or "", *sub],
        ),
        ("workspace", ns.workspace, la_call(ns.workspace or "", "print 1", frm, to)),
        ("component", ns.app, ai_call(ns.app or "", "print 1", frm, to)),
    ]
    given = [(name, call) for name, value, call in parts if value]
    answers = dict(zip([n for n, _ in given], run_many([c for _, c in given])))
    code = 0
    for name, value, _ in parts:
        if not value:
            note = "not persisted"
            if name == "component":
                note += " - no app_insights_app: requests/dependencies/customMetrics/traces/exceptions are unavailable and the run is logs-only; distributed tracing is a telemetry gap"
            elif name == "subscription":
                note += " - the CLI's active subscription is the one queried"
            out["targeting"][name] = {"ok": None, "note": note}
            continue
        r = answers[name]
        results.append(r)
        if r.ok and name == "resource_group" and r.data is not True:
            r.ok, r.kind, r.error = False, "not-found", "az group exists answered false"
        t: dict = {"ok": r.ok, "error": r.error, "kind": r.kind}
        if r.ok and name == "component":
            rows = ai_rows(r.data)
            t["value"] = rows[0].get("print_0") if rows else None
        if r.ok and name == "subscription":
            t["differs_from_active"] = (r.data or {}).get("id") != d.get("id")
        t["diagnosis"] = (
            ""
            if r.ok
            else DIAGNOSIS.get(
                r.kind,
                "read the error: connection, proxy, throttling or service error - report it verbatim and retry; never rewrite it as a targeting failure",
            )
        )
        out["targeting"][name] = t
        if not r.ok and code == 0:
            code = _targeting_code(r.kind)
    if code == 0 and not (ns.app or ns.workspace):
        # identity alone proves nothing the queries read (#657)
        code = 3
        out["identity_only"] = True
    out["connected"] = code == 0
    out["commands"] = commands(results)
    out["failed"] = failures(results)
    return code, out


def render_check(o: dict) -> str:
    out = []
    i = o["identity"]
    if not i.get("ok"):
        out.append(
            f"identity  NOT logged in - {i.get('error')}\n          {i.get('diagnosis')}"
        )
    else:
        out.append(
            f"identity  az account show: subscription {i['subscription_name']} ({i['subscription_id']}), tenant {i['tenant_id']}, user type {i['user_type']}, state {i['state']}"
        )
    for part, t in o["targeting"].items():
        if t.get("ok") is None:
            out.append(f"targeting {part}: skipped - {t['note']}")
        elif t["ok"] and part in ("subscription", "resource_group"):
            differs = (
                " - differs from the CLI's active one: the queries target the persisted one"
                if t.get("differs_from_active")
                else ""
            )
            out.append(f"targeting {part}: resolves{differs}")
        elif t["ok"]:
            out.append(f"targeting {part}: connected (print 1 answered)")
        else:
            out.append(
                f"targeting {part}: FAILED [{t['kind']}] {t['error']}\n          {t['diagnosis']}"
            )
    if o.get("identity_only"):
        out.append(
            "NOT connected - identity only: the resolved entry persists neither a workspace nor an app_insights_app, so nothing the queries read is proven - route to the switch to persist them"
        )
    else:
        out.append("connected" if o["connected"] else "NOT connected")
    out += render_commands(o)
    return "\n".join(out)


def cmd_landing(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    every = max(1, ns.every)
    cap = parse_duration(ns.cap)
    kql = (
        f"requests {kql_in('cloud_RoleName', ns.service or [])}"
        f"| where tostring(customDimensions[{kql_str(ns.dimension)}]) == {kql_str(ns.identity)} "
        f"| summarize n=count()"
    )
    out: dict = {
        "window": [frm, to],
        "identity": ns.identity,
        "expect": ns.expect,
        "polls": [],
        "landed": False,
        "count": None,
        "commands": [],
    }
    results = []
    started = time.monotonic()
    code = 1
    while True:
        r = run_az(ai_call(ns.app, kql, frm, to))
        results.append(r)
        elapsed = round(time.monotonic() - started)
        if not r.ok:
            out["polls"].append(
                {"elapsed_s": elapsed, "error": r.error, "kind": r.kind}
            )
            out["failed"] = [{"command": r.command, "error": r.error, "kind": r.kind}]
            code = (
                3
                if r.kind in ("not-found", "not-an-appid")
                else (2 if r.kind == "usage" else 1)
            )
            break
        rows = ai_rows(r.data)
        n = rows[0].get("n", 0) if rows else 0
        out["count"] = n
        out["polls"].append({"elapsed_s": elapsed, "count": n})
        if n >= ns.expect:
            out["landed"] = True
            code = 0
            break
        if time.monotonic() - started + every > cap:
            break
        time.sleep(every)
    out["commands"] = commands(results)
    return code, out


def render_landing(o: dict) -> str:
    out = [
        f"landing of identity {o['identity']!r} in {o['window'][0]}..{o['window'][1]}, expecting {o['expect']} requests"
    ]
    for p in o["polls"]:
        if "error" in p:
            out.append(f"  t+{p['elapsed_s']:>4}s  FAILED [{p['kind']}] {p['error']}")
        else:
            out.append(f"  t+{p['elapsed_s']:>4}s  {p['count']} landed")
    out.append(
        "landed"
        if o["landed"]
        else f"NOT landed within the cap: {o['count']} of {o['expect']} - widen the window, check the identity, or report the shortfall"
    )
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check")
    a.add_argument("--app")
    a.add_argument("--workspace")
    a.add_argument("--resource-group")
    a.add_argument("--subscription")
    a.add_argument("--json", action="store_true")
    b = sub.add_parser("landing")
    b.add_argument("--app", required=True)
    b.add_argument("--identity", required=True)
    b.add_argument("--expect", type=int, required=True)
    b.add_argument("--dimension", default="user_agent.original")
    b.add_argument("--service", action="append")
    b.add_argument("--every", type=int, default=20)
    b.add_argument("--cap", default="3m")
    add_window(b)
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
