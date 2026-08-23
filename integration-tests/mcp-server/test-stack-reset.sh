#!/usr/bin/env bash
# odd_stack_reset wipes stored telemetry: inject a log via OTLP, see it in
# Loki through the Grafana proxy, reset, verify it is gone and the stack is
# ready again.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

LOKI_QUERY_URL="http://localhost:3000/api/datasources/proxy/uid/loki/loki/api/v1/query_range"
# Distinct, non-overlapping markers: the "gone" check uses a substring
# filter, so the canary must not contain the pre-reset marker.
MARKER="oddyssey-proof-before-reset"
CANARY="oddyssey-proof-after-reset"

# loki_hits <marker> - count of log lines carrying the marker
loki_hits() {
  curl -s -G "$LOKI_QUERY_URL" \
    --data-urlencode "query={service_name=\"reset-proof\"} |= \"$1\"" \
    --data-urlencode "start=$((($(date +%s) - 600) * 1000000000))" \
    --data-urlencode "end=$((($(date +%s) + 1) * 1000000000))" \
    | jq '[.data.result[].values[]] | length'
}

# inject_log <marker> - push one OTLP log record for service reset-proof
inject_log() {
  curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:4318/v1/logs \
    -H 'Content-Type: application/json' \
    -d '{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"reset-proof"}}]},"scopeLogs":[{"logRecords":[{"timeUnixNano":"'"$(($(date +%s) * 1000000000))"'","severityText":"INFO","body":{"stringValue":"'"$1"'"}}]}]}]}' \
    | grep -qE "200|204"
}

# wait_for_hits <marker> - poll until the marker is queryable
wait_for_hits() {
  for _ in $(seq 1 30); do
    [ "$(loki_hits "$1")" -ge 1 ] && return 0
    sleep 2
  done
  return 1
}

step "start the stack"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up.json"
assert_result_contains "$workdir/up.json" '"running": true'

step "inject a log record via OTLP HTTP"
inject_log "$MARKER"

step "the log is queryable in Loki"
wait_for_hits "$MARKER"

step "odd_stack_reset returns a fresh, ready stack"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_reset > "$workdir/reset.json"
assert_result_contains "$workdir/reset.json" '"running": true'

step "the reset names the services it wiped (issue #35)"
assert_result_contains "$workdir/reset.json" 'services_wiped'
assert_result_contains "$workdir/reset.json" 'reset-proof'

step "the OTLP->Loki pipeline is live again (post-reset canary)"
inject_log "$CANARY"
wait_for_hits "$CANARY"

step "the previous telemetry is gone"
test "$(loki_hits "$MARKER")" -eq 0

step "tear down"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

echo "stack reset: OK"
