#!/usr/bin/env python3
"""The connection proof and the effective seqcli configuration, in one call.

    seq-context.py
    seq-context.py --json

Whole surface: --json. No window, no selector. Prints where the seqcli
binary was found (PATH or ~/.dotnet/tools), the client version, the server
URL and where it came from (the SEQCLI_CONNECTION_SERVERURL variable when
set, else connection.serverUrl in SeqCli.json), whether an API key is
configured (by name only - SEQCLI_CONNECTION_APIKEY or connection.apiKey -
its value is never printed), the health probe's verdict and the server
version it answered with. Exit 0 when the server answered healthy, 1 when
it is unreachable or unhealthy, 127 when seqcli is not installed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seq_cli import SEQCLI, SEQCLI_WHERE, commands, emit, health, render_commands, run


def probe() -> tuple[int, dict]:
    out = {
        "seqcli": SEQCLI or None,
        "found_in": SEQCLI_WHERE or None,
        "client_version": None,
        "server_url": None,
        "server_url_from": None,
        "api_key": "not set",
        "api_key_from": None,
        "health": None,
        "server_version": None,
        "error": "",
        "commands": [],
    }
    if not SEQCLI:
        out["error"] = "seqcli is not installed: not on PATH and not at ~/.dotnet/tools/seqcli"
        return 127, out
    results = []
    ver = run(["version"], "text")
    results.append(ver)
    out["client_version"] = ver.data if ver.ok else None
    env_url = os.environ.get("SEQCLI_CONNECTION_SERVERURL")
    if env_url:
        out["server_url"], out["server_url_from"] = env_url, "SEQCLI_CONNECTION_SERVERURL"
    else:
        cfg = run(["config", "get", "-k", "connection.serverUrl"], "text")
        results.append(cfg)
        out["server_url"] = cfg.data if cfg.ok else None
        out["server_url_from"] = "SeqCli.json connection.serverUrl"
    if os.environ.get("SEQCLI_CONNECTION_APIKEY"):
        out["api_key"], out["api_key_from"] = "set", "SEQCLI_CONNECTION_APIKEY"
    else:
        key = run(["config", "get", "-k", "connection.apiKey"], "text")
        results.append(key)
        if key.ok and key.data:
            out["api_key"], out["api_key_from"] = "set", "SeqCli.json connection.apiKey"
    h = health()
    results.append(h)
    out["health"] = h.data if h.ok else {"status": "unreachable", "description": h.error}
    if h.ok and out["server_url"]:
        api = out["server_url"].rstrip("/") + "/api"
        try:
            with urllib.request.urlopen(api, timeout=15) as resp:  # noqa: S310 - the configured server
                out["server_version"] = json.load(resp).get("Version")
            out["commands_extra"] = [f"curl -s {api}"]
        except (urllib.error.URLError, ValueError, OSError):
            out["server_version"] = None
    out["commands"] = commands(results) + out.pop("commands_extra", [])
    healthy = h.ok and (h.data or {}).get("status") == "healthy"
    if not healthy:
        out["error"] = h.error or f"server answered {(h.data or {}).get('status')}"
    return (0 if healthy else 1), out


def render(o: dict) -> str:
    lines = []
    if not o.get("seqcli"):
        return "ERROR " + o["error"]
    lines.append(f"seqcli: {o['seqcli']} (found on {o['found_in']}), client {o['client_version']}")
    lines.append(f"server: {o['server_url']} (from {o['server_url_from']}), api key {o['api_key']}"
                 + (f" ({o['api_key_from']})" if o.get("api_key_from") else ""))
    h = o.get("health") or {}
    lines.append(f"health: {h.get('status')} - {h.get('description')}"
                 + (f"; server version {o['server_version']}" if o.get("server_version") else ""))
    if o.get("error"):
        lines.append("ERROR " + o["error"])
    lines += render_commands(o)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ns = ap.parse_args()
    code, out = probe()
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
