#!/usr/bin/env bash
# Runner: executes every test-*.sh in this folder, in name order, fail-fast.
# Add a new integration test by dropping a test-<name>.sh next to this file.

set -euo pipefail
cd "$(dirname "$0")/../.."

for test_script in integration-tests/mcp-server/test-*.sh; do
  echo "=== $(basename "$test_script") ==="
  bash "$test_script"
done

echo "all mcp-server integration tests passed"
