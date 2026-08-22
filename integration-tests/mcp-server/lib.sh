# Shared helpers for the mcp-server integration tests.
# Every interaction with the server goes through the official MCP Inspector
# CLI over stdio - no side channel - so the server's autonomy is what gets
# tested.

set -euo pipefail

INSPECTOR_VERSION="${INSPECTOR_VERSION:-2.3.0}"
SERVER_BIN="${SERVER_BIN:-src/mcp-server/.venv/bin/oddyssey-mcp}"

# mcp_list_tools -> JSON of tools/list on stdout
mcp_list_tools() {
  npx -y @modelcontextprotocol/inspector@"$INSPECTOR_VERSION" --cli \
    "$SERVER_BIN" --method tools/list
}

# mcp_call <tool-name> -> JSON of tools/call on stdout
mcp_call() {
  npx -y @modelcontextprotocol/inspector@"$INSPECTOR_VERSION" --cli \
    "$SERVER_BIN" --method tools/call --tool-name "$1"
}

# assert_result_contains <json-file> <substring> - checks the tool result text
assert_result_contains() {
  jq -e --arg needle "$2" '.content[0].text | contains($needle)' "$1" > /dev/null \
    || { echo "ASSERTION FAILED: $(basename "$1") does not contain: $2" >&2; cat "$1" >&2; exit 1; }
}

step() {
  echo "==> $*"
}
