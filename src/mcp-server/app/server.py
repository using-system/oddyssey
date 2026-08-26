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
    """Check whether the local LGTM stack is up (Prometheus, Tempo, Loki, and Pyroscope ready)."""
    return stack_ops.stack_status()


@mcp.tool()
@telemetry.traced_tool
def odd_stack_reset(env: dict[str, str] | None = None) -> dict:
    """Wipe ALL stored telemetry (traces, metrics, logs, profiles) and return a fresh, ready stack.

    env adds environment variables to the recreated container (see
    odd_stack_up); unlike on up, a reset always recreates, so env always
    applies.

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
    """Read the global oddyssey configuration: the configured stack (local, or a remote backend) and the local stack host ports (defaults applied; invalid stored values are listed in invalid_ignored)."""
    return config_ops.load()


@mcp.tool()
@telemetry.traced_tool
def odd_config_set(config: dict) -> dict:
    """Update the global oddyssey configuration (partial merge).

    config example: {"stack": "datadog"} or {"local": {"grafana_port": 3300}}.
    stack is one of: local (the local stack - the default), grafana (a
    REMOTE Grafana - the CLI context says which instance), azure-monitor,
    cloudwatch, datadog, dynatrace, splunk. Switching to the local stack
    is {"stack": "local"}. Changing a port while a stack container exists
    RESETS the stack immediately so the configuration is always applied:
    this WIPES all stored telemetry machine-wide (the result embeds the
    reset outcome, including
    services_wiped). The auto-reset carries the old container's user-set
    environment forward to the recreated one, best-effort: the result's
    env_preserved field lists the carried variable names (never values). If
    reading the old container failed, env_preserved is empty and nothing was
    carried - re-run odd_stack_reset with the desired env to reapply it.
    The MCP server's own telemetry export honors a
    changed OTLP port only after the MCP server restarts, and applications
    configured against the old ports keep exporting to them - their
    OTEL_EXPORTER_OTLP_ENDPOINT must be updated to the new otlp_endpoint.
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
        # old config still matches and the guard passes. Best-effort like the
        # reset's own pre-boot: a container too broken to boot is still wiped.
        try:
            stack_ops.stack_up()
        except RuntimeError:
            pass
    effective = config_ops.save(config)
    result: dict = {"config": effective}
    if effective["local"] != ports_before and state_before != "absent":
        # Read the doomed container's user env BEFORE the reset destroys
        # it, and hand it to the recreation (issue #62).
        preserved = stack_ops.container_user_env()
        result["stack_reset"] = stack_ops.stack_reset(preserved)
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
