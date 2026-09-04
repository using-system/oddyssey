# Replay a stored k6 benchmark

When the mission names a benchmark under `.odd/benchmarks/<name>/`
(`k6-benchmark-expert` authored it, `odd-memory`'s `benchmark`
reference stored it),
the load comes from its script instead of a curl loop. The identity
reference and `SKILL.md` steps 3 and 5 apply unchanged — the clean-base
order, the sample-count rules, the flush wait — and `SKILL.md` step 4
applies with the record shape below. What
differs is how the load is generated and how the record cites it:

## Confirm k6 is installed before anything else

Before the clean-base reset (`references/run-identity.md`):
`command -v k6`, per the `k6-guides` skill's `install.md`. Reached
from a prompt's preflight (the nominal case, inside `observe-run`),
the binary is already there — a still-missing one is a contract
failure to report with the reference's install steps, never a reason
to install from a subagent. Entered directly in the main
conversation, with no preflight behind it, run that reference's
auto-install step first. Either way, when k6 is absent the observed
process and the store stay untouched: never restart or reset for a
run you cannot perform, never approximate the script with a curl
loop. `running-tests.md` in the same skill carries the flags, the
output surface, and the exit codes cited below.

## Read the manifest, then run the script unmodified

The benchmark
directory holds one k6 script and one manifest
(the `benchmark` reference's layout): the script is `script.js`
unless the manifest names another file. Run it from the repository
root, as one blocking foreground command (or the detached poller
below when the run outlasts a tool call), with k6's end-of-test
summary exported to a scratch file:

```text
k6 run .odd/benchmarks/<name>/script.js --summary-export <summary-file>
```

Inputs the manifest leaves to mission time (a base URL, a named
environment variable) are passed through k6's `-e KEY=value` or the
environment, and recorded by name — a credential's value never lands
in the record. Never edit the script or the manifest to make the run
nicer: a benchmark that cannot run as stored is a reported failure,
and a change to it goes through `/odd-instrument-bench`'s reviewed
diff, never through the run.
- **The record cites the benchmark by name and git revision, not by
  commands.** Record the repository revision (`git rev-parse HEAD`) and
  whether the benchmark's directory is clean
  (`git status --porcelain .odd/benchmarks/<name>/` prints nothing). A
  dirty benchmark has no revision to replay at — say so in the record.
  A replay runs the same benchmark at the same revision; when the
  stored benchmark moved between the two runs (a diff-reviewed update
  landed), the load may have changed with it. The record then says
  what moved: findings against the benchmark itself (a script defect,
  an unattainable threshold) are ruled on the new revision, while the
  service's before/after numbers compare only when the requests,
  pacing, and stages are the same — otherwise the second run's numbers
  open the service's new baseline, stated as such, never a before/after
  against the first.

## Warmup is the manifest's stage boundaries

A k6 run is one
continuous window, so `SKILL.md` step 2's "discard the warmup" becomes a
sub-window: quote steady-state numbers from the interval the
manifest's ramp and steady stages delimit, record those boundaries
as UTC timestamps, and say the ramp was excluded. `SKILL.md` step 3's
standard sample counts apply (>= 30 requests before a p95, ~100 before a p99)
— k6 load is cheap, high-volume, and deterministic, so the
expensive-iteration carve-out of `references/long-scenarios.md` does
not.

## k6's own summary and exit status are evidence, never the verdict

Record the exit code (`0` every threshold passed, `99` a threshold
was crossed, anything else a setup or script error — read stderr),
the request count, failed checks, dropped iterations, and script
exceptions from stderr — folded into the record's `k6:` line, which
is what survives. The summary file itself is transient: write it to
a scratch location, never inside `.odd/benchmarks/<name>/` (it would
dirty the directory the record just declared clean), and never
count on it existing when the run is verified later. Then measure
through the service's own telemetry, after `SKILL.md` step 5's flush wait. A
generator that never connected, crashed mid-run, or threw on every
iteration leaves telemetry that looks deceptively clean — "a failed
or partial run is data" applies to the generator too. The manifest's
thresholds are what the observation rules on, each against a
telemetry-derived measurement carrying its query — **unless the
generator threw**: script exceptions above zero mean the benchmark
did not exercise what it was built to measure, every threshold
ruling is void, and the run is reported as a defective benchmark (a
finding against the script, to fix through `/odd-instrument-bench`),
never as a pass.

## k6's own OpenTelemetry output is a bonus signal

Against the local
stack, `K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run -o opentelemetry
<script>` lands k6's client-side view in the same store under
`service_name="k6"` (`running-tests.md`): cross-confirm against it
when it lands, never require it, never mistake it for the target
service.

## A run longer than a tool call uses the detached poller of `references/long-scenarios.md`

A
staged benchmark routinely exceeds one tool call's budget; the poller
script and its output file are part of the record.

## This skill stays scoped to locally running services

Whether a
benchmark may be driven at a remote target is the observation
caller's decision, given at mission time through `observe-run`'s own
rule — never read from the manifest, never decided here.

The record replaces `SKILL.md` step 4's `Commands:` lines with the benchmark's
identity, the single command, and k6's own evidence:

```text
Scenario:  benchmark orders-read-heavy
Benchmark: .odd/benchmarks/orders-read-heavy/ @ 3ccfd18 (clean)
Base URL:  http://127.0.0.1:8080   # BASE_URL, mission-time
Listeners: none
Backend:   odd_stack_reset, env: defaults
Instance:  orders-run-0902 (restarted before reset)
Stages (UTC): ramp 10:04:12–10:05:12 (excluded), steady 10:05:12–10:10:12, ramp-down 10:10:12–10:10:42
Started (UTC): 2026-09-02T10:04:12Z
Ended   (UTC): 2026-09-02T10:10:42Z
Query points: 1 (after Ended)
Command:
  K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run .odd/benchmarks/orders-read-heavy/script.js -o opentelemetry --summary-export /tmp/k6-summary-orders-run-0902.json -e BASE_URL=http://127.0.0.1:8080   # -o opentelemetry and its env: local stack only
k6:        exit 0, 1234 requests, checks 100%, dropped iterations 0, script errors 0 (summary file transient, numbers above are the record)
Not reproducible: none
```

