# Writing a k6 script

Official docs: https://grafana.com/docs/k6/latest/using-k6/

## Requests, checks, thresholds - three distinct concepts

- **Requests** - `k6/http`: `http.get(url)`, `http.post(url, body)`, etc.
  Source: https://grafana.com/docs/k6/latest/using-k6/http-requests/
- **Checks** - per-request pass/fail assertions that never stop the
  test (`check(res, {'status is 200': (r) => r.status === 200})`).
  Failures count toward `checks_failed`, never abort the run. Source:
  https://grafana.com/docs/k6/latest/using-k6/checks/
- **Thresholds** - pass/fail criteria on **aggregated metrics** across
  the whole run (`thresholds: {http_req_duration: ['p(95)<500']}`).
  A crossed threshold is what produces exit code 99 (see
  running-tests.md). Source:
  https://grafana.com/docs/k6/latest/using-k6/thresholds/
- **Assertions** (`expect`, from the `k6-testing` jslib) - a third,
  newer concept, Playwright-inspired, distinct from both checks and
  thresholds. Confirm current syntax against the official docs before
  using it - not yet exercised live for this plan.

## Staged load - `options.stages`

Verified live (this machine, k6 v2.2.0):

```javascript
export const options = {
  stages: [
    { duration: '3s', target: 5 },  // ramp up to 5 VUs
    { duration: '5s', target: 5 },  // hold at 5 VUs (steady state)
    { duration: '2s', target: 0 },  // ramp down to 0
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};
```

This is the shape a benchmark manifest's warmup/ramp/steady profile
stages map onto - `stages` is k6's own vocabulary for it (the
`ramping-vus` executor under the hood; see
https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ for the
full executor list when a benchmark needs a shape other than staged
ramping - e.g. `constant-vus`, `constant-arrival-rate`).

**Discarding warmup**: k6 runs one continuous window - there is no
built-in "discard the first N seconds" the way `run-scenario`'s own
warmup rule expects. A benchmark's manifest needs the stage boundaries
recorded (as timestamps, since `options.stages` durations are known at
author time) so a later query can exclude the ramp stage from quoted
steady-state percentiles. This is one of the two inputs the manifest
schema (owned by `k6-benchmark-expert`, not fixed by this skill) must
settle.

## Secrets - never a literal credential in a committed script

An authenticated benchmark reads credentials through k6's own secrets
API, never inlined:

- `k6/secrets` module + `--secret-source` flag (source:
  https://grafana.com/docs/k6/latest/javascript-api/k6-secrets/) - the
  documented way to keep a secret out of both the script and k6's own
  logs.
- Alternative: environment variables the manifest names but never
  stores a value for (`__ENV.API_TOKEN` in the script, the manifest
  records only the variable's **name**).

`create-update-benchmark` refuses to persist a script containing a
literal credential - this reference is what the authoring agent follows
so that check never fires.
