#!/usr/bin/env python3
"""Configure gcx against the local oddyssey stack, and prove it.

Everything this does is mechanical: read the host ports the global
configuration holds, write an isolated gcx context at a stable path, and
run `gcx config check` against it. It exists so no agent has to
reconstruct that from prose - the ports are never assumed, the user's own
gcx contexts are never touched, and a port change rewrites the file whole
(gcx binds a stored credential to its destination, so patching the
`server:` line in place leaves the binding stale and gcx refuses it).

    python3 gcx_local.py            # configure and check
    python3 gcx_local.py --json     # the same, machine-readable

Prints the export line to put in front of every later gcx call, the four
datasource UIDs, and the endpoints an instrumented service should target.
Exit 0 when gcx reached the stack, 1 otherwise - the message says which
step failed and what to do about it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".oddyssey" / "config.json"
DEFAULT_PORTS = {
    "grafana_port": 3000,
    "otlp_grpc_port": 4317,
    "otlp_http_port": 4318,
    "pyroscope_port": 4040,
}
DATASOURCES = {
    "traces": "tempo",
    "metrics": "prometheus",
    "logs": "loki",
    "profiles": "pyroscope",
}


def config_path() -> Path:
    tmp = os.environ.get("TMPDIR", "/tmp").rstrip("/")
    return Path(tmp) / "oddyssey" / "gcx-local.yaml"


def ports() -> dict:
    """Host ports from the global configuration, defaults where it is silent."""
    resolved = dict(DEFAULT_PORTS)
    try:
        stored = json.loads(CONFIG_PATH.read_text()).get("local", {})
    except (OSError, ValueError):
        return resolved
    for key in resolved:
        value = stored.get(key)
        if isinstance(value, int) and 0 < value < 65536:
            resolved[key] = value
    return resolved


def write_context(grafana_port: int) -> Path:
    """Write the isolated context whole - never patch it in place."""
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "current-context: local\n"
        "contexts:\n"
        "  local:\n"
        "    grafana:\n"
        f"      server: http://localhost:{grafana_port}\n"
        "      user: admin\n"
        "      password: admin\n"
        "      org-id: 1\n"
        "    default-prometheus-datasource: prometheus\n"
        "    default-loki-datasource: loki\n"
        "    default-tempo-datasource: tempo\n"
        "    default-pyroscope-datasource: pyroscope\n"
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if shutil.which("gcx") is None:
        print(
            "gcx is not on the path. Install it - `brew install gcx`, or the "
            "official script from https://github.com/grafana/gcx - then run "
            "this again.",
            file=sys.stderr,
        )
        return 1

    resolved = ports()
    target = write_context(resolved["grafana_port"])
    env = {**os.environ, "GCX_CONFIG": str(target)}
    check = subprocess.run(
        ["gcx", "config", "check"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    result = {
        "gcx_config": str(target),
        "grafana_url": f"http://localhost:{resolved['grafana_port']}",
        "otlp_http_endpoint": f"http://localhost:{resolved['otlp_http_port']}",
        "otlp_grpc_endpoint": f"http://localhost:{resolved['otlp_grpc_port']}",
        "pyroscope_endpoint": f"http://localhost:{resolved['pyroscope_port']}",
        "datasources": DATASOURCES,
        "connected": check.returncode == 0,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"export GCX_CONFIG={target}")
        print(f"grafana        {result['grafana_url']}")
        print(f"otlp (http)    {result['otlp_http_endpoint']}")
        print(f"pyroscope      {result['pyroscope_endpoint']}")
        print("datasources    " + "  ".join(f"{k}={v}" for k, v in DATASOURCES.items()))
        print(f"connected      {'yes' if result['connected'] else 'NO'}")

    if check.returncode != 0:
        sys.stderr.write(check.stdout + check.stderr)
        sys.stderr.write(
            "\ngcx could not reach the stack. Start it with the oddyssey MCP "
            "server's odd_stack_up, then run this again.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
