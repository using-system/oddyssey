// mcp-read-load - load benchmark of the oddyssey-mcp read surface.
//
// Target: the oddyssey MCP server on the MCP SDK's streamable HTTP
// transport (POST /mcp). The packaged server speaks stdio; this is the
// same code on another transport - see manifest.yaml, "target".
//
// One MCP session per VU, opened on first use and kept across the VU's
// iterations: `initialize` and `notifications/initialized` once, then
// `tools/list`, `tools/call odd_config_get` and
// `tools/call odd_stack_status` every iteration, and a sleep of
// PACING_S seconds. A 404 answer means the server no longer knows the
// session: the id is dropped and the next request re-initializes.
// Never odd_stack_up / odd_stack_down / odd_stack_reset / odd_config_set:
// they act on the machine-wide shared stack and on the user's config.

import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { sha256 } from 'k6/crypto';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8802';
const MCP_URL = `${BASE_URL}/mcp`;
// Run identity, carried the way the package's run-scenario skill does:
// a User-Agent naming the benchmark, the run slug appended when the
// caller passes one (-e RUN_SLUG=<slug>) - never substituted.
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-load' + (RUN_SLUG ? '/' + RUN_SLUG : '');

// The run's `traceparent`, behind two independent gates (the authoring
// contract; run-scenario's run-identity reference):
//   RUN_SLUG          no slug, no identity at all - the trace ids would be
//                     the same set on every replay and the runs would merge
//                     under them;
//   SEND_TRACEPARENT  read by PRESENCE, whatever its value: k6 hands every
//                     -e value over as a string, so `-e SEND_TRACEPARENT=0`
//                     and `-e SEND_TRACEPARENT=false` are both truthy
//                     (verified on k6 v2.2.0, 2026-09-06). There is no value
//                     that means off, only leaving the variable out of the
//                     command AND out of the environment - k6 reads exported
//                     system variables too (verified on k6 v2.2.0,
//                     2026-09-06). The drive decides it: a remote drive sets it
//                     (the requests are the only identity there is), a local
//                     drive leaves it unset - the launched process already
//                     carries service.instance.id and a synthetic parent
//                     would cost the run its trace roots for nothing.
const SEND_TRACEPARENT = RUN_SLUG !== '' && __ENV.SEND_TRACEPARENT !== undefined;
// The trace id is 32 hex in three parts: the protocol's 8-hex prefix, baked
// in here at authoring time and recorded in the manifest (that literal is
// what the run's rows carry, whatever prefix the protocol names later);
// 8 hex derived from the run slug, hashed once in init and constant for the
// run; and the 16-hex sequence field below, which is also the span id.
const TRACEPARENT_PREFIX = '0ddc0ffe';
const SLUG_HEX = SEND_TRACEPARENT ? sha256(RUN_SLUG, 'hex').slice(0, 8) : '';

const CLIENT_PROTOCOL_VERSION = '2025-06-18';
const PACING_S = 1; // sleep at the end of every iteration (manifest: profile.pacing)

export const options = {
  // Discard bodies globally (the documented recommendation); every
  // request whose body is read below sets responseType: 'text'.
  discardResponseBodies: true,
  scenarios: {
    read_load: {
      executor: 'constant-vus',
      vus: 10,
      duration: '5m',
    },
  },
  // Per-operation latency targets, keyed on the `name` tag every request
  // below sets (a sub-metric no request populates would pass on nothing).
  // No whole-run duration threshold: odd_stack_status carries a
  // ~120 ms floor (manifest.yaml, thresholds) that would bind it.
  thresholds: {
    'http_req_duration{name:tools/list}': ['p(95)<50'],
    'http_req_duration{name:tools/call odd_config_get}': ['p(95)<50'],
    'http_req_duration{name:tools/call odd_stack_status}': ['p(95)<300'],
    http_req_failed: ['rate<0.01'],
  },
};

// Module scope is per VU (k6 runs the init context once per VU), so
// these hold one MCP session per VU across its iterations.
let sessionId = null;
let protocolVersion = CLIENT_PROTOCOL_VERSION;
let nextId = 1;

// The sequence field, disjoint across every runtime that sends a request:
// the high 8 hex name the runtime, the low 8 hex are that runtime's own
// request counter from 1. k6 gives every runtime its own module state, so
// the counter below counts this runtime's requests and nobody else's, and
// exec.vu.idInTest (>= 1 in VU code) keeps the VUs apart. setup() and
// teardown() are two further runtimes, where exec.vu.idInTest reads 0
// (verified on k6 v2.2.0, 2026-09-06): ffffffff and fffffffe are reserved
// for them, outside the VU index range - this script exports neither and
// sends every request from VU code, which the guard in traceparent() below
// enforces. No two requests of the run share an id, and the field is never
// all zeros: the counter starts at 1.
let runtimeRequests = 0;

function hex8(n) {
  return (n >>> 0).toString(16).padStart(8, '0');
}

// One traceparent per request, from the headers helper below - the single
// helper every request of this script goes through.
function traceparent() {
  const runtime = exec.vu.idInTest;
  // 0 is setup() or teardown(), which must take a reserved high half of
  // their own: a zero one would give setup's n-th request and teardown's
  // n-th the same id. Neither exists here, so this raises rather than
  // collide silently if a later author sends a request from one.
  if (runtime === 0) {
    throw new Error('traceparent: a request outside VU code needs a reserved runtime id (ffffffff for setup, fffffffe for teardown)');
  }
  runtimeRequests += 1;
  const sequence = hex8(runtime) + hex8(runtimeRequests);
  return `00-${TRACEPARENT_PREFIX}${SLUG_HEX}${sequence}-${sequence}-01`;
}

function headers() {
  const h = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
    'User-Agent': USER_AGENT,
  };
  if (sessionId) {
    h['Mcp-Session-Id'] = sessionId;
    h['MCP-Protocol-Version'] = protocolVersion;
  }
  if (SEND_TRACEPARENT) {
    h.traceparent = traceparent();
  }
  return h;
}

// The streamable HTTP transport answers a request with an SSE stream
// holding one `data: <json-rpc response>` event. Return the parsed
// JSON-RPC message, or null when none is found.
function rpcMessage(res) {
  if (!res.body) return null;
  const line = res.body.split('\n').find((l) => l.startsWith('data:'));
  if (!line) return null;
  try {
    return JSON.parse(line.slice(5).trim());
  } catch (e) {
    return null;
  }
}

function rpc(method, params, name) {
  const payload = { jsonrpc: '2.0', id: nextId++, method };
  if (params !== undefined) payload.params = params;
  const res = http.post(MCP_URL, JSON.stringify(payload), {
    headers: headers(),
    tags: { name },
    responseType: 'text', // the JSON-RPC result is read from the SSE body
  });
  if (res.status === 404 && sessionId) {
    // The server no longer knows this session (restarted, or expired):
    // drop the id so the next request opens a fresh one.
    sessionId = null;
  }
  const msg = rpcMessage(res);
  return { res, msg };
}

function toolCall(tool) {
  const { res, msg } = rpc('tools/call', { name: tool, arguments: {} }, `tools/call ${tool}`);
  check(res, {
    [`${tool}: status 200`]: (r) => r.status === 200,
  });
  check(msg, {
    [`${tool}: json-rpc result`]: (m) => m !== null && m.result !== undefined && m.error === undefined,
    [`${tool}: tool result not isError`]: (m) => m !== null && m.result !== undefined && m.result.isError !== true,
  });
}

function openSession() {
  const { res, msg } = rpc(
    'initialize',
    {
      protocolVersion: CLIENT_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: 'odd-bench-mcp-read-load', version: '1' },
    },
    'initialize',
  );
  const id = res.headers['Mcp-Session-Id'];
  check(res, {
    'initialize: status 200': (r) => r.status === 200,
    'initialize: session id header': () => typeof id === 'string' && id.length > 0,
  });
  check(msg, {
    'initialize: json-rpc result': (m) => m !== null && m.result !== undefined && m.error === undefined,
  });
  if (!id) return false;
  sessionId = id;
  if (msg && msg.result && typeof msg.result.protocolVersion === 'string') {
    protocolVersion = msg.result.protocolVersion;
  }
  // A notification has no id and expects no response: the transport
  // answers 202 Accepted with an empty body, so no responseType here.
  const ack = http.post(
    MCP_URL,
    JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
    { headers: headers(), tags: { name: 'notifications/initialized' } },
  );
  check(ack, { 'notifications/initialized: status 202': (r) => r.status === 202 });
  return true;
}

export default function () {
  if (!sessionId && !openSession()) {
    // Failed handshake: recorded by its checks; nothing else can be
    // sent this iteration, the next one retries.
    sleep(PACING_S);
    return;
  }
  const { res, msg } = rpc('tools/list', undefined, 'tools/list');
  check(res, { 'tools/list: status 200': (r) => r.status === 200 });
  check(msg, {
    'tools/list: lists the two read tools': (m) => {
      if (m === null || !m.result || !Array.isArray(m.result.tools)) return false;
      const names = m.result.tools.map((t) => t.name);
      return names.includes('odd_config_get') && names.includes('odd_stack_status');
    },
  });
  if (sessionId) toolCall('odd_config_get');
  if (sessionId) toolCall('odd_stack_status');
  sleep(PACING_S);
}
