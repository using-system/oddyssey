"""The oddyssey MCP server: pilots the local observability stack over stdio."""

from __future__ import annotations

import logging

# mcp 2.0 renamed the high-level server: `mcp.server.fastmcp.FastMCP` is gone,
# the equivalent is `mcp.server.MCPServer` (canonically
# `mcp.server.mcpserver.MCPServer`). The `@server.tool()` decorator and the
# synchronous `run()` entrypoint (transport defaults to "stdio") are unchanged.
from mcp.server import MCPServer

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
