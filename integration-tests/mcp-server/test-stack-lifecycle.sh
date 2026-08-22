#!/usr/bin/env bash
# Full stack lifecycle through the MCP client only:
# tools exposed -> status down -> up (pull + startup inside the tool call)
# -> status up -> down -> status down.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

step "the three stack tools are exposed"
mcp_list_tools > "$workdir/tools.json"
jq -e '[.tools[].name] | sort == ["odd_stack_down", "odd_stack_status", "odd_stack_up"]' \
  "$workdir/tools.json" > /dev/null

step "odd_stack_status reports down before start"
mcp_call odd_stack_status > "$workdir/status-down.json"
assert_result_contains "$workdir/status-down.json" '"running": false'

step "odd_stack_up starts the real stack (pull + startup inside the call)"
# The tool call carries the whole cost on its own; raise the client timeout.
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up.json"
assert_result_contains "$workdir/up.json" '"running": true'

step "odd_stack_status confirms it is up"
mcp_call odd_stack_status > "$workdir/status-up.json"
assert_result_contains "$workdir/status-up.json" '"running": true'

step "odd_stack_down stops it"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

step "odd_stack_status confirms it is down"
mcp_call odd_stack_status > "$workdir/status-final.json"
assert_result_contains "$workdir/status-final.json" '"running": false'

echo "stack lifecycle: OK"
