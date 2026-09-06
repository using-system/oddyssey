# Driving an MCP server with k6

Official docs: the transport is specified at
https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
(streamable HTTP); the k6 side is plain `k6/http` - see scripting.md.

An MCP server's packaged entry point usually speaks **stdio**, which k6
cannot drive. The same application served over the SDK's **streamable
HTTP** transport is one HTTP endpoint k6 loads like any other API, so a
benchmark targets that transport and records that the stdio server is
the same application. Everything below was verified live on
2026-09-06 against **k6 v2.2.0** and the **Python MCP SDK 2.1.1**;
re-verify against the server's own SDK before reusing it.

## The wire - one endpoint, JSON-RPC, two possible body shapes

Every call is a `POST` to the transport's single path (`/mcp` by
default) carrying a JSON-RPC 2.0 payload. Two request headers are not
optional:

- `Content-Type: application/json`.
- `Accept: application/json, text/event-stream` - in its default (SSE)
  mode the server requires **both** media types to be acceptable and
  refuses a JSON-only request with `406`, before any tool runs. A
  transport built with `json_response=True` requires only JSON, so
  sending both is the shape that works against either.

The answer is either a JSON body or a `text/event-stream` whose `data:`
line carries the JSON-RPC response - the same request can return either
shape, so a script parses both:

```javascript
function parseRpc(body) {
  if (!body) return null;
  const trimmed = body.trim();
  if (trimmed.startsWith('{')) return JSON.parse(trimmed);
  for (const line of trimmed.split('\n')) {
    if (line.startsWith('data:')) {
      const payload = line.slice(5).trim();
      if (payload) return JSON.parse(payload); // skip an empty priming event
    }
  }
  return null;
}
```

Bodies are read, so the global `discardResponseBodies` recommendation of
scripting.md needs `responseType: 'text'` on every request whose answer
the script parses.

`parseRpc` above returns on the first `data:` line, which is the answer
in the default configuration. A server configured with an event store
(resumability) may emit a priming event with an empty `data:` payload
first - skip an empty payload rather than handing it to `JSON.parse`.

## The handshake - two calls, then a session id on everything

1. `initialize` (params: `protocolVersion`, `capabilities`,
   `clientInfo`) answers **200**. The session id is in the
   `Mcp-Session-Id` **response header**, and the result carries the
   `protocolVersion` the server negotiated - which may differ from the
   one offered.
2. `notifications/initialized` answers **202 with an empty body**. It is
   a notification: no `id` in the payload, nothing to parse. A server
   may reject tool calls made before it.
3. Every later request carries `Mcp-Session-Id` and
   `MCP-Protocol-Version` (the negotiated value) beside the two headers
   above.

## The header trap - `res.headers[name]` is a string, not an array

k6's Response reference states: *"When requesting a header by a specific
name, an array of strings is returned since the header can have multiple
values ... `Response.headers["my_key"][0]`"*. **k6 v2.2.0 returns a
plain string.** Verified live (this machine, 2026-09-06, a local server
answering `Mcp-Session-Id: abc123`):

| Expression | Value returned |
| --- | --- |
| `typeof res.headers['Mcp-Session-Id']` | `string` |
| `res.headers['Mcp-Session-Id']` | `"abc123"` |
| `res.headers['Mcp-Session-Id'][0]` (the documented form) | `"a"` |
| `res.headers['mcp-session-id']` (lowercase) | `undefined` |

Two defects follow, both silent - no exception, no warning:

- Indexing as the docs describe yields the **first character** of the
  session id. The handshake looks like it succeeded and every later call
  fails on an unknown session.
- Header keys are canonical-cased (Go's `CanonicalHeaderKey`), so the
  lowercase name the server sends on the wire finds nothing. Look the
  header up in canonical form.

Read the header through a helper that tolerates both shapes, so the
script survives a k6 version that does return arrays:

```javascript
function headerValue(res, name) {
  const value = res.headers[name];
  if (Array.isArray(value)) return value.length ? value[0] : null;
  return value === undefined ? null : value;
}
```

## A tool failure is HTTP 200 - `http_req_failed` never sees it

A tool that raises answers **200** with a JSON-RPC result whose
`isError` is `true` (or, for a protocol-level fault, a JSON-RPC `error`
member). Neither moves `http_req_failed`, whose rate counts transport
failures and HTTP error statuses only. A benchmark that rules on
`http_req_failed` alone reports a clean run over a server that failed
every call.

Assert both in a check, on every `tools/call` (an excerpt of the
assembled script at the end of this reference):

```javascript
const res = http.post(ENDPOINT, payload, params);
const rpc = parseRpc(res.body); // null when the body is missing or unparseable

check(res, {
  'status is 200': (r) => r.status === 200,
  'no JSON-RPC error': () => !!rpc && !rpc.error,
  'isError not true': () => !!rpc && !!rpc.result && rpc.result.isError !== true,
});
```

Guard every callback against `null`: a check that throws aborts the
iteration exactly like the `fail()` below, and `null` is the state a 404
or an unparseable body produces - both of which this transport
produces.

`checks: ['rate==1.00']` as a threshold then makes those assertions
count toward the run's verdict (scripting.md, "Requests, checks,
thresholds").

## One session per VU

Module-level state in k6 is **per VU**, and init code cannot make HTTP
requests, so a VU opens its session on its first iteration and keeps it
for every later one:

```javascript
let sessionId = null; // per VU

export default function () {
  if (sessionId === null && !openSession()) {
    sleep(1); // the checks recorded the failure; retry next iteration
    return;
  }
  // ... calls carrying sessionId
}
```

- **Never `fail()` on a failed handshake.** `fail()` throws, and the
  throw **aborts that iteration**: the calls after it are never sent, so
  the iteration measures nothing and the VU loses its retry. Verified
  live (this machine, 2026-09-06, k6 v2.2.0): `fail()` in 1 of 5
  iterations logs `hint="script exception"` on stderr, and the run
  continues - the other iterations run, the thresholds are still
  evaluated, exit 0. The ruling is not lost, the iteration is: the
  aborted iteration measures nothing and the VU retries with no pacing
  in between. k6's summary carries no exception counter, so the error
  line on stderr is the only trace. Record the failure through the
  checks, pace, return.
- **The script never closes a session.** The transport does accept a
  `DELETE` carrying the session id (the spec has clients send one), but
  k6 has nowhere to send it from: `teardown()` runs once, in its own
  context, with no access to the per-VU session ids. And the Python
  SDK's `session_idle_timeout` defaults to `None`, so nothing expires
  them either - sessions live until the server stops. A run at 200 VUs
  leaves 200 open sessions behind, so a server process is not reused
  across runs.
- **A 404 means the session is gone** ("Session not found") - after a
  server restart, or an eviction. Drop the id so the next iteration
  re-initializes, and **skip the rest of the current iteration**:
  otherwise one lost session becomes three or four failed requests, and
  an error-rate threshold measures a stuck client rather than the
  server.

A request helper can only drop the id; leaving the iteration is the
caller's job, so the helper reports the loss and the default function
acts on it:

```javascript
// in the request helper
if (res.status === 404 && sessionId !== null) {
  sessionId = null;
  sessionLost = true;
}

// in the default function, after the call's checks
if (call.sessionLost) {
  sleep(1); // pace before the next iteration re-initializes
  return;
}
```

That re-initialization is not free of consequence for the thresholds: the
404 itself is a failed request, so `http_req_failed: ['rate==0']` is
crossed by a session the server dropped, not by a service defect. A run
that may restart the server wants the threshold scoped by tag, or a
rate that tolerates the re-initializations it expects.

## The ceiling to check before reading a latency result

In the Python SDK, a tool declared as a synchronous `def` is executed
through `anyio.to_thread.run_sync`, whose default worker pool is a
`CapacityLimiter` of **40** (anyio 4.14.2). At most 40 such calls run at
once; beyond that they queue, and latency grows with no error and no
failed request to point at. An `async def` tool runs on the event loop
and is not bound by it.

So before quoting a stress or breakpoint number as the service's
capacity, check which of the two the tool under load is: a plateau at
around 40 concurrent calls is the pool, not the service. The same
applies to any per-call subprocess or external command a tool runs - the
cost is the tool's, not the transport's, and a whole-run latency
threshold that ignores it is unattainable by construction (see
`authoring-inputs.md` on cross-checking a threshold against the code).

## Protocol revisions - this shape has a boundary

The session model above is the **handshake-era** transport (revisions
`2024-11-05` through `2025-11-25`). SDK 2.1.1 also speaks a newer
revision (`2026-07-28`) that carries a stateless per-request envelope
instead. A script that hardcodes the handshake is fine as long as it offers a
handshake-era `protocolVersion` **and asserts that the negotiated one is
handshake-era too** - a check on the value, not merely on its presence
(`init` and `result` come from the handshake, as assembled at the end of
this reference):

```javascript
const HANDSHAKE_VERSIONS = ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'];
check(init.res, {
  'initialize: handshake-era version negotiated': () =>
    !!result && HANDSHAKE_VERSIONS.indexOf(result.protocolVersion) !== -1,
});
```

A server that answers with a modern revision passes a presence-only
check and then receives session headers a stateless transport does not
use. When that happens, re-read the transport spec before assuming these
headers still apply.

## Minimal shape

The fragments above, assembled - one session per VU, one tool call,
every rule applied. `parseRpc()` and `headerValue()` are the two helpers
defined earlier in this reference; the script needs both:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const ENDPOINT = `${__ENV.BASE_URL || 'http://127.0.0.1:8080'}/mcp`;
const PROTOCOL_VERSION = '2025-06-18';
const HANDSHAKE_VERSIONS = ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'];

export const options = {
  discardResponseBodies: true,
  scenarios: { read: { executor: 'constant-vus', vus: 1, duration: '1m' } },
  thresholds: { http_req_failed: ['rate==0'], checks: ['rate==1.00'] },
};

let sessionId = null;
let negotiated = PROTOCOL_VERSION;
let nextId = 0;

function headers(extra) {
  return Object.assign(
    {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
    },
    extra || {}
  );
}

function sessionHeaders() {
  return { 'Mcp-Session-Id': sessionId, 'MCP-Protocol-Version': negotiated };
}

// Returns { res, rpc, sessionLost } - rpc is null when the body carries
// no parsable JSON-RPC response, so every caller guards it.
function post(name, method, params, extra) {
  const payload = { jsonrpc: '2.0', method };
  if (method.indexOf('notifications/') !== 0) payload.id = ++nextId;
  if (params !== undefined) payload.params = params;
  const res = http.post(ENDPOINT, JSON.stringify(payload), {
    headers: headers(extra),
    tags: { name },
    responseType: 'text',
  });
  let sessionLost = false;
  if (res.status === 404 && sessionId !== null) {
    sessionId = null;
    sessionLost = true;
  }
  return { res, rpc: parseRpc(res.body), sessionLost };
}

function openSession() {
  const init = post('initialize', 'initialize', {
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {},
    clientInfo: { name: 'k6-bench', version: '1' },
  });
  const id = headerValue(init.res, 'Mcp-Session-Id');
  const result = init.rpc && init.rpc.result;
  check(init.res, {
    'initialize: status 200': (r) => r.status === 200,
    'initialize: session id header present': () => typeof id === 'string' && id.length > 0,
    'initialize: handshake-era version negotiated': () =>
      !!result && HANDSHAKE_VERSIONS.indexOf(result.protocolVersion) !== -1,
  });
  if (!id || !result || HANDSHAKE_VERSIONS.indexOf(result.protocolVersion) === -1) return false;
  sessionId = id;
  negotiated = result.protocolVersion;
  const ack = post('notifications/initialized', 'notifications/initialized', undefined, sessionHeaders());
  if (!check(ack.res, { 'initialized: status 202': (r) => r.status === 202 })) {
    sessionId = null;
    return false;
  }
  return true;
}

export default function () {
  if (sessionId === null && !openSession()) {
    sleep(1); // the checks recorded the failure; retry next iteration
    return;
  }
  const call = post('tools/call my_tool', 'tools/call', { name: 'my_tool', arguments: {} }, sessionHeaders());
  const result = call.rpc && call.rpc.result;
  check(call.res, {
    'my_tool: status 200': (r) => r.status === 200,
    'my_tool: no JSON-RPC error': () => !!call.rpc && !call.rpc.error,
    'my_tool: isError not true': () => !!result && result.isError !== true,
  });
  // The session is gone: leave the iteration instead of sending the
  // remaining calls without one - paced, like every other iteration.
  if (call.sessionLost) {
    sleep(1);
    return;
  }
  sleep(1);
}
```

Verified live (this machine, 2026-09-06): assembled with `parseRpc()`
and `headerValue()`, `k6 inspect` exits 0, and one iteration against a
running MCP server (Python SDK 2.1.1, streamable HTTP, the tool name
replaced by one the server exposes) answers `initialize`,
`notifications/initialized` and the `tools/call` with 7 of 7 checks
passed and 0 of 3 requests failed.

`tags: { name }` on every request is what makes a per-operation
threshold possible - a `tools/call` costing a subprocess and an
in-process `tools/list` share `http_req_duration` otherwise, and one
whole-run percentile then measures neither (scripting.md, "Requests,
checks, thresholds").
