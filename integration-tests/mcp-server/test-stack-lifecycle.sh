#!/usr/bin/env bash
# Full stack lifecycle through the MCP client only:
# tools exposed -> status down -> up (pull + startup inside the tool call)
# -> status up -> down -> status down.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

step "the stack and config tools are exposed"
mcp_list_tools > "$workdir/tools.json"
jq -e '[.tools[].name] | sort == ["odd_config_get", "odd_config_set", "odd_stack_down", "odd_stack_reset", "odd_stack_status", "odd_stack_up"]' \
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
# Issue #118: a running stack also reports the container's identity, so a
# report's instance fields need no docker inspect on the caller's side. The
# tag is matched by prefix, not by the exact pin, so a bump stays green.
jq -e '.content[0].text | fromjson
       | ((.image | type) == "string" and (.image | startswith("grafana/otel-lgtm:")))
         and (.created | type) == "string"
         and (.started | type) == "string"' \
  "$workdir/status-up.json" > /dev/null

step "odd_stack_down stops it"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

step "odd_stack_status confirms it is down"
mcp_call odd_stack_status > "$workdir/status-final.json"
assert_result_contains "$workdir/status-final.json" '"running": false'
# The container is gone, so its identity goes with it - null, never a stale
# tag left over from the container that just got destroyed.
jq -e '.content[0].text | fromjson | .image == null' \
  "$workdir/status-final.json" > /dev/null

echo "stack lifecycle: OK"
