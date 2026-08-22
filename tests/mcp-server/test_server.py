import asyncio

from oddyssey_mcp import server

EXPECTED_TOOLS = {
    "odd_stack_up",
    "odd_stack_down",
    "odd_stack_status",
    "odd_stack_reset",
}


def test_all_stack_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_tools_have_descriptions():
    tools = asyncio.run(server.mcp.list_tools())
    assert all(tool.description for tool in tools)


def test_sdk_otel_middleware_removed():
    # mcp 2.0 installs its own OpenTelemetryMiddleware by default, which
    # duplicated every tool span (observation report finding 1). The
    # branch's decorator span is canonical; the SDK middleware must be gone.
    assert not any(
        type(m).__name__ == "OpenTelemetryMiddleware" for m in server.mcp.middleware
    )
