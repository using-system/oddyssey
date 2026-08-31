# Benchmark authoring and running

A k6 load-test benchmark, authored once as reviewed code and replayed
identically for as long as it stays useful.

## Install k6

Needed to **run** a benchmark, never to author one — authoring only
writes the script and the manifest, it never executes k6 itself.

**Binary**: `k6` — `brew install k6` (macOS/Linux), or the official
install script / prebuilt binaries for other platforms:
https://grafana.com/docs/k6/latest/set-up/install-k6/

## Author

```text
/odd-instrument-bench author a load benchmark for checkout, stress test, p95 under 300ms
```

Investigates the service and writes a k6 script + manifest into
`.odd/benchmarks/<name>/`. It asks you back for whatever only you can
decide — test type, thresholds, target environment, new benchmark or an
update to an existing one — and proposes a load shape/duration for you
to confirm; everything else (which endpoints matter) it figures out on
its own. It never runs what it writes.

Updating an existing benchmark follows the same prompt — the change
comes back as a reviewed diff against the stored version, never a
silent replacement.

## Run

```text
/odd-observe run .odd/benchmarks/checkout-read-heavy/
```

Point `/odd-observe` at the stored script and it asks for whatever else
it needs (the service, the mode). A dedicated `benchmark: <name>` field
— citing the manifest and pinning the git revision automatically
instead of naming the path by hand — is designed but not built yet.

