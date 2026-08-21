"""The oddyssey MCP server: ODD measurement tools over stdio."""

from __future__ import annotations

import time

# mcp 2.0 renamed the high-level server: `mcp.server.fastmcp.FastMCP` is gone,
# the equivalent is `mcp.server.MCPServer` (canonically
# `mcp.server.mcpserver.MCPServer`). The `@server.tool()` decorator and the
# synchronous `run()` entrypoint (transport defaults to "stdio") are unchanged.
from mcp.server import MCPServer

from oddyssey_summarize.report import summarize

from . import baseline as baseline_store
from . import stack as stack_ops
from .budget import load_budget
from .diff import build_diff

mcp = MCPServer("oddyssey")


@mcp.tool()
def odd_stack_up() -> dict:
    """Start the local LGTM observability stack (Grafana, Tempo, Prometheus, OTLP)."""
    return stack_ops.stack_up()


@mcp.tool()
def odd_stack_down() -> dict:
    """Stop the local LGTM observability stack."""
    return stack_ops.stack_down()


@mcp.tool()
def odd_stack_status() -> dict:
    """Check whether the local LGTM stack is up (Prometheus and Tempo ready)."""
    return stack_ops.stack_status()


def _window(window_seconds: int) -> tuple[int, int]:
    end = int(time.time())
    return end - window_seconds, end


@mcp.tool()
def odd_summarize(service: str, window_seconds: int = 900) -> dict:
    """Summarize a service's telemetry over the last window_seconds: p95, requests, errors, DB spans, top spans."""
    start, end = _window(window_seconds)
    return summarize(service, start, end)


@mcp.tool()
def odd_baseline(service: str, window_seconds: int = 900) -> dict:
    """Measure the service and store the report as the baseline for later odd_diff calls."""
    start, end = _window(window_seconds)
    report = summarize(service, start, end)
    path = baseline_store.save_baseline(report)
    return {"baseline_path": str(path), "report": report}


@mcp.tool()
def odd_diff(service: str, window_seconds: int = 900) -> dict:
    """Measure the service now, compare against the stored baseline, and give a budget verdict."""
    stored = baseline_store.load_baseline()
    start, end = _window(window_seconds)
    current = summarize(service, start, end)
    return build_diff(stored, current, load_budget())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
