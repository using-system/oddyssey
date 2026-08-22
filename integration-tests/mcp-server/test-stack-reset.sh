#!/usr/bin/env bash
# odd_stack_reset wipes stored telemetry: inject a log via OTLP, see it in
# Loki through the Grafana proxy, reset, verify it is gone and the stack is
# ready again.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

LOKI_QUERY_URL="http://localhost:3000/api/datasources/proxy/uid/loki/loki/api/v1/query_range"
MARKER="oddyssey-reset-proof"

loki_hits() {
  curl -s -G "$LOKI_QUERY_URL" \
    --data-urlencode "query={service_name=\"reset-proof\"} |= \"$MARKER\"" \
    --data-urlencode "start=$((($(date +%s) - 600) * 1000000000))" \
    --data-urlencode "end=$(($(date +%s) * 1000000000))" \
    | jq '[.data.result[].values[]] | length'
}

step "start the stack"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up.json"
assert_result_contains "$workdir/up.json" '"running": true'

step "inject a log record via OTLP HTTP"
now_ns=$(($(date +%s) * 1000000000))
curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:4318/v1/logs \
  -H 'Content-Type: application/json' \
  -d '{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"reset-proof"}}]},"scopeLogs":[{"logRecords":[{"timeUnixNano":"'"$now_ns"'","severityText":"INFO","body":{"stringValue":"'"$MARKER"'"}}]}]}]}' \
  | grep -qE "200|204"

step "the log is queryable in Loki"
for _ in $(seq 1 30); do
  [ "$(loki_hits)" -ge 1 ] && break
  sleep 2
done
test "$(loki_hits)" -ge 1

step "odd_stack_reset returns a fresh, ready stack"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_reset > "$workdir/reset.json"
assert_result_contains "$workdir/reset.json" '"running": true'

step "the previous telemetry is gone"
test "$(loki_hits)" -eq 0

step "tear down"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

echo "stack reset: OK"
