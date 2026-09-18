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
import re
import tempfile
from importlib import metadata as importlib_metadata
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
)

# Per-stack stack_config field whitelist, mirroring each backend's
# "## What to persist" section in the observability-cli-guides skill's
# references/<stack>.md. None means unrestricted: "local"'s keys are container
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
}

# A custom stack (issue #228) is a backend the package does not ship,
# described by a stack directory in the observed repository. The server never
# reads that directory: the caller passes its declaration - the stack name and
# the stack_config fields its guide names - and the server stores it under
# "custom", keyed by stack, next to the built-in whitelist above. A name
# outside STACKS is accepted only with a declaration; its stack_config is
# validated against the declared list exactly like a built-in's. Names and
# fields are kebab-case / snake_case identifiers - the shape a stack guide's
# frontmatter and a stack_config key already have.
CUSTOM_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
CUSTOM_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DECLARATION_KEYS = frozenset({"stack_config_fields"})

# A stack_config key is "<stack>" or "<environment>-<stack>" (issue #618):
# a remote backend's targeting values differ per deployment environment,
# so one stack may hold one entry per environment next to its plain one.
# The environment is kebab-case with no trailing dash - stricter than
# CUSTOM_NAME_RE - and never the sentinel the agents record when the
# telemetry carries no environment. The key is parsed by suffix, the
# longest known stack winning ("dev-azure-monitor" is dev + azure-monitor,
# "pre-prod-cloudwatch" is pre-prod + cloudwatch); "local" takes no
# prefix - the local stack is the local environment by construction. The
# optional global "environment" field selects, for the configured stack,
# the entry whose key resolves to (environment, stack), else the plain
# one: two whole entries, never a merge.
ENVIRONMENT_RE = re.compile(r"^[a-z]([a-z0-9-]*[a-z0-9])?$")
ENVIRONMENT_SENTINEL = "unknown"
KEY_FORMS = (
    "<stack> or <environment>-<stack> - <stack> a built-in or a declared custom"
    " stack, <environment> kebab-case (^[a-z]([a-z0-9-]*[a-z0-9])?$) and never"
    f" {ENVIRONMENT_SENTINEL!r}; local takes no prefix"
)

DEFAULTS = {
    "stack": "local",
    "local": {
        "grafana_port": 3000,
        "otlp_grpc_port": 4317,
        "otlp_http_port": 4318,
        "pyroscope_port": 4040,
    },
    "stack_config": {},
    "custom": {},
}


def _valid_port(value: object) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535
    )


def _valid_config_value(value: object) -> bool:
    # Identifiers, names, regions, ports - flat scalars only, and never
    # secrets (credentials stay in the CLI's own auth store, by name).
    return isinstance(value, (str, int, float, bool))


def _valid_declaration(declaration: object) -> bool:
    """A declaration is exactly {"stack_config_fields": [unique field names]}."""
    if not isinstance(declaration, dict) or set(declaration) != DECLARATION_KEYS:
        return False
    fields = declaration["stack_config_fields"]
    return (
        isinstance(fields, list)
        and all(isinstance(f, str) and CUSTOM_FIELD_RE.fullmatch(f) for f in fields)
        and len(set(fields)) == len(fields)
    )


def _valid_environment(value: object) -> bool:
    return (
        isinstance(value, str)
        and ENVIRONMENT_RE.fullmatch(value) is not None
        and value != ENVIRONMENT_SENTINEL
    )


def _split_prefixed(key: str, known: frozenset[str]) -> tuple[str, str] | None:
    """The (environment, stack) parse of a key that is not itself a known
    stack: the longest known stack that is its "-<stack>" suffix, and the
    environment before it. None when no stack is the suffix or the prefix
    is no environment - "local" is never a suffix."""
    for stack in sorted(known - {"local"}, key=len, reverse=True):
        if key.endswith("-" + stack):
            prefix = key[: -len(stack) - 1]
            return (prefix, stack) if _valid_environment(prefix) else None
    return None


def resolve_stack_config_key(
    key: object, custom: dict[str, dict]
) -> tuple[str | None, str] | None:
    """(environment, stack) for a stack_config key: (None, key) when the
    key is a known stack, the suffix parse otherwise, None when the key
    resolves to nothing - the whitelist is the stack's either way."""
    if not isinstance(key, str):
        return None
    if key in STACKS or key in custom:
        return None, key
    return _split_prefixed(key, frozenset(STACKS) | frozenset(custom))


def _allowed_fields(stack: str, custom: dict[str, dict]) -> frozenset[str] | None:
    """The field whitelist of a known stack: None for an open set."""
    if stack in STACKS:
        return STACK_CONFIG_FIELDS[stack]
    return frozenset(custom[stack]["stack_config_fields"])


def _stack_config_key_allowed(stack: str, key: str, custom: dict) -> bool:
    fields = _allowed_fields(stack, custom)
    return fields is None or key in fields


def _effective_entry(stack: str, environment: str | None, stack_config: dict) -> dict:
    """The entry the configured pair resolves to: the environment's when
    one is persisted for it, the stack's plain one otherwise - whole, never
    merged. On the local stack the environment is inert."""
    if stack == "local":
        environment = None
    key = stack
    if environment is not None and f"{environment}-{stack}" in stack_config:
        key = f"{environment}-{stack}"
    return {
        "stack": stack,
        "environment": environment,
        "stack_config_key": key,
        "stack_config": dict(stack_config.get(key, {})),
    }


def installed_version() -> str | None:
    """The installed oddyssey-mcp distribution's version, read from its
    metadata like the telemetry resource's service.version - never a
    constant. None when the distribution is absent (a source checkout not
    installed as a distribution): a version never breaks a tool.
    """
    try:
        return importlib_metadata.version("oddyssey-mcp")
    except Exception:  # noqa: BLE001 - a version never breaks a tool
        return None


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
        "environment": None,
        "local": dict(DEFAULTS["local"]),
        "stack_config": {},
        "custom": {},
    }
    invalid: list[str] = []
    try:
        stored = json.loads(target.read_text())
    except FileNotFoundError:
        effective["effective"] = _effective_entry("local", None, {})
        return effective
    except (OSError, ValueError):
        effective["invalid_ignored"] = ["<file>"]
        effective["effective"] = _effective_entry("local", None, {})
        return effective
    if not isinstance(stored, dict):
        effective["invalid_ignored"] = ["<file>"]
        effective["effective"] = _effective_entry("local", None, {})
        return effective

    # Declarations first: the stack and the stack_config entries below are
    # read against them, so a broken declaration takes its stack down with
    # it - flagged twice, once per dropped field, never silently. A name
    # that parses as <environment>-<known stack> (a built-in, or another
    # otherwise-valid declaration) is dropped too: its entry is then read
    # as that stack's environment entry - the one backward-compatibility
    # exception of #618.
    raw_custom = stored.get("custom", {})
    if isinstance(raw_custom, dict):
        candidates = {
            name
            for name, declaration in raw_custom.items()
            if isinstance(name, str)
            and CUSTOM_NAME_RE.fullmatch(name)
            and name not in STACKS
            and _valid_declaration(declaration)
        }
        for name, declaration in raw_custom.items():
            if name in candidates and (
                _split_prefixed(name, frozenset(STACKS) | (candidates - {name})) is None
            ):
                effective["custom"][name] = {
                    "stack_config_fields": list(declaration["stack_config_fields"])
                }
            else:
                invalid.append(f"custom.{name}")
    elif "custom" in stored:
        invalid.append("custom")
    custom = effective["custom"]

    stack = stored.get("stack", DEFAULTS["stack"])
    if stack in STACKS or stack in custom:
        effective["stack"] = stack
    else:
        invalid.append("stack")

    environment = stored.get("environment")
    if environment is None or _valid_environment(environment):
        effective["environment"] = environment
    else:
        invalid.append("environment")

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
            resolved = resolve_stack_config_key(stack_key, custom)
            if resolved is None or not isinstance(payload, dict):
                invalid.append(f"stack_config.{stack_key}")
                continue
            _, stack_of_key = resolved
            clean = {}
            for key, value in payload.items():
                if _valid_config_value(value) and _stack_config_key_allowed(
                    stack_of_key, key, custom
                ):
                    clean[key] = value
                else:
                    invalid.append(f"stack_config.{stack_key}.{key}")
            effective["stack_config"][stack_key] = clean
    elif "stack_config" in stored:
        invalid.append("stack_config")

    if invalid:
        effective["invalid_ignored"] = invalid
    effective["effective"] = _effective_entry(
        effective["stack"], effective["environment"], effective["stack_config"]
    )
    return effective


def _validate_custom(partial: dict, stored_custom: dict) -> dict:
    """The declarations after this partial: stored ones, replaced by the
    partial's, minus the null-deleted ones. Raises on a malformed partial."""
    custom_partial = partial.get("custom", {})
    if not isinstance(custom_partial, dict):
        raise ValueError("custom must be an object keyed by stack name")  # noqa: TRY004
    effective = {name: dict(decl) for name, decl in stored_custom.items()}
    for name, declaration in custom_partial.items():
        if not isinstance(name, str) or not CUSTOM_NAME_RE.fullmatch(name):
            raise ValueError(
                f"custom stack names are kebab-case identifiers"
                f" (^[a-z][a-z0-9-]*$), got {name!r}"
            )
        if name in STACKS:
            raise ValueError(
                f"custom.{name}: {name!r} is a built-in stack and cannot be redeclared"
            )
        if declaration is None:
            # The deletion marker, as everywhere else in this file.
            effective.pop(name, None)
            continue
        if not _valid_declaration(declaration):
            raise ValueError(
                f'custom.{name} must be {{"stack_config_fields": [...]}} - a list'
                f" of unique snake_case field names, got {declaration!r}"
            )
        # A name readable as <environment>-<known stack> would make a
        # stack_config key readable two ways (#618): refused in both
        # directions - the name itself, and a name that would turn an
        # already-declared one into its environment entry.
        known = frozenset(STACKS) | frozenset(effective) - {name}
        parsed = _split_prefixed(name, known)
        if parsed is not None:
            raise ValueError(
                f"custom.{name}: {name!r} reads as the {parsed[0]!r} environment"
                f" entry of stack {parsed[1]!r} (stack_config keys are"
                f" <environment>-<stack>) - pick a name that ends in no known stack"
            )
        for other in sorted(effective):
            if other != name and _split_prefixed(other, known | {name}) is not None:
                raise ValueError(
                    f"custom.{name}: declaring {name!r} would make the declared"
                    f" custom stack {other!r} read as its environment entry"
                    f" (stack_config keys are <environment>-<stack>) - remove"
                    f" {other!r} first, or in the same call"
                )
        effective[name] = {
            "stack_config_fields": list(declaration["stack_config_fields"])
        }
    return effective


def save(partial: dict, path: Path | None = None) -> dict:
    """Validated deep-merge into the stored file; a rejected partial writes nothing.

    Strict where load is tolerant: the caller is a tool, not a hand
    edit, so a clear error beats a silent fallback. The merged EFFECTIVE
    ports are validated together, so a partial cannot collide with a
    stored or default port. Inside stack_config and custom, None is the
    deletion marker (issue #112): a null stack entry removes that entry, a
    null key value removes that key - the only non-scalar the strict gate
    accepts. Atomic write (temp + os.replace) so a concurrent MCP server
    never reads a half-written file.
    """
    target = CONFIG_PATH if path is None else path
    unknown = set(partial) - {"stack", "environment", "local", "stack_config", "custom"}
    if unknown:
        raise ValueError(f"unknown configuration keys: {sorted(unknown)}")

    before = load(target)
    custom = _validate_custom(partial, before["custom"])
    # None is the deletion marker here too: {"environment": null} clears
    # the field, and the missions read the stack's plain entry.
    if (
        "environment" in partial
        and partial["environment"] is not None
        and not _valid_environment(partial["environment"])
    ):
        raise ValueError(
            "environment must be a kebab-case name"
            f" (^[a-z]([a-z0-9-]*[a-z0-9])?$), never {ENVIRONMENT_SENTINEL!r},"
            f" or null to clear it, got {partial['environment']!r}"
        )
    effective_stack = partial.get("stack", before["stack"])
    removed = {name for name, decl in partial.get("custom", {}).items() if decl is None}
    if effective_stack in removed:
        raise ValueError(
            f"custom.{effective_stack} cannot be removed while it is the"
            " configured stack - switch to another stack first, or in the"
            " same call"
        )
    if (
        "stack" in partial
        and effective_stack not in STACKS
        and effective_stack not in custom
    ):
        raise ValueError(
            f"stack must be one of {list(STACKS)} or a declared custom stack"
            f' (pass custom: {{"<name>": {{"stack_config_fields": [...]}}}}),'
            f" got {partial['stack']!r}"
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
        # None is the deletion marker (issue #112): a null entry removes
        # the stack's whole entry, a null key value removes that key. The
        # entry deletion is accepted for any name - it is how the values
        # of a removed custom declaration get cleaned up (#228).
        if payload is None:
            continue
        resolved = resolve_stack_config_key(stack_key, custom)
        if resolved is None:
            raise ValueError(
                f"stack_config keys must be one of {list(STACKS)} or a declared"
                f" custom stack, optionally prefixed by an environment ({KEY_FORMS}),"
                f" got {stack_key!r}"
            )
        _, stack_of_key = resolved
        allowed = _allowed_fields(stack_of_key, custom)
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
            if not _stack_config_key_allowed(stack_of_key, key, custom):
                if allowed:
                    raise ValueError(
                        f"stack_config.{stack_key} accepts only "
                        f"{sorted(allowed)}, got unknown key {key!r}"
                    )
                raise ValueError(
                    f"stack_config.{stack_key} does not persist any fields,"
                    f" got unknown key {key!r}"
                )

    effective_local = {**before["local"], **local_partial}
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
    if "environment" in partial:
        if partial["environment"] is None:
            stored.pop("environment", None)
        else:
            stored["environment"] = partial["environment"]
    if local_partial:
        stored_local = stored.get("local")
        stored["local"] = {
            **(stored_local if isinstance(stored_local, dict) else {}),
            **local_partial,
        }
    custom_partial = partial.get("custom", {})
    if custom_partial:
        stored_custom = stored.get("custom")
        stored_custom = stored_custom if isinstance(stored_custom, dict) else {}
        for name, declaration in custom_partial.items():
            if declaration is None:
                stored_custom.pop(name, None)
            else:
                # A re-declaration replaces the list: the file changed.
                stored_custom[name] = custom[name]
        stored["custom"] = stored_custom
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
