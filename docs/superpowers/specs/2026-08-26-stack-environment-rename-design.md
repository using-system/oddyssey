# Report Stack / Detected Environment — Design

Spec for issue #94. Status: all decisions settled (maintainer, 2026-08-26).

## Problem

The observation-report frontmatter field named `environment` actually
records the **stack** (`local | the remote backend name — grafana,
datadog, ...`) — the same vocabulary as the global configuration's
`stack` value. What it does not record is the **deployment environment**
the observed service runs in: the same `stack: grafana` can target
integration, uat, or prod depending on the external gcx CLI context at
run time.

Three concrete harms:

- **Recall comparability hazard (the serious one):** recall matches
  baselines on services + same `environment`. Two runs both recording
  `grafana` while the CLI context pointed at different instances (uat,
  then prod) get diffed against each other — a one-changed-variable
  violation, and unlike `workload`/`instance` nothing recorded in the
  report distinguishes them today.
- **`/odd-status` cannot filter on what users mean by environment** (its
  documented `on prod` example has no frontmatter value it could match).
- **Vocabulary clash:** the MCP configuration calls it `stack`; the
  prompts say "environment (defaults to the configured stack)" — two
  names for one concept, and the real concept of environment has no name
  at all. The telemetry already carries it: `otel-instrumentation-expert`
  mandates `deployment.environment.name` as a resource attribute.

## Decisions settled (maintainer)

1. **Rename `environment` → `stack`** in the observation-report
   frontmatter; values unchanged. Same rename for the instrumentation
   report's `target` field. One vocabulary everywhere.
2. **New `environment` field, detected — never asked.** Its source is
   the observed service's `deployment.environment.name` resource
   attribute — not the mission, not the CLI context, not the persisted
   configuration.
3. **One observation, one environment.** A mission's observed services
   cannot live in different environments; `environment` is a single
   frontmatter value.
4. **`/odd-verify` stops hard on divergence.** No verdict is ever ruled
   cross-environment.
5. **No compatibility layer in the contracts; migrate this repo's
   reports.** The contracts carry no pre-rename tolerance; the four
   stored reports of this repository are migrated in the same PR
   (the #79 precedent, commit 8de2901). Elsewhere a pre-rename report
   simply yields no recall match — the recall's normal no-baseline case.
6. **No `environment` field on instrumentation reports:** an
   investigation analyzes code, not a running deployment that emits the
   attribute.

## The two fields

```yaml
stack: grafana          # local | the remote backend name (grafana, datadog, ...)
environment: prod       # detected: deployment.environment.name reported by the service's telemetry
```

- On `stack: local`, `environment` is `local` by construction — the
  local stack IS the environment. A local service emitting a different
  `deployment.environment.name` still records `local`, and the
  discrepancy is stated as a finding (misconfigured resource
  attributes), never silently ignored.
- When the service emits no `deployment.environment.name`, the
  environment is recorded as `unknown` — stated, never guessed — and
  the absence is a telemetry gap for the instrumentation to fix.

## Detection timing

The environment is only knowable once telemetry exists, so the sequence
is explicit:

- **Pre-run probe:** before any reset or scenario, a bounded discovery
  query reads the service's recent telemetry for
  `deployment.environment.name`; when a value is found, recall matching
  and the verify divergence check both fire before any traffic is
  driven.
- **Provisional value:** when pre-run telemetry is empty (fresh reset,
  first run), the environment is provisional until the first scenario
  telemetry lands; the verify divergence check fires at that point —
  the already-driven load is the named, accepted cost — and the
  recalled baseline is re-confirmed or discarded with a statement.
- **Actor:** the `observe-run` agent performs the detection and owns
  the hard stop (a prompt's preflight cannot query telemetry); the
  verify mission block hands it the baseline's environment to compare
  against.
- **Split detection:** services of one mission detecting different
  values — or several values for one service in a post-hoc window —
  stop the run; the report names the split and the remedy: separate
  missions, one per environment.

## Recall matching

A baseline matches on services ∩ + same `stack` + same `environment` —
two runs on the same backend kind but different environments never get
diffed. An `unknown` environment matches only another `unknown`, and
with a warning: the comparison may span environments without the
reports being able to say so.

## Verify on environment divergence

`/odd-verify` compares the environment its own run detects against the
baseline's and stops hard on divergence: no cross-environment verdict —
the run names both values (baseline `prod`, detected `uat`) and
recommends rerunning against the baseline's environment, or observing
the detected one as a new baseline. When the baseline is an
instrumentation report (no environment by design), the check is skipped
and the detected environment is recorded fresh.

## Surfaces

- `create-observe-run-report`: frontmatter contract (rename + detected
  field + detection rules) and the recall matching rule.
- `observe-run` agent + `/odd-observe`: the mission's Environment input
  becomes **Stack**; the environment is not a mission input — the agent
  detects it per the timing above and records it.
- `/odd-verify`: preflight replays the report's `stack`; mission block
  carries the baseline environment; hard-stop contract.
- `/odd-status`: filters on stack and deployment environment,
  distinctly.
- `create-otel-instrumentation-report` + `otel-instrumentation-expert`
  + `/odd-instrument`: `target` → `stack`; the agent's "export target"
  prose names the stack.
- `observability-cli-guides`: "the environment's backend / CLI"
  phrasing follows the rename.
- README: remaining environment-means-backend prose; the `/odd-status`
  `on prod` example becomes real.
- `.odd/observe-run-reports/`: the four stored reports migrated
  (`stack: local` + `environment: local`, by construction).

**Exemptions:** backend-native product terms (Dynatrace's "environment"
is its tenant term), environment *variables* (container env, `OTEL_*`),
the `otel-guides` references (official OTel docs vocabulary), and
`deployment.environment.name` itself keep their names.

## Out of scope

- Any Python change: `config.py`/`server.py` already speak `stack`.
- Filename conventions (#80 closed wontfix): frontmatter only.
- Per-service environment maps: rejected — one observation, one
  environment (decision 3).
