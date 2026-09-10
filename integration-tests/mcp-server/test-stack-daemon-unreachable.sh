#!/usr/bin/env bash
# Issue #521: with the Docker daemon unreachable, the tools must refuse
# fast with the one-line remedy instead of hanging until the MCP timeout.
# No real Docker needed: DOCKER_HOST points at a socket nothing listens
# on. The env override travels through the inspector's `-e` flag: the
# inspector inherits only a sudo-like env allowlist (HOME/PATH/...), so
# a plain `export DOCKER_HOST=...` never reaches the server subprocess.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

# A socket nothing listens on: the CLI fails fast with its own
# cannot-connect error, which the server classifies as daemon-down.
dead_host="unix:///tmp/oddyssey-definitely-dead.sock"

# mcp_call_dead <tool> -> runs the tool with DOCKER_HOST forced to the
# dead socket through the inspector's -e flag (the only env route that
# reaches the server subprocess).
mcp_call_dead() {
  npx -y "@modelcontextprotocol/inspector@${INSPECTOR_VERSION}" --cli \
    "$SERVER_BIN" --method tools/call --tool-name "$1" \
    -e "DOCKER_HOST=${dead_host}"
}

step "odd_stack_status reports the daemon, not a timeout"
mcp_call_dead odd_stack_status > "$workdir/status-dead.json"
assert_result_contains "$workdir/status-dead.json" '"running": false'
assert_result_contains "$workdir/status-dead.json" '"daemon": "unreachable"'
assert_result_contains "$workdir/status-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"

step "odd_stack_up refuses with the same remedy"
mcp_call_dead odd_stack_up > "$workdir/up-dead.json" 2> "$workdir/up-dead.stderr" || true
# The tool result is an isError whose content carries the one-line
# remedy; the inspector CLI surfaces that content on stderr as
# "Tool '...' failed: ..." and an isError envelope on stdout.
grep -q 'tool_is_error' "$workdir/up-dead.json" \
  || { echo "ASSERTION FAILED: up-dead.json is not a tool error" >&2; cat "$workdir/up-dead.json" >&2; exit 1; }
grep -q "the Docker daemon does not answer - restart Docker Desktop and retry" "$workdir/up-dead.stderr" \
  || { echo "ASSERTION FAILED: remedy missing from up-dead.stderr" >&2; cat "$workdir/up-dead.stderr" >&2; exit 1; }

echo "stack daemon unreachable: OK"