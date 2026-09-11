#!/usr/bin/env bash
# Issue #521: with the Docker daemon unreachable, the tools must refuse
# fast with the one-line remedy instead of hanging until the MCP timeout.
# No real Docker needed: DOCKER_HOST points at a socket nothing listens
# on. The env override travels through lib.sh's mcp_call_env (the
# inspector's `-e` flag): the inspector inherits only a sudo-like env
# allowlist (HOME/PATH/...), so a plain `export DOCKER_HOST=...` never
# reaches the server subprocess.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

# A socket nothing listens on: the CLI fails fast with its own
# cannot-connect error, which the server classifies as daemon-down.
dead_host="unix:///tmp/oddyssey-definitely-dead.sock"

step "odd_stack_status reports the daemon, not a timeout"
mcp_call_env odd_stack_status "DOCKER_HOST=${dead_host}" -- > "$workdir/status-dead.json"
assert_result_contains "$workdir/status-dead.json" '"running": false'
assert_result_contains "$workdir/status-dead.json" '"daemon": "unreachable"'
assert_result_contains "$workdir/status-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"

step "odd_stack_up refuses with the same remedy"
mcp_call_env odd_stack_up "DOCKER_HOST=${dead_host}" -- > "$workdir/up-dead.json" || true
# The refusal reaches the client as a ToolError: an isError result whose
# content carries the one-line remedy (issue #521's contract - a bare
# RuntimeError would be withheld by the MCP SDK).
jq -e '.isError == true' "$workdir/up-dead.json" > /dev/null \
  || { echo "ASSERTION FAILED: up-dead.json is not a tool error" >&2; cat "$workdir/up-dead.json" >&2; exit 1; }
assert_result_contains "$workdir/up-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"

step "odd_stack_reset refuses with the same remedy (nothing is wiped)"
mcp_call_env odd_stack_reset "DOCKER_HOST=${dead_host}" -- > "$workdir/reset-dead.json" || true
jq -e '.isError == true' "$workdir/reset-dead.json" > /dev/null \
  || { echo "ASSERTION FAILED: reset-dead.json is not a tool error" >&2; cat "$workdir/reset-dead.json" >&2; exit 1; }
assert_result_contains "$workdir/reset-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"

echo "stack daemon unreachable: OK"