# odd_stack_status Identity Fields — Design

Implements [#118](https://github.com/using-system/oddyssey/issues/118):
`odd_stack_status` returns liveness only — expose image, timestamps,
and effective env.

## Problem

`odd_stack_status` returns four readiness booleans and nothing else.
Everything else the observation contracts need about the container
must come from outside oddyssey via `docker inspect`: the image tag
(report frontmatter, replay conditions), the created/started
timestamps (the `instance` / `process_restarted` identity that
cumulative-metric queries key on), and the effective container
environment (the N3 finding of the 2026-08-28 observation report: an
applied-but-not-persisted variable is invisible without docker
access).

## Design

### Result shape

`stack_status()` keeps its five booleans unchanged and gains four
fields, **always present**:

```json
{
  "running": true,
  "prometheus": true, "tempo": true, "loki": true, "pyroscope": true,
  "image": "grafana/otel-lgtm:0.31.0",
  "created": "2026-08-29T08:12:03.123456789Z",
  "started": "2026-08-29T08:12:04.567890123Z",
  "env": {"GF_LOG_LEVEL": "debug", "X_DEMO_TOKEN": null}
}
```

- `image` — the tag the container was created from
  (`.Config.Image`), verbatim.
- `created` / `started` — `.Created` and `.State.StartedAt` as docker
  reports them (RFC 3339, UTC), passed through verbatim — no parsing,
  no reformatting.
- `env` — the container's **user-set** environment as
  `container_user_env()` already computes it (everything minus the
  image's own env and the embedded defaults), with one redaction
  rule: a credential-named variable (the existing
  `SENSITIVE_ENV_MARKERS` heuristic, the same rule as
  `env_not_persisted`) keeps its **name** but carries `null` instead
  of its value. The name closes N3's dark window
  (applied-but-not-persisted variables become visible without docker
  access); the value never leaves the server, per the no-secrets
  contract. This is a deliberate reading of the issue's "secrets
  excluded": excluding the entry entirely would re-create the very
  invisibility N3 reported.
- **Absent container**: all four fields are `null` (`env` included —
  `null`, not `{}`: "no container" and "container with no user env"
  are different facts). A stopped container reports its identity
  fields normally (it exists) with the booleans `false`.
- Every identity read is **best-effort**: an unreadable inspect
  yields `null` fields, never an error — a status call must never
  fail because docker hiccupped, matching `container_user_env()`'s
  own contract.

### Internal split — the boot loop stays cheap

`stack_up()` polls the status every 2 s for up to 120 s; enriching
that loop with three docker inspects per poll would multiply spans in
every boot trace for data the loop never reads. Split:

- `_readiness(transport)` — the current probe-only body (five
  booleans); used by `stack_up`'s wait loop.
- `stack_status(transport)` — `_readiness()` plus the identity
  fields; the public surface `odd_stack_status` and `stack_reset`'s
  callers keep using.

One new helper, `_container_identity()`, reads image/created/started
in a single `docker inspect` (one span); `env` reuses
`container_user_env()` unchanged (two more docker calls, already
instrumented). Cost: at most three docker invocations per
`odd_stack_status` call, zero added to boot polling.

### What does not change

- The four booleans and `running` — same names, same semantics.
- The tool set — `odd_stack_status` keeps its registration (spec §2
  "tool registration must not change" is untouched by a richer
  result).
- stdout stays the JSON-RPC wire; identity reads go through the
  existing `_docker()` (instrumented, no stdout).

## Acceptance (from #118)

1. `odd_stack_status` returns image, created/started timestamps, and
   the effective user-set env alongside the readiness booleans.
2. A report's `instance` identity can be filled from
   `odd_stack_status` alone — no `docker inspect` needed by the
   caller.
3. Unit tests cover the new fields, including the absent-container
   case (and, per this design, the redaction rule and the
   boot-loop-stays-cheap split).

## Out of scope

- Remote stacks (the issue's env visibility concern on remote
  backends is a different tool surface).
- Any change to `stack_up`/`stack_reset` result shapes.
