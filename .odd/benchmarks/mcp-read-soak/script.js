// mcp-read-soak - a k6 soak over the read surface of oddyssey-mcp.
//
// Target: the oddyssey MCP server served on the MCP SDK's streamable HTTP
// transport (POST <BASE_URL>/mcp). The packaged server speaks stdio; the
// manifest names the launcher that starts the same code on this transport.
//
// Load: 10 VUs held for one hour, one MCP session per VU kept across
// iterations (a leak per session or per request shows), paced with
// sleep(1) at the end of every iteration. Read operations only: initialize
// and notifications/initialized once per VU, then tools/list,
// tools/call odd_config_get and tools/call odd_stack_status per iteration.
// Never odd_stack_up / odd_stack_down / odd_stack_reset (they act on the
// machine-wide shared stack) nor odd_config_set.
//
// Mission-time input: -e BASE_URL=http://127.0.0.1:<port> (default below).
// Optional: -e RUN_SLUG=<slug>, appended to the User-Agent, and
// -e SEND_TRACEPARENT (presence, whatever the value) on a remote drive.

import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { sha256 } from 'k6/crypto';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8804';
const MCP_URL = `${BASE_URL}/mcp`;
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-soak' + (RUN_SLUG ? '/' + RUN_SLUG : '');

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

const REQUESTED_PROTOCOL_VERSION = '2025-06-18';
const PACING_S = 1;

export const options = {
  // Discard bodies globally (memory on the load generator); the requests
  // whose SSE body the script reads set responseType: 'text' explicitly.
  discardResponseBodies: true,
  scenarios: {
    read_soak: {
      executor: 'constant-vus',
      vus: 10,
      duration: '1h',
      gracefulStop: '30s',
    },
  },
  // Thresholds are scoped per operation through the `name` tag every
  // request sets below; there is deliberately no whole-run duration
  // threshold: odd_stack_status has a structural latency floor (three
  // docker CLI subprocesses and four readiness probes per call, see the
  // manifest) that would bound a whole-run p(99).
  thresholds: {
    'http_req_duration{name:tools/list}': ['p(99)<100'],
    'http_req_duration{name:tools/call odd_config_get}': ['p(99)<100'],
    'http_req_duration{name:tools/call odd_stack_status}': ['p(99)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

// Per-VU state: each VU runs its own JS runtime, so these module-level
// variables are one session, one negotiated protocol version and one id
// counter per VU.
let sessionId = null;
let protocolVersion = REQUESTED_PROTOCOL_VERSION;
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
  if (sessionId !== null) {
    h['Mcp-Session-Id'] = sessionId;
    h['MCP-Protocol-Version'] = protocolVersion;
  }
  if (SEND_TRACEPARENT) {
    h.traceparent = traceparent();
  }
  return h;
}

function rpc(method, params) {
  const msg = { jsonrpc: '2.0', id: nextId, method };
  nextId += 1;
  if (params !== undefined) {
    msg.params = params;
  }
  return JSON.stringify(msg);
}

// The streamable HTTP transport answers a request with an SSE stream that
// closes once the JSON-RPC response has been sent: the body is
// "event: message\ndata: {...}\n\n". Return the parsed JSON-RPC message.
function sseResult(res) {
  if (res.body === null || res.body === undefined) {
    return null;
  }
  const lines = String(res.body).split('\n');
  for (const line of lines) {
    if (line.startsWith('data:')) {
      try {
        return JSON.parse(line.slice(5).trim());
      } catch (e) {
        return null;
      }
    }
  }
  return null;
}

// A 404 means the server no longer knows this session: drop it so the
// next request re-initializes instead of failing for the rest of the run.
function forgetSessionOn404(res) {
  if (res.status === 404) {
    sessionId = null;
  }
}

// Returns true when the session is open; a failed handshake is recorded
// through its checks and the caller sleeps and returns.
function openSession() {
  const init = http.post(
    MCP_URL,
    rpc('initialize', {
      protocolVersion: REQUESTED_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: USER_AGENT, version: '1' },
    }),
    {
      headers: headers(),
      tags: { name: 'initialize' },
      responseType: 'text', // the SSE body is read below
    },
  );
  const sid = init.headers['Mcp-Session-Id'];
  const initResult = sseResult(init);
  const ok = check(init, {
    'initialize: status 200': (r) => r.status === 200,
    'initialize: session id issued': () => typeof sid === 'string' && sid.length > 0,
    'initialize: protocol version negotiated': () =>
      initResult !== null &&
      initResult.result !== undefined &&
      typeof initResult.result.protocolVersion === 'string',
  });
  if (!ok) {
    sessionId = null;
    return false;
  }
  sessionId = sid;
  protocolVersion = initResult.result.protocolVersion;

  const notified = http.post(
    MCP_URL,
    JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
    { headers: headers(), tags: { name: 'notifications/initialized' } },
  );
  check(notified, {
    'notifications/initialized: status 202': (r) => r.status === 202,
  });
  forgetSessionOn404(notified);
  return sessionId !== null;
}

function callTool(name) {
  const res = http.post(
    MCP_URL,
    rpc('tools/call', { name, arguments: {} }),
    {
      headers: headers(),
      tags: { name: `tools/call ${name}` },
      responseType: 'text', // the SSE body is read below
    },
  );
  const msg = sseResult(res);
  check(res, {
    [`${name}: status 200`]: (r) => r.status === 200,
    [`${name}: result without isError`]: () =>
      msg !== null && msg.result !== undefined && msg.result.isError !== true,
  });
  forgetSessionOn404(res);
}

export default function () {
  if (sessionId === null && !openSession()) {
    sleep(PACING_S);
    return;
  }

  const list = http.post(MCP_URL, rpc('tools/list'), {
    headers: headers(),
    tags: { name: 'tools/list' },
    responseType: 'text', // the SSE body is read below
  });
  const listed = sseResult(list);
  const toolNames =
    listed !== null && listed.result !== undefined && Array.isArray(listed.result.tools)
      ? listed.result.tools.map((t) => t.name)
      : [];
  check(list, {
    'tools/list: status 200': (r) => r.status === 200,
    'tools/list: lists odd_config_get and odd_stack_status': () =>
      toolNames.includes('odd_config_get') && toolNames.includes('odd_stack_status'),
  });
  forgetSessionOn404(list);

  // A 404 dropped the session: skip the remaining calls of this iteration
  // (one lost session is one failed request, not three); the next
  // iteration re-initializes.
  if (sessionId !== null) {
    callTool('odd_config_get');
  }
  if (sessionId !== null) {
    callTool('odd_stack_status');
  }

  sleep(PACING_S);
}
