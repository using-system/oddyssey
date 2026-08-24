#!/usr/bin/env bash
# env passthrough and the embedded delta default (#34/#43): a delta-
# temporality sum is stored out of the box, odd_stack_reset forwards env
# to the recreated container, and odd_stack_up on an existing container
# truthfully reports env_applied: false.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

PROM_QUERY_URL="http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query"

step "start the stack"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up.json"
assert_result_contains "$workdir/up.json" '"running": true'

step "a delta-temporality sum is stored (embedded delta-to-cumulative default)"
NOW=$(($(date +%s) * 1000000000))
curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:4318/v1/metrics \
  -H 'Content-Type: application/json' \
  -d '{"resourceMetrics":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"delta-proof"}}]},"scopeMetrics":[{"metrics":[{"name":"oddyssey_delta_proof_total","sum":{"aggregationTemporality":1,"isMonotonic":true,"dataPoints":[{"asInt":"7","startTimeUnixNano":"'"$((NOW - 60000000000))"'","timeUnixNano":"'"$NOW"'"}]}}]}]}]}' \
  | grep -qE "200|204"
for _ in $(seq 1 15); do
  HITS=$(curl -s -G "$PROM_QUERY_URL" --data-urlencode "query=oddyssey_delta_proof_total" \
    | jq '.data.result | length' || echo 0)
  [ "$HITS" -ge 1 ] && break
  sleep 2
done
test "$HITS" -ge 1

step "odd_stack_up with env on the existing container reports env_applied: false"
mcp_call odd_stack_up 'env={"GF_LOG_LEVEL":"debug"}' > "$workdir/up-env.json"
assert_result_contains "$workdir/up-env.json" '"env_applied": false'

step "odd_stack_reset forwards env to the recreated container"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_reset 'env={"GF_LOG_LEVEL":"debug"}' > "$workdir/reset.json"
assert_result_contains "$workdir/reset.json" '"env_applied": true'
docker inspect oddyssey-lgtm --format '{{json .Config.Env}}' | grep -q '"GF_LOG_LEVEL=debug"'
docker inspect oddyssey-lgtm --format '{{json .Config.Env}}' \
  | grep -q '"PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative"'

step "tear down"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

echo "stack env: OK"
