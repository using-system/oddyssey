"""Global oddyssey configuration: one file per machine, like the stack.

One shared container for every project on the machine is the assumed
design (#50 closed not-planned), so the configuration is global too -
user scope, no per-project state. The file is hand-editable: reads are
tolerant (a broken value degrades to its default, visibly), writes are
strict (a rejected partial writes nothing).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

CONFIG_PATH = Path.home() / ".oddyssey" / "config.json"

# "local" is the local stack and the default (a fresh machine is
# self-serve, #67); every other value is a remote backend of the
# observability-cli-guides skill - "grafana" means a remote Grafana,
# the CLI context says which instance.
STACKS = (
    "local",
    "grafana",
    "azure-monitor",
    "cloudwatch",
    "datadog",
    "dynatrace",
    "splunk",
)

DEFAULTS = {
    "stack": "local",
    "local": {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
}


def _valid_port(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535
    )


def load(path: Path | None = None) -> dict:
    """Effective configuration: defaults overlaid with the stored file.

    Tolerant by contract - the file is hand-editable and a tool call
    must never crash on it. Every tolerated-invalid field is listed in
    "invalid_ignored" (dotted names; "<file>" for unparseable JSON) so
    odd_config_get can surface the degradation.
    """
    target = CONFIG_PATH if path is None else path
    effective = {"stack": DEFAULTS["stack"], "local": dict(DEFAULTS["local"])}
    invalid: list[str] = []
    try:
        stored = json.loads(target.read_text())
    except FileNotFoundError:
        return effective
    except (OSError, ValueError):
        effective["invalid_ignored"] = ["<file>"]
        return effective
    if not isinstance(stored, dict):
        effective["invalid_ignored"] = ["<file>"]
        return effective

    stack = stored.get("stack", DEFAULTS["stack"])
    if stack in STACKS:
        effective["stack"] = stack
    else:
        invalid.append("stack")

    local = stored.get("local", {})
    if isinstance(local, dict):
        for key in DEFAULTS["local"]:
            if key not in local:
                continue
            if _valid_port(local[key]):
                effective["local"][key] = local[key]
            else:
                invalid.append(f"local.{key}")
    elif "local" in stored:
        invalid.append("local")

    if invalid:
        effective["invalid_ignored"] = invalid
    return effective


def save(partial: dict, path: Path | None = None) -> dict:
    """Validated deep-merge into the stored file; a rejected partial writes nothing.

    Strict where load is tolerant: the caller is a tool, not a hand
    edit, so a clear error beats a silent fallback. The merged EFFECTIVE
    ports are validated together, so a partial cannot collide with a
    stored or default port. Atomic write (temp + os.replace) so a
    concurrent MCP server never reads a half-written file.
    """
    target = CONFIG_PATH if path is None else path
    unknown = set(partial) - {"stack", "local"}
    if unknown:
        raise ValueError(f"unknown configuration keys: {sorted(unknown)}")
    if "stack" in partial and partial["stack"] not in STACKS:
        raise ValueError(
            f"stack must be one of {list(STACKS)}, got {partial['stack']!r}"
        )
    local_partial = partial.get("local", {})
    if not isinstance(local_partial, dict):
        # Every rejected partial raises ValueError by contract, so one
        # caller-facing except clause covers the whole validation.
        raise ValueError("local must be an object of port fields")  # noqa: TRY004
    unknown_ports = set(local_partial) - set(DEFAULTS["local"])
    if unknown_ports:
        raise ValueError(f"unknown local keys: {sorted(unknown_ports)}")
    for key, value in local_partial.items():
        if not _valid_port(value):
            raise ValueError(f"{key} must be an integer port in 1-65535, got {value!r}")

    effective_local = {**load(target)["local"], **local_partial}
    if len(set(effective_local.values())) != len(effective_local):
        raise ValueError(f"ports must be pairwise distinct, got {effective_local}")

    try:
        stored = json.loads(target.read_text())
        if not isinstance(stored, dict):
            stored = {}
    except (OSError, ValueError):
        stored = {}
    if "stack" in partial:
        stored["stack"] = partial["stack"]
    if local_partial:
        stored_local = stored.get("local")
        stored["local"] = {
            **(stored_local if isinstance(stored_local, dict) else {}),
            **local_partial,
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(stored, handle, indent=2)
        os.replace(temp, target)
    except BaseException:
        os.unlink(temp)
        raise
    return load(target)
