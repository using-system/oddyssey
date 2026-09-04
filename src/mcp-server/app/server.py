"""The oddyssey MCP server: pilots the local observability stack over stdio."""

from __future__ import annotations

import logging

# mcp 2.0 renamed the high-level server: `mcp.server.fastmcp.FastMCP` is gone,
# the equivalent is `mcp.server.MCPServer` (canonically
# `mcp.server.mcpserver.MCPServer`). The `@server.tool()` decorator and the
# synchronous `run()` entrypoint (transport defaults to "stdio") are unchanged.
from mcp.server import MCPServer

from . import config as config_ops
from . import stack as stack_ops
from . import telemetry

mcp = MCPServer("oddyssey")

# mcp 2.0 ships its own OpenTelemetryMiddleware on by default, which would
# duplicate every tool span (and double the spanmetrics counts). The
# decorator span below is the canonical one - the spec froze its contract,
# and the SDK marks its middleware API as subject to change before v2
# final. Defensive: if the SDK moves the class, keep the duplicates rather
# than crash the server.
try:
    from mcp.server._otel import OpenTelemetryMiddleware

    mcp.middleware[:] = [
        m for m in mcp.middleware if not isinstance(m, OpenTelemetryMiddleware)
    ]
except Exception:  # noqa: BLE001, S110 - degraded telemetry beats a dead server
    pass


@mcp.tool()
@telemetry.traced_tool
def odd_stack_up(env: dict[str, str] | None = None) -> dict:
    """Start the local LGTM observability stack (Grafana, Tempo, Prometheus, Loki, Pyroscope, OTLP).

    env adds environment variables to the container - the otel-lgtm image is
    configured exclusively through them (PROMETHEUS_EXTRA_ARGS,
    LOKI_EXTRA_ARGS, TEMPO_EXTRA_ARGS, GF_*, ...); explicit entries override
    the embedded defaults. Docker only applies env at container creation: when
    a container already exists the result carries env_applied: false and the
    requested env is NOT active - run odd_stack_reset with the same env to
    apply it (destroys stored telemetry).

    A creation persists the applied env into stack_config.local and reapplies
    what is persisted there (explicit entries win), so a creation-time choice
    survives later recreations without repeating it. Credential-named
    variables (headers, tokens, secrets, passwords) are applied but never
    persisted - the result's env_reapplied / env_persisted /
    env_not_persisted fields say exactly what happened; remove a persisted
    variable with odd_config_set's null deletion.
    """
    return stack_ops.stack_up(env)


@mcp.tool()
@telemetry.traced_tool
def odd_stack_down() -> dict:
    """Stop and remove the local LGTM stack; stored telemetry does not survive. The stack is shared by every project on this machine, so their data is destroyed too."""
    return stack_ops.stack_down()


@mcp.tool()
@telemetry.traced_tool
def odd_stack_status() -> dict:
    """Check whether the local LGTM stack is up (Prometheus, Tempo, Loki, and Pyroscope ready) - plus the container's identity: image tag, created/started timestamps, and user-set env (credential-named values redacted to null, all four null when there is no container)."""
    return stack_ops.stack_status()


@mcp.tool()
@telemetry.traced_tool
def odd_stack_reset(env: dict[str, str] | None = None) -> dict:
    """Wipe ALL stored telemetry (traces, metrics, logs, profiles) and return a fresh, ready stack.

    env adds environment variables to the recreated container (see
    odd_stack_up); unlike on up, a reset always recreates, so env always
    applies. The recreation reapplies the env persisted in
    stack_config.local and persists the explicit non-credential entries it
    applied (odd_stack_up's creation contract), so the reset needs no env
    at all to keep a previously applied configuration.

    The wipe is machine-wide and irreversible: one shared stack per machine, so
    data from every project ever observed on it is destroyed, not just the
    current one. The result's services_wiped field lists the service.name
    values that were stored. If it may contain services outside the current
    project, warn the user before calling this tool.

    services_wiped always includes oddyssey-mcp (this server observes itself
    and exports to the stack it pilots) and otelcol-contrib (the embedded
    collector's own metrics): those two are never another project's leftover
    state - only other names are.
    """
    return stack_ops.stack_reset(env)


@mcp.tool()
@telemetry.traced_tool
def odd_config_get() -> dict:
    """Read the global oddyssey configuration: the configured stack (local, or a remote backend) and the local stack host ports (defaults applied; invalid stored values are listed in invalid_ignored). Also returns stack_config: per-stack non-secret targeting values (identifiers, names, regions) persisted for each backend."""
    return config_ops.load()


@mcp.tool()
@telemetry.traced_tool
def odd_config_set(config: dict) -> dict:
    """Update the global oddyssey configuration (partial merge).

    config example: {"stack": "datadog"} or {"local": {"grafana_port": 3300}} or
    {"stack_config": {"azure-monitor": {"workspace": "<guid>"}}}.
    stack is one of: local (the local stack - the default), grafana (a
    REMOTE Grafana - the CLI context says which instance), azure-monitor,
    cloudwatch, datadog, dynatrace, splunk - or a custom stack (a backend
    the package does not ship, described by a stack file in the observed
    repository) declared under custom in the same call or an earlier one:
    {"stack": "seq", "custom": {"seq": {"stack_config_fields":
    ["base_url"]}}}. A custom name is kebab-case, never a built-in one; its
    declaration lists the stack_config fields the stack file names (an
    empty list when it persists nothing), and a re-declaration replaces
    the list. The server never reads the stack file - the caller derives
    the declaration from it. Custom declarations survive a switch to a
    built-in stack; {"custom": {"seq": null}} removes one (refused while
    seq is the configured stack, unless the same call switches away).
    Removing a declaration keeps its stack_config values - a later
    re-declaration finds them again - and until then odd_config_get lists
    them as invalid_ignored; {"stack_config": {"seq": null}} clears them.
    Switching to the local stack
    is {"stack": "local"}. Changing a port while a stack container exists
    RESETS the stack immediately so the configuration is always applied:
    this WIPES all stored telemetry machine-wide (the result embeds the
    reset outcome, including
    services_wiped). The auto-reset carries the old container's user-set
    environment forward to the recreated one, best-effort: the result's
    env_preserved field lists the carried variable names (never values). If
    reading the old container failed, env_preserved is empty; the recreation
    still reapplies whatever stack_config.local persists, so only
    never-persisted variables (credential-named ones) are lost - re-run
    odd_stack_reset with the desired env to reapply those. The auto-reset
    applies the carried env without re-persisting it, so a variable
    deleted with null in this same call stays deleted across the port
    change.
    The MCP server's own telemetry export honors a
    changed OTLP port only after the MCP server restarts, and applications
    configured against the old ports keep exporting to them - their
    OTEL_EXPORTER_OTLP_ENDPOINT must be updated to the new otlp_endpoint.
    stack_config is merged per stack (other stacks' payloads are untouched)
    and never boots or resets the stack container; values must be non-secret
    scalars - credentials stay in the CLI's own auth store, referenced by
    name only. Each stack accepts only its own documented field set (e.g.
    azure-monitor: subscription, resource_group, workspace,
    app_insights_app; grafana/datadog/dynatrace/splunk: none, their CLI
    context carries targeting; a custom stack: its declared list) - an
    undocumented key is rejected, writing nothing, EXCEPT as a null deletion, which is always accepted so a
    stray key can still be cleaned up. local is the one exception: its
    keys are otel-lgtm container env var names, an open set. null deletes:
    {"stack_config": {"azure-monitor": {"workspace":
    null}}} removes that key (the last deletion leaves the entry present but
    empty - "not configured"), {"stack_config": {"azure-monitor": null}}
    removes the stack's entry entirely; a deletion never boots or resets the
    container either.
    """
    ports_before = config_ops.load()["local"]
    state_before = stack_ops._container_state()
    # Read on the RAW partial, before save validates it: a malformed one
    # is left to save's ValueError contract (isinstance, so this read never
    # raises first), at worst after a wasted boot - booting is idempotent.
    local_partial = config.get("local")
    will_change_ports = isinstance(local_partial, dict) and any(
        ports_before.get(key) != value for key, value in local_partial.items()
    )
    if will_change_ports and state_before == "stopped":
        # Boot a stopped container BEFORE the write: once the new ports are
        # saved they diverge from the container's, the reset's pre-boot then
        # trips the mismatch guard, and the pre-wipe enumeration would report
        # services_wiped: [] over real data (#35 contract). Booted now, the
        # container is still enumerable. Best-effort like the
        # reset's own pre-boot: a container too broken to boot is still wiped.
        try:
            # check_ports=False like the reset's own pre-boot: a
            # pre-change container mismatching a newly added named port
            # (issue #224) must still be booted to stay enumerable.
            stack_ops.stack_up(check_ports=False)
        except RuntimeError:
            pass
    effective = config_ops.save(config)
    result: dict = {"config": effective}
    if effective["local"] != ports_before and state_before != "absent":
        # Read the doomed container's user env BEFORE the reset destroys
        # it, and hand it to the recreation (issue #62).
        preserved = stack_ops.container_user_env()
        # persist=False: the carried env is what the container happens to
        # run right now, not a fresh caller choice - re-persisting it
        # would rewrite variables this very call may have deleted with
        # null, resurrecting them on the next recreation.
        result["stack_reset"] = stack_ops.stack_reset(preserved, persist=False)
        result["env_preserved"] = sorted(preserved or {})
    return result


def main() -> None:
    # The mcp SDK configures INFO logging, which lets httpx announce every
    # readiness probe on stderr (28 lines per observed session). Quiet the
    # HTTP client loggers; real errors still surface at WARNING+.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    shutdown = telemetry.setup_telemetry()
    try:
        mcp.run()
    finally:
        shutdown()


if __name__ == "__main__":
    main()
