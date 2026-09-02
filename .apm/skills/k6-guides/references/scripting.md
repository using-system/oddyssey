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
  running-tests.md). Expressions take `==`, `!=`, `>`, `>=`, `<`, `<=`,
  so a caller answering "zero failures" maps onto an equality, not a
  small fraction: `http_req_failed: ['rate==0']` (not one failed
  request) and `checks: ['rate==1.00']` (every check passed). Verified
  live (this machine, k6 v2.2.0): both pass with exit 0 on a clean run,
  and a single 404 among 10 requests crosses both and exits 99. Source:
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

## Pacing - VU count is not the request rate

`options.stages` bounds two things and two only: how many VUs run
concurrently, and how long the run lasts. It says nothing about the
request rate. A VU is a loop - "VUs are essentially parallel
`while(true)` loops" - that calls the default function again the
instant the previous iteration returns, so:

```
requests/s = VUs x (requests per iteration) / (iteration duration)
```

and the iteration duration is whatever the default function takes,
**including any `sleep`**. With no `sleep`, the iteration duration
collapses to the response time, and against a fast local target a
5-VU "smoke test" becomes thousands of requests per second - a load
test nobody asked for, which then crosses its own error threshold.

Verified live (this machine, k6 v2.2.0, the staged-load options above
against a trivial local HTTP target):

- default function with one request and one check, **no `sleep`** -
  25,703 requests at 2,570 req/s, 19.13% failed, `http_req_failed`
  threshold crossed, exit 99.
- the same script with `sleep(1)` added - 40 requests at 4.0 req/s,
  0% failed, every threshold met, exit 0.

`sleep` suspends the calling VU for a number of **seconds**:

```javascript
import { sleep } from 'k6';

sleep(1); // last statement of the default function
```

Source: https://grafana.com/docs/k6/latest/javascript-api/k6/sleep/

So a benchmark's request rate is set by VU count **and** pacing
together - a manifest that records stages but not the pacing has not
recorded the load. When a benchmark needs an *exact* request rate
rather than one that drifts with the target's response time, don't
pace with `sleep`: use the `constant-arrival-rate` executor (named
above), which holds iterations/s directly and starts however many VUs
that takes. Source:
https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/

## Response bodies - `discardResponseBodies` and `responseType`

Official docs: `using-k6/k6-options/reference/#discard-response-bodies`,
`javascript-api/k6-http/params/` (`Params.responseType`).

`discardResponseBodies: true` in `options` changes the default
`responseType` of **every** request to `none`: `res.body` is `null`,
and `res.json()` throws. The docs recommend exactly that - discard
globally, it lightens memory and GC on the load generator - **and then
set `responseType: 'text'` (or `'binary'`) on the individual requests
whose body the script reads**:

```javascript
export const options = { discardResponseBodies: true };

export default function () {
  const res = http.post(`${__ENV.BASE_URL}/orders`, payload, {
    headers: { 'Content-Type': 'application/json' },
    responseType: 'text', // this body is read below
  });
  const id = res.json('id');
}
```

Verified live (this machine, 2026-09-02, k6 v2.2.0, one iteration
against a trivial local JSON endpoint):

- global discard, `res.json('id')` on the POST, **no override** -
  `res.body` is `null`, then `GoError: the body is null so we can't
  transform it to JSON - this likely was because of a request error
  getting the response`, a script exception on every iteration. The
  request itself succeeded: the error message's guess is wrong, the
  cause is the discard.
- the same script with `responseType: 'text'` on that request - the id
  is read, no error.

This is a **runtime** defect: `k6 inspect` does not see it (see
running-tests.md, "Validating without running"), and a benchmark
carrying it reports a clean run whose every dependent request went to
a nonexistent id. The static check is trivial - a global discard plus
any `res.json()` / `res.body` / `res.html()` on a request without an
explicit `responseType` is a self-contradiction to fix before
persisting.

## Minimal runnable script

The blocks above are fragments. This is the structure that makes them
a file k6 can run - imports, `options`, and the default function:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  // stages + thresholds - see "Staged load" above
};

export default function () {
  const res = http.get('http://localhost:8080/');
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
```

Init code (the imports and `options`) "runs first and is called only
once per VU. The `default` code runs as many times or as long as is
configured in the test options" - the default function *is* the
iteration. Source:
https://grafana.com/docs/k6/latest/get-started/running-k6/

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
