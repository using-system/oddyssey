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


@mcp.tool()
@telemetry.traced_tool
def odd_stack_up() -> dict:
    """Start the local LGTM observability stack (Grafana, Tempo, Prometheus, Loki, OTLP)."""
    return stack_ops.stack_up()


@mcp.tool()
@telemetry.traced_tool
def odd_stack_down() -> dict:
    """Stop and remove the local LGTM stack; stored telemetry does not survive."""
    return stack_ops.stack_down()


@mcp.tool()
@telemetry.traced_tool
def odd_stack_status() -> dict:
    """Check whether the local LGTM stack is up (Prometheus and Tempo ready)."""
    return stack_ops.stack_status()


@mcp.tool()
@telemetry.traced_tool
def odd_stack_reset() -> dict:
    """Wipe all stored telemetry (traces, metrics, logs, profiles) and return a fresh, ready stack."""
    return stack_ops.stack_reset()


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
