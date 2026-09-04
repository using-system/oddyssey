#!/usr/bin/env bash
# Configuration surface end to end (#172): the stack switch round-trips
# through every allowed value, a rejected partial writes nothing, the
# stack_config contract holds through a real MCP client (merge, null
# deletion of a key and of a whole entry), a custom stack declared by
# the caller (#228) is accepted, validated and removed, and the tolerant read lists
# hand-edited invalid values in invalid_ignored instead of crashing.
# Pure configuration - no stack container is booted, reset, or wiped.
# The config file is backed up/restored so a developer machine is left
# untouched.

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

# Start from the defaults - the assertions below describe a machine with
# no stored configuration, which is what CI has and what the backup lets
# us hand back to a developer unchanged.
rm -f "$CONFIG_FILE"

step "a fresh machine reads pure defaults"
mcp_call odd_config_get > "$workdir/defaults.json"
assert_result_contains "$workdir/defaults.json" '"stack": "local"'
assert_result_contains "$workdir/defaults.json" '"grafana_port": 3000'
assert_result_contains "$workdir/defaults.json" '"pyroscope_port": 4040'
assert_result_contains "$workdir/defaults.json" '"stack_config": {}'

step "the stack switch round-trips through every allowed value"
# The seven values of config.STACKS, ending back on the default so the
# later steps run against the state a fresh machine would have.
for stack in grafana azure-monitor cloudwatch datadog dynatrace splunk local; do
  mcp_call odd_config_set "config={\"stack\":\"$stack\"}" > "$workdir/set-stack.json"
  assert_result_contains "$workdir/set-stack.json" "\"stack\": \"$stack\""
done
mcp_call odd_config_get > "$workdir/after-roundtrip.json"
assert_result_contains "$workdir/after-roundtrip.json" '"stack": "local"'

step "an unknown stack is rejected and writes nothing"
mcp_call odd_config_set 'config={"stack":"narnia"}' > "$workdir/bad-stack.json" || true
grep -q "must be one of" "$workdir/bad-stack.json" \
  || { echo "ASSERTION FAILED: unknown stack was not rejected" >&2; cat "$workdir/bad-stack.json" >&2; exit 1; }
mcp_call odd_config_get > "$workdir/after-bad-stack.json"
assert_result_contains "$workdir/after-bad-stack.json" '"stack": "local"'

step "stack_config merges per stack and per key"
mcp_call odd_config_set \
  'config={"stack_config":{"azure-monitor":{"workspace":"00000000-fake-ws","resource_group":"rg-westeurope"}}}' \
  > "$workdir/sc-seed.json"
assert_result_contains "$workdir/sc-seed.json" '"workspace": "00000000-fake-ws"'
assert_result_contains "$workdir/sc-seed.json" '"resource_group": "rg-westeurope"'
# A second partial on the same stack updates one key and leaves the other
# alone; a partial on another stack leaves the first stack untouched.
mcp_call odd_config_set \
  'config={"stack_config":{"azure-monitor":{"resource_group":"rg-northeurope"},"cloudwatch":{"region":"eu-west-1"}}}' \
  > "$workdir/sc-merge.json"
assert_result_contains "$workdir/sc-merge.json" '"workspace": "00000000-fake-ws"'
assert_result_contains "$workdir/sc-merge.json" '"resource_group": "rg-northeurope"'
assert_result_contains "$workdir/sc-merge.json" '"region": "eu-west-1"'

step "a null key value deletes that key, the rest of the entry survives"
mcp_call odd_config_set \
  'config={"stack_config":{"azure-monitor":{"workspace":null}}}' > "$workdir/sc-del-key.json"
assert_result_contains "$workdir/sc-del-key.json" '"resource_group": "rg-northeurope"'
jq -e '.content[0].text | contains("workspace") | not' "$workdir/sc-del-key.json" > /dev/null \
  || { echo "ASSERTION FAILED: deleted key workspace still present" >&2; cat "$workdir/sc-del-key.json" >&2; exit 1; }

step "deleting the last key leaves the entry present but empty (#112)"
mcp_call odd_config_set \
  'config={"stack_config":{"azure-monitor":{"resource_group":null}}}' > "$workdir/sc-del-last.json"
assert_result_contains "$workdir/sc-del-last.json" '"azure-monitor": {}'

step "a null entry deletes the stack's whole entry"
mcp_call odd_config_set \
  'config={"stack_config":{"azure-monitor":null}}' > "$workdir/sc-del-entry.json"
jq -e '.content[0].text | contains("azure-monitor") | not' "$workdir/sc-del-entry.json" > /dev/null \
  || { echo "ASSERTION FAILED: deleted entry azure-monitor still present" >&2; cat "$workdir/sc-del-entry.json" >&2; exit 1; }
# The untouched stack survives both deletions.
assert_result_contains "$workdir/sc-del-entry.json" '"region": "eu-west-1"'

step "an undocumented key is rejected and writes nothing (#196)"
mcp_call odd_config_set \
  'config={"stack_config":{"azure-monitor":{"tenant":"11111111-1111-1111-1111-111111111111"}}}' \
  > "$workdir/sc-unknown-key.json" || true
grep -q "unknown key" "$workdir/sc-unknown-key.json" \
  || { echo "ASSERTION FAILED: undocumented key was not rejected" >&2; cat "$workdir/sc-unknown-key.json" >&2; exit 1; }
mcp_call odd_config_get > "$workdir/after-unknown-key.json"
jq -e '.content[0].text | contains("tenant") | not' "$workdir/after-unknown-key.json" > /dev/null \
  || { echo "ASSERTION FAILED: rejected partial was written anyway" >&2; cat "$workdir/after-unknown-key.json" >&2; exit 1; }

step "a stack with no documented fields rejects every key (#196)"
mcp_call odd_config_set \
  'config={"stack_config":{"grafana":{"note":"fake-instance"}}}' \
  > "$workdir/sc-no-fields.json" || true
grep -q "does not persist any fields" "$workdir/sc-no-fields.json" \
  || { echo "ASSERTION FAILED: grafana key was not rejected" >&2; cat "$workdir/sc-no-fields.json" >&2; exit 1; }

step "the local stack still accepts arbitrary container env var keys (#196)"
mcp_call odd_config_set \
  'config={"stack_config":{"local":{"GF_LOG_LEVEL":"debug"}}}' > "$workdir/sc-local.json"
assert_result_contains "$workdir/sc-local.json" '"GF_LOG_LEVEL": "debug"'
mcp_call odd_config_set 'config={"stack_config":{"local":null}}' > /dev/null

step "cloudwatch accepts a profile and a separate metrics log group (#207)"
mcp_call odd_config_set \
  'config={"stack_config":{"cloudwatch":{"profile":"myteam","log_group":"/oddyssey-playground/logs","metrics_log_group":"/oddyssey-playground/metrics"}}}' \
  > "$workdir/sc-cloudwatch.json"
assert_result_contains "$workdir/sc-cloudwatch.json" '"profile": "myteam"'
assert_result_contains "$workdir/sc-cloudwatch.json" '"log_group": "/oddyssey-playground/logs"'
assert_result_contains "$workdir/sc-cloudwatch.json" '"metrics_log_group": "/oddyssey-playground/metrics"'
mcp_call odd_config_set 'config={"stack_config":{"cloudwatch":null}}' > /dev/null

step "a non-scalar stack_config value is rejected and writes nothing"
mcp_call odd_config_set \
  'config={"stack_config":{"grafana":{"bad":["a","list"]}}}' > "$workdir/sc-bad.json" || true
grep -q "must be a string, number, boolean, or null" "$workdir/sc-bad.json" \
  || { echo "ASSERTION FAILED: non-scalar value was not rejected" >&2; cat "$workdir/sc-bad.json" >&2; exit 1; }
mcp_call odd_config_get > "$workdir/after-sc-bad.json"
jq -e '.content[0].text | contains("bad") | not' "$workdir/after-sc-bad.json" > /dev/null \
  || { echo "ASSERTION FAILED: rejected partial was written anyway" >&2; cat "$workdir/after-sc-bad.json" >&2; exit 1; }

step "a custom stack needs a declaration - undeclared, the door stays closed (#228)"
mcp_call odd_config_set 'config={"stack":"seq"}' > "$workdir/custom-undeclared.json" || true
grep -q "or a declared custom stack" "$workdir/custom-undeclared.json" \
  || { echo "ASSERTION FAILED: undeclared custom stack was not rejected" >&2; cat "$workdir/custom-undeclared.json" >&2; exit 1; }
mcp_call odd_config_get > "$workdir/after-custom-undeclared.json"
assert_result_contains "$workdir/after-custom-undeclared.json" '"stack": "local"'
assert_result_contains "$workdir/after-custom-undeclared.json" '"custom": {}'

step "a declaration, the switch and a declared value land in one call (#228)"
mcp_call odd_config_set \
  'config={"stack":"seq","custom":{"seq":{"stack_config_fields":["base_url"]}},"stack_config":{"seq":{"base_url":"http://seq.example.test:5341"}}}' \
  > "$workdir/custom-declare.json"
assert_result_contains "$workdir/custom-declare.json" '"stack": "seq"'
assert_result_contains "$workdir/custom-declare.json" '"base_url": "http://seq.example.test:5341"'
jq -e '.content[0].text | fromjson | .config.custom.seq.stack_config_fields == ["base_url"]' \
  "$workdir/custom-declare.json" > /dev/null \
  || { echo "ASSERTION FAILED: declaration not stored" >&2; cat "$workdir/custom-declare.json" >&2; exit 1; }

step "an undeclared field of a custom stack is rejected and writes nothing (#228)"
mcp_call odd_config_set \
  'config={"stack_config":{"seq":{"api_key_name":"SEQ_API_KEY"}}}' > "$workdir/custom-bad-field.json" || true
grep -q "accepts only" "$workdir/custom-bad-field.json" \
  || { echo "ASSERTION FAILED: undeclared custom field was not rejected" >&2; cat "$workdir/custom-bad-field.json" >&2; exit 1; }
mcp_call odd_config_get > "$workdir/after-custom-bad-field.json"
jq -e '.content[0].text | contains("api_key_name") | not' "$workdir/after-custom-bad-field.json" > /dev/null \
  || { echo "ASSERTION FAILED: rejected partial was written anyway" >&2; cat "$workdir/after-custom-bad-field.json" >&2; exit 1; }

step "a built-in name cannot be redeclared (#228)"
mcp_call odd_config_set \
  'config={"custom":{"grafana":{"stack_config_fields":[]}}}' > "$workdir/custom-builtin.json" || true
grep -q "built-in" "$workdir/custom-builtin.json" \
  || { echo "ASSERTION FAILED: redeclaring a built-in was not rejected" >&2; cat "$workdir/custom-builtin.json" >&2; exit 1; }

step "the declaration and its values survive a switch to a built-in and back (#228)"
mcp_call odd_config_set 'config={"stack":"local"}' > "$workdir/custom-away.json"
assert_result_contains "$workdir/custom-away.json" '"stack": "local"'
assert_result_contains "$workdir/custom-away.json" '"base_url": "http://seq.example.test:5341"'
mcp_call odd_config_set 'config={"stack":"seq"}' > "$workdir/custom-back.json"
assert_result_contains "$workdir/custom-back.json" '"stack": "seq"'

step "removing the declaration of the configured stack is refused (#228)"
mcp_call odd_config_set 'config={"custom":{"seq":null}}' > "$workdir/custom-remove-configured.json" || true
grep -q "configured stack" "$workdir/custom-remove-configured.json" \
  || { echo "ASSERTION FAILED: removing the configured stack's declaration was not refused" >&2; cat "$workdir/custom-remove-configured.json" >&2; exit 1; }
mcp_call odd_config_get > "$workdir/after-custom-remove-configured.json"
assert_result_contains "$workdir/after-custom-remove-configured.json" '"stack": "seq"'

step "switching away and removing the declaration in one call (#228)"
mcp_call odd_config_set 'config={"stack":"local","custom":{"seq":null},"stack_config":{"seq":null}}' \
  > "$workdir/custom-remove.json"
assert_result_contains "$workdir/custom-remove.json" '"stack": "local"'
assert_result_contains "$workdir/custom-remove.json" '"custom": {}'
jq -e '.content[0].text | contains("seq") | not' "$workdir/custom-remove.json" > /dev/null \
  || { echo "ASSERTION FAILED: removed custom stack still present" >&2; cat "$workdir/custom-remove.json" >&2; exit 1; }

step "hand-edited invalid values degrade to defaults, listed in invalid_ignored"
mkdir -p "$(dirname "$CONFIG_FILE")"
printf '%s' \
  '{"stack":"narnia","local":{"grafana_port":"high"},"custom":{"seq":{"stack_config_fields":"base_url"}},"stack_config":{"notastack":{},"azure-monitor":{"tenant":"11111111-1111-1111-1111-111111111111"}}}' \
  > "$CONFIG_FILE"
mcp_call odd_config_get > "$workdir/tolerant.json"
assert_result_contains "$workdir/tolerant.json" '"stack": "local"'
assert_result_contains "$workdir/tolerant.json" '"grafana_port": 3000'
jq -e '.content[0].text | fromjson | .stack_config["azure-monitor"] | has("tenant") | not' \
  "$workdir/tolerant.json" > /dev/null \
  || { echo "ASSERTION FAILED: undocumented key tenant was surfaced as effective config" >&2; cat "$workdir/tolerant.json" >&2; exit 1; }
assert_result_contains "$workdir/tolerant.json" '"custom": {}'
for flagged in "custom.seq" "stack" "local.grafana_port" "stack_config.notastack" "stack_config.azure-monitor.tenant"; do
  jq -e --arg name "$flagged" \
    '.content[0].text | fromjson | .invalid_ignored | index($name)' \
    "$workdir/tolerant.json" > /dev/null \
    || { echo "ASSERTION FAILED: invalid_ignored does not list: $flagged" >&2; cat "$workdir/tolerant.json" >&2; exit 1; }
done

echo "config surface: OK"
