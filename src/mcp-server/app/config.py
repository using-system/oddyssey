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

# Per-stack stack_config field whitelist, mirroring what each backend's
# "what to persist" reference (update-backend-configuration skill)
# documents. None means unrestricted: "local"'s keys are container
# environment variable names (setup-local-stack's otel-lgtm-env.md
# catalog), an open set by design, not a closed field list like the
# remote backends'. A stack absent here would silently accept anything -
# every STACKS value must have an entry.
STACK_CONFIG_FIELDS: dict[str, frozenset[str] | None] = {
    "local": None,
    "grafana": frozenset(),
    "azure-monitor": frozenset(
        {"subscription", "resource_group", "workspace", "app_insights_app"}
    ),
    "cloudwatch": frozenset(
        {"region", "profile", "log_group", "metrics_log_group", "xray"}
    ),
    "datadog": frozenset(),
    "dynatrace": frozenset(),
    "splunk": frozenset(),
}

DEFAULTS = {
    "stack": "local",
    "local": {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
    "stack_config": {},
}


def _valid_port(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535
    )


def _valid_config_value(value: object) -> bool:
    # Identifiers, names, regions, ports - flat scalars only, and never
    # secrets (credentials stay in the CLI's own auth store, by name).
    return isinstance(value, (str, int, float, bool))


def _stack_config_key_allowed(stack_key: str, key: str) -> bool:
    fields = STACK_CONFIG_FIELDS.get(stack_key)
    return fields is None or key in fields


def load(path: Path | None = None) -> dict:
    """Effective configuration: defaults overlaid with the stored file.

    Tolerant by contract - the file is hand-editable and a tool call
    must never crash on it. Every tolerated-invalid field is listed in
    "invalid_ignored" (dotted names; "<file>" for unparseable JSON) so
    odd_config_get can surface the degradation.
    """
    target = CONFIG_PATH if path is None else path
    effective = {
        "stack": DEFAULTS["stack"],
        "local": dict(DEFAULTS["local"]),
        "stack_config": {},
    }
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

    raw_sc = stored.get("stack_config", {})
    if isinstance(raw_sc, dict):
        for stack_key, payload in raw_sc.items():
            if stack_key not in STACKS or not isinstance(payload, dict):
                invalid.append(f"stack_config.{stack_key}")
                continue
            clean = {}
            for key, value in payload.items():
                if _valid_config_value(value) and _stack_config_key_allowed(
                    stack_key, key
                ):
                    clean[key] = value
                else:
                    invalid.append(f"stack_config.{stack_key}.{key}")
            effective["stack_config"][stack_key] = clean
    elif "stack_config" in stored:
        invalid.append("stack_config")

    if invalid:
        effective["invalid_ignored"] = invalid
    return effective


def save(partial: dict, path: Path | None = None) -> dict:
    """Validated deep-merge into the stored file; a rejected partial writes nothing.

    Strict where load is tolerant: the caller is a tool, not a hand
    edit, so a clear error beats a silent fallback. The merged EFFECTIVE
    ports are validated together, so a partial cannot collide with a
    stored or default port. Inside stack_config, None is the deletion
    marker (issue #112): a null stack entry removes that entry, a null
    key value removes that key - the only non-scalar the strict gate
    accepts. Atomic write (temp + os.replace) so a concurrent MCP server
    never reads a half-written file.
    """
    target = CONFIG_PATH if path is None else path
    unknown = set(partial) - {"stack", "local", "stack_config"}
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

    sc_partial = partial.get("stack_config", {})
    if not isinstance(sc_partial, dict):
        raise ValueError("stack_config must be an object keyed by stack")  # noqa: TRY004
    for stack_key, payload in sc_partial.items():
        if stack_key not in STACKS:
            raise ValueError(
                f"stack_config keys must be one of {list(STACKS)}, got {stack_key!r}"
            )
        # None is the deletion marker (issue #112): a null entry removes
        # the stack's whole entry, a null key value removes that key.
        if payload is None:
            continue
        if not isinstance(payload, dict):
            raise ValueError(  # noqa: TRY004
                f"stack_config.{stack_key} must be an object of scalar values"
            )
        for key, value in payload.items():
            if value is None:
                # The deletion marker is always accepted, even for a key
                # outside the whitelist below - it must stay possible to
                # clean up a stray key an older write (or a hand edit)
                # left behind.
                continue
            if not _valid_config_value(value):
                raise ValueError(
                    f"stack_config.{stack_key}.{key} must be a string, number,"
                    f" boolean, or null to delete the key, got {value!r}"
                )
            if not _stack_config_key_allowed(stack_key, key):
                allowed = STACK_CONFIG_FIELDS[stack_key]
                if allowed:
                    raise ValueError(
                        f"stack_config.{stack_key} accepts only "
                        f"{sorted(allowed)}, got unknown key {key!r}"
                    )
                raise ValueError(
                    f"stack_config.{stack_key} does not persist any fields,"
                    f" got unknown key {key!r}"
                )

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
    if sc_partial:
        stored_sc = stored.get("stack_config")
        stored_sc = stored_sc if isinstance(stored_sc, dict) else {}
        for stack_key, payload in sc_partial.items():
            if payload is None:
                stored_sc.pop(stack_key, None)
                continue
            existing = stored_sc.get(stack_key)
            entry = dict(existing) if isinstance(existing, dict) else {}
            for key, value in payload.items():
                if value is None:
                    # Deleting the last key leaves the present-but-empty
                    # entry, which already reads as "not configured".
                    entry.pop(key, None)
                else:
                    entry[key] = value
            stored_sc[stack_key] = entry
        stored["stack_config"] = stored_sc

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
