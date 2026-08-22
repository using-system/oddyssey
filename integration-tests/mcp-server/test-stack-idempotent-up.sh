#!/usr/bin/env bash
# odd_stack_up is idempotent: calling it while the stack already runs
# succeeds without disturbing the running container.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

step "start the stack"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up-first.json"
assert_result_contains "$workdir/up-first.json" '"running": true'

step "odd_stack_up again on the running stack succeeds"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up-again.json"
assert_result_contains "$workdir/up-again.json" '"running": true'

step "the stack is still up"
mcp_call odd_stack_status > "$workdir/status.json"
assert_result_contains "$workdir/status.json" '"running": true'

step "tear down"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

echo "idempotent up: OK"
