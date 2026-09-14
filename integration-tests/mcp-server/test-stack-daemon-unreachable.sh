#!/usr/bin/env bash
# Issue #521: with the Docker daemon unreachable, the tools must refuse
# fast with the one-line remedy instead of hanging until the MCP timeout.
# Issue #537: the remedy keeps the CLI's own diagnosis, and a port change
# refused on a dead daemon leaves the configuration untouched.
# No real Docker needed: DOCKER_HOST points at a socket nothing listens
# on. The env override travels through lib.sh's mcp_call_env (the
# inspector's `-e` flag): the inspector inherits only a sudo-like env
# allowlist (HOME/PATH/...), so a plain `export DOCKER_HOST=...` never
# reaches the server subprocess.
# The config file is backed up/restored so a developer machine is left
# untouched even if a refused port change were to persist again.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
CONFIG_FILE="$HOME/.oddyssey/config.json"
config_backup="$workdir/config.json.bak"
had_config=0

# The configuration is user-scoped machine state, so every exit path -
# success, failed assertion, interrupt - has to put it back. The backup
# lives in the workdir, hence it is restored BEFORE the workdir is wiped.
restore() {
  if [ "$had_config" = 1 ]; then
    mv -f "$config_backup" "$CONFIG_FILE" 2>/dev/null || true
  else
    rm -f "$CONFIG_FILE"
  fi
  rm -rf "$workdir"
}
if [ -f "$CONFIG_FILE" ]; then
  cp "$CONFIG_FILE" "$config_backup"
  had_config=1
fi
trap restore EXIT
# A signal must clean up too: exiting from the handler is what fires EXIT.
trap 'exit 130' INT
trap 'exit 143' TERM

# Start from the defaults: the port-change step below asserts the
# default Grafana port survives the refusal.
rm -f "$CONFIG_FILE"

# A socket nothing listens on: the CLI fails fast with its own
# cannot-connect error, which the server classifies as daemon-down.
dead_host="unix:///tmp/oddyssey-definitely-dead.sock"

step "odd_stack_status reports the daemon, not a timeout"
mcp_call_env odd_stack_status "DOCKER_HOST=${dead_host}" -- > "$workdir/status-dead.json"
assert_result_contains "$workdir/status-dead.json" '"running": false'
assert_result_contains "$workdir/status-dead.json" '"daemon": "unreachable"'
assert_result_contains "$workdir/status-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"

step "the remedy carries the docker CLI's own diagnosis (#537)"
# The CLI's first stderr line rides along in parentheses; its wording
# drifts across Docker versions, so only the shape is asserted: the
# tail opens, and it is never empty.
assert_result_contains "$workdir/status-dead.json" \
  "restart Docker Desktop and retry (docker: "
jq -e '.content[0].text | contains("(docker: )") | not' "$workdir/status-dead.json" > /dev/null \
  || { echo "ASSERTION FAILED: status-dead.json carries an empty docker diagnosis" >&2; cat "$workdir/status-dead.json" >&2; exit 1; }

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

step "odd_config_set refuses a port change and persists nothing (#537)"
# The reset a port change owes needs the daemon: the refusal comes
# BEFORE the write, so the configuration read back is untouched - a
# change persisted first would apply silently on the retry.
mcp_call_env odd_config_set "DOCKER_HOST=${dead_host}" -- \
  'config={"local":{"grafana_port":3300}}' > "$workdir/config-dead.json" || true
jq -e '.isError == true' "$workdir/config-dead.json" > /dev/null \
  || { echo "ASSERTION FAILED: config-dead.json is not a tool error" >&2; cat "$workdir/config-dead.json" >&2; exit 1; }
assert_result_contains "$workdir/config-dead.json" \
  "the Docker daemon does not answer - restart Docker Desktop and retry"
mcp_call_env odd_config_get "DOCKER_HOST=${dead_host}" -- > "$workdir/config-after.json"
assert_result_contains "$workdir/config-after.json" '"grafana_port": 3000'
jq -e '.content[0].text | contains("3300") | not' "$workdir/config-after.json" > /dev/null \
  || { echo "ASSERTION FAILED: the refused port change was persisted" >&2; cat "$workdir/config-after.json" >&2; exit 1; }

echo "stack daemon unreachable: OK"
