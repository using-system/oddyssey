import asyncio

from oddyssey_mcp import server

EXPECTED_TOOLS = {
    "odd_stack_up",
    "odd_stack_down",
    "odd_stack_status",
}


def test_all_stack_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_tools_have_descriptions():
    tools = asyncio.run(server.mcp.list_tools())
    assert all(tool.description for tool in tools)
