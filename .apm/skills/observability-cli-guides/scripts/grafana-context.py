#!/usr/bin/env python3
"""A per-session gcx context for a remote Grafana, without touching the user's config.

    grafana-context.py --stack prod
    grafana-context.py --stack prod --json

Whole surface: --stack NAME (the gcx context to target; default the user's
current one), --json. It copies the user's gcx config to a session path,
points GCX_CONFIG at the copy, reads `gcx datasources list` on that context
and writes the default datasource UID per signal into the copy (so no later
call pays `-d <uid>`), then proves the copy with `gcx config check`. Prints the
export line to put in front of every later call, and the four UIDs. Exit 0
when the check passed, 1 when it did not - the message says what to do, and it
is the user's to do: keychain-backed credentials are bound to the original
file's path and reject the copy; the fix is `gcx login <stack> --config
<the session path>`, run by the user, then this script again. Never copies a
credential out of the keychain, never writes into the user's file.

The local oddyssey stack has its own script (the setup-local-stack skill's
gcx_local.py); this one is for a remote instance only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import run_gcx

KINDS = {
    "prometheus": ("prometheus", "-prom"),
    "tempo": ("tempo", "-traces"),
    "loki": ("loki", "-logs"),
    "pyroscope": ("grafana-pyroscope-datasource", "-profiles"),
}


def user_config() -> str:
    env = os.environ.get("GCX_CONFIG")
    if env and os.path.exists(env):
        return env
    home = os.path.join(os.path.expanduser("~"), ".config", "gcx", "config.yaml")
    return home


def session_path() -> str:
    d = os.path.join(tempfile.gettempdir(), "oddyssey")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "gcx-session.yaml")


def pick_uid(datasources: list[dict], kind: str) -> str:
    dtype, suffix = KINDS[kind]
    for ds in datasources:
        if ds.get("type") == dtype:
            return ds.get("uid", "")
    for ds in datasources:
        uid = ds.get("uid") or ""
        if uid.endswith(suffix) or uid == kind:
            return uid
    for ds in datasources:
        if suffix.strip("-") in (ds.get("name") or "").lower():
            return ds.get("uid", "")
    return ""


def set_defaults(path: str, context: str, uids: dict[str, str]) -> None:
    """Insert `datasources:` under contexts.<context> of a YAML file, without a YAML library."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    block = ["    datasources:"] + [f"      {k}: {v}" for k, v in uids.items() if v]
    out, i, done = [], 0, False
    while i < len(lines):
        ln = lines[i]
        out.append(ln)
        if (
            not done
            and re.match(rf"^  {re.escape(context)}:\s*$", ln)
            and any(l.strip() == "contexts:" for l in lines[:i])
        ):
            i += 1
            while i < len(lines) and (
                lines[i].startswith("    ") or not lines[i].strip()
            ):
                if lines[i].strip().startswith("datasources:"):
                    i += 1
                    while i < len(lines) and lines[i].startswith("      "):
                        i += 1
                    continue
                out.append(lines[i])
                i += 1
            out += block
            done = True
            continue
        i += 1
    if not done:
        raise SystemExit(f"context {context!r} not found under contexts: in {path}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stack")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    src = user_config()
    if not os.path.exists(src):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"no gcx config at {src} - run `gcx login <stack> --server <url>` first",
                }
            )
            if ns.json
            else f"no gcx config at {src} - run `gcx login <stack> --server <url>` first (yours to run)"
        )
        return 1
    dst = session_path()
    shutil.copyfile(src, dst)
    env = {"GCX_CONFIG": dst}
    context = ns.stack
    if not context:
        view = run_gcx(["config", "view"], env=env)
        context = (view.data or {}).get("current-context", "") if view.ok else ""
    if not context:
        print(
            "no gcx context selected - pass --stack <name> (see `gcx config list-contexts`)"
        )
        return 1
    ds = run_gcx(["datasources", "list", "--context", context], env=env)
    if not ds.ok:
        msg = ds.error
        hint = f"the copy at {dst} was rejected - if the message names the keychain, run `gcx login {context} --config {dst}` yourself, then this script again"
        print(
            json.dumps(
                {
                    "ok": False,
                    "context": context,
                    "config": dst,
                    "error": msg,
                    "hint": hint,
                }
            )
            if ns.json
            else f"FAILED {msg}\n{hint}"
        )
        return 1
    uids = {k: pick_uid((ds.data or {}).get("datasources") or [], k) for k in KINDS}
    set_defaults(dst, context, uids)
    check = subprocess.run(
        ["gcx", "config", "check", "--context", context],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        check=False,
    )
    ok = check.returncode == 0
    result = {
        "ok": ok,
        "context": context,
        "config": dst,
        "export": f"export GCX_CONFIG={dst}",
        "datasources": uids,
        "check": (check.stdout + check.stderr).strip().splitlines()[-1:],
    }
    if ns.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["export"])
        print("context: " + context)
        print(
            "datasources: "
            + ", ".join(f"{k}={v or '(none found)'}" for k, v in uids.items())
        )
        print(
            ("connected" if ok else "NOT connected - " + " ".join(result["check"]))
            + (
                f"; the fix is yours: gcx login {context} --config {dst}, then run this again"
                if not ok
                else ""
            )
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
