#!/usr/bin/env bash
# Global configuration end to end (#59): a port change through
# odd_config_set auto-resets the stack onto the new ports, Grafana and
# OTLP answer there, and defaults are restored afterwards. The config
# file is backed up/restored so a developer machine is left untouched.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
CONFIG_FILE="$HOME/.oddyssey/config.json"
GRAFANA_READY_PATH="/api/datasources/proxy/uid/prometheus/-/ready"
config_backup="$workdir/config.json.bak"
had_config=0
ports_moved=0

# The configuration is user-scoped machine state, so every exit path -
# success, failed assertion, interrupt - has to put it back. The backup
# lives in the workdir, hence it is restored BEFORE the workdir is wiped.
restore() {
  if [ "$had_config" = 1 ]; then
    mv -f "$config_backup" "$CONFIG_FILE" 2>/dev/null || true
  else
    rm -f "$CONFIG_FILE"
  fi
  # Bailed out while the stack was on the test ports: destroy the container
  # so nothing keeps them bound and no container survives that contradicts
  # the configuration just restored above.
  if [ "$ports_moved" = 1 ]; then
    docker rm --force --volumes oddyssey-lgtm > /dev/null 2>&1 || true
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

# Start from the defaults - the assertions below describe a machine with no
# stored configuration, which is what CI has and what the backup lets us
# hand back to a developer unchanged.
rm -f "$CONFIG_FILE"

# http_code <url> [curl-arg...] - status of the request, "000" when nothing
# answers. curl exits non-zero on a refused connection and that must not
# kill the script under set -e: here the code itself IS the assertion.
http_code() {
  local url="$1"; shift
  curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@" "$url" || true
}

step "start the stack on default ports"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up.json"
assert_result_contains "$workdir/up.json" '"running": true'

step "odd_config_get returns the defaults"
mcp_call odd_config_get > "$workdir/get.json"
assert_result_contains "$workdir/get.json" '"grafana_port": 3000'
assert_result_contains "$workdir/get.json" '"stack": "grafana"'

step "changing the ports auto-resets the stack onto them"
ports_moved=1
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_config_set \
  'config={"local":{"grafana_port":3300,"otlp_http_port":4418}}' > "$workdir/set.json"
assert_result_contains "$workdir/set.json" '"grafana_port": 3300'
assert_result_contains "$workdir/set.json" '"otlp_http_port": 4418'
# A container was present, so the change wiped it: the embedded reset result
# is what makes that machine-wide destruction visible to the caller.
assert_result_contains "$workdir/set.json" 'services_wiped'
test "$(http_code "http://localhost:3300$GRAFANA_READY_PATH")" = "200"
test "$(http_code "http://localhost:3000$GRAFANA_READY_PATH")" != "200"

step "OTLP ingest answers on the configured port"
# An empty resourceLogs list is a valid OTLP/HTTP request, so a 2xx proves
# the collector - not just Grafana - is published on the configured port.
otlp_code=$(http_code "http://localhost:4418/v1/logs" \
  -X POST -H 'Content-Type: application/json' -d '{"resourceLogs":[]}')
case "$otlp_code" in
  200 | 204) ;;
  *) echo "ASSERTION FAILED: OTLP on 4418 answered $otlp_code" >&2; exit 1 ;;
esac

step "restoring the default ports auto-resets back"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_config_set \
  'config={"local":{"grafana_port":3000,"otlp_http_port":4318}}' > "$workdir/restore.json"
assert_result_contains "$workdir/restore.json" '"grafana_port": 3000'
test "$(http_code "http://localhost:3000$GRAFANA_READY_PATH")" = "200"
ports_moved=0

step "tear down"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

echo "stack config: OK"
