#!/usr/bin/env python3
"""A per-session gcx context for a remote Grafana, without touching the user's config.

    grafana-context.py --stack prod
    grafana-context.py --stack prod --json

Whole surface: --stack NAME (the gcx context to target; default the user's
current one), --json. It copies the user's gcx config to a session path of
its own (one per stack and session, never shared), makes NAME the copy's
current context, reads `gcx datasources list` on it and writes the default
datasource UID per signal into the copy (so no later call pays `-d <uid>`),
then proves the copy with `gcx config check`. Prints the export line to put
in front of every later call, the context, and the four UIDs. Exit 0 when
the check passed, 1 when it did not - the message says what to do, and it
is the user's to do: keychain-backed credentials are bound to the original
file's path and reject the copy; the fix is `gcx login <stack> --config
<the session path>`, run by the user, then this script again. Never copies a
credential out of the keychain, never writes into the user's file, and there
is no other fallback: the scripts resolve their datasource from the context
and take no `-d`.

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
import time
import uuid

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
    return os.path.join(os.path.expanduser("~"), ".config", "gcx", "config.yaml")


def session_path(stack: str) -> str:
    d = os.path.join(tempfile.gettempdir(), "oddyssey")
    os.makedirs(d, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", stack)
    return os.path.join(
        d,
        f"gcx-session-{safe}-{int(time.time())}-{os.getpid()}-{uuid.uuid4().hex[:8]}.yaml",
    )


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


def _top_key(line: str) -> str | None:
    m = re.match(r"^([A-Za-z0-9_.-]+):", line)
    return m.group(1) if m else None


def current_context(path: str) -> str:
    """The file's top-level `current-context`, "" when it has none."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^current-context:\s*[\"']?([^\"'\s#]+)", line)
            if m:
                return m.group(1)
    return ""


def set_context(path: str, context: str, uids: dict[str, str]) -> None:
    """Make `context` current and give it datasource defaults - inside `contexts:` only."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    block = ["    datasources:"] + [f"      {k}: {v}" for k, v in uids.items() if v]
    out: list[str] = []
    top = None
    i, done, current_seen = 0, False, False
    while i < len(lines):
        ln = lines[i]
        key = _top_key(ln)
        if key is not None:
            top = key
            if key == "current-context":
                out.append(f"current-context: {context}")
                current_seen = True
                i += 1
                continue
        if (
            top == "contexts"
            and not done
            and re.match(rf'^  "?{re.escape(context)}"?:\s*$', ln)
        ):
            out.append(ln)
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
        out.append(ln)
        i += 1
    if not done:
        raise SystemExit(
            f"context {context!r} not found under contexts: in {path} - see `gcx config list-contexts`"
        )
    if not current_seen:
        out.append(f"current-context: {context}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stack")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    src = user_config()
    if not os.path.exists(src):
        msg = f"no gcx config at {src} - run `gcx login <stack> --server <url>` first (yours to run)"
        print(json.dumps({"ok": False, "error": msg}) if ns.json else msg)
        return 1
    current = current_context(src)
    context = ns.stack or current
    if not context:
        print(
            "no gcx context selected - pass --stack <name> (see `gcx config list-contexts`)"
        )
        return 1
    in_place = context == current
    if in_place:
        # The user's own current context: use the file where it is. gcx
        # resolves each signal's datasource from the stack when the context
        # carries no default, and a keychain-bound credential works only
        # from the file it was bound to - a copy would be refused.
        dst = src
    else:
        dst = session_path(context)
        shutil.copyfile(src, dst)
    env = {"GCX_CONFIG": dst}
    ds = run_gcx(["datasources", "list", "--context", context], env=env)
    if not ds.ok:
        hint = f"the copy at {dst} was rejected - if the message names the keychain, run `gcx login {context} --config {dst}` yourself, then this script again"
        print(
            json.dumps(
                {
                    "ok": False,
                    "context": context,
                    "config": dst,
                    "error": ds.error,
                    "hint": hint,
                }
            )
            if ns.json
            else f"FAILED {ds.error}\n{hint}"
        )
        return 1
    uids = {k: pick_uid((ds.data or {}).get("datasources") or [], k) for k in KINDS}
    if not in_place:
        set_context(dst, context, uids)
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
        "in_place": in_place,
        "export": f"export GCX_CONFIG={dst}",
        "datasources": uids,
        "check": (check.stdout + check.stderr).strip().splitlines()[-1:],
    }
    if ns.json:
        print(json.dumps(result, indent=1))
    else:
        print(result["export"])
        print(
            "context: "
            + context
            + (
                " (your current context, your config used in place, nothing written)"
                if in_place
                else " (now the copy's current context)"
            )
        )
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
