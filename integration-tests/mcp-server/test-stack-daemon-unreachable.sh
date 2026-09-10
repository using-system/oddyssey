#!/usr/bin/env bash
# Issue #521: with the Docker daemon unreachable, the tools must refuse
# fast with the one-line remedy instead of hanging until the MCP timeout.
# No real Docker needed: DOCKER_HOST points at a socket nothing listens
# on, and the env override reaches the server through the inspector CLI
# exactly like every other mcp_call below.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

# A socket nothing listens on: the CLI fails fast with its own
# cannot-connect error, which the server classifies as daemon-down.
export DOCKER_HOST="unix:///tmp/oddyssey-definitely-dead.sock"

step "odd_stack_status reports the daemon, not a timeout"
mcp_call odd_stack_status > "$workdir/status-dead.json"
assert_result_contains "$workdir/status-dead.json" '"running": false'
assert_result_contains "$workdir/status-dead.json" '"daemon": "unreachable"'
assert_result_contains "$workdir/status-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"

step "odd_stack_up refuses with the same remedy"
mcp_call odd_stack_up > "$workdir/up-dead.json" 2> "$workdir/up-dead.stderr" || true
assert_result_contains "$workdir/up-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"

echo "stack daemon unreachable: OK"
