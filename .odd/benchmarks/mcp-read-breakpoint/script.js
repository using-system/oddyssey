// mcp-read-breakpoint - k6 breakpoint benchmark for the read surface of
// oddyssey-mcp served over the MCP SDK's streamable HTTP transport.
//
// One MCP session per VU: a VU's first iteration runs `initialize` and
// `notifications/initialized` and keeps the session id; every iteration
// then sends `tools/list`, `tools/call odd_config_get` and
// `tools/call odd_stack_status`. Load ramps by arrival rate (open model,
// the k6 breakpoint guidance) from 1 to 200 iterations/s over 10 minutes,
// with at most 200 VUs; the arrival rate is the pacing - the only `sleep`
// is the 1 s back-off on the failed-handshake early return below.
//
// Mission-time inputs (k6 -e KEY=value):
//   BASE_URL  the server's base URL (default http://127.0.0.1:8806)
//   RUN_SLUG  the run's identity, appended to the User-Agent:
//             odd-bench/mcp-read-breakpoint[/<slug>]
//   SEND_TRACEPARENT
//             present (whatever its value) on a remote drive, unset on a
//             local one: the second gate of the traceparent below
// See manifest.yaml beside this file for the profile, the thresholds and
// the validation record. An authoring mission never runs this script as a
// benchmark: /odd-observe runs it.

import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { sha256 } from 'k6/crypto';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8806';
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-breakpoint' + (RUN_SLUG ? '/' + RUN_SLUG : '');

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

const MCP_URL = `${BASE_URL}/mcp`;
// The version the client proposes; the server's answer wins for the
// session (read from the initialize result, sent back as MCP-Protocol-Version).
const CLIENT_PROTOCOL_VERSION = '2025-06-18';

export const options = {
  discardResponseBodies: true,
  scenarios: {
    read_surface: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 200,
      stages: [{ duration: '10m', target: 200 }],
    },
  },
  thresholds: {
    // Breaking points, per operation (the name tag is set on every request below).
    'http_req_duration{name:tools/list}': [
      { threshold: 'p(95)<200', abortOnFail: true, delayAbortEval: '30s' },
    ],
    'http_req_duration{name:tools/call odd_config_get}': [
      { threshold: 'p(95)<200', abortOnFail: true, delayAbortEval: '30s' },
    ],
    // odd_stack_status has a structural floor (three docker CLI subprocesses
    // plus four readiness probes per call): 600 ms, floor acknowledged.
    'http_req_duration{name:tools/call odd_stack_status}': [
      { threshold: 'p(95)<600', abortOnFail: true, delayAbortEval: '30s' },
    ],
    http_req_failed: ['rate<0.05'],
  },
};

// Per-VU state: every VU has its own module scope, so this is one session
// per VU for the whole run.
let sessionId = null;
let protocolVersion = CLIENT_PROTOCOL_VERSION;
let nextId = 0;

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
    'MCP-Protocol-Version': protocolVersion,
  };
  if (sessionId) {
    h['Mcp-Session-Id'] = sessionId;
  }
  if (SEND_TRACEPARENT) {
    h.traceparent = traceparent();
  }
  return h;
}

function headerValue(res, name) {
  const wanted = name.toLowerCase();
  for (const key in res.headers) {
    if (key.toLowerCase() === wanted) {
      return res.headers[key];
    }
  }
  return null;
}

// The SSE body of a POST answer: `event: message` / `data: <json-rpc>` lines,
// closed after the response. Return the message whose id matches, or null.
function rpcMessage(res, id) {
  if (typeof res.body !== 'string') {
    return null;
  }
  const lines = res.body.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.startsWith('data:')) {
      continue;
    }
    const payload = line.slice(5).trim();
    if (!payload) {
      continue;
    }
    try {
      const msg = JSON.parse(payload);
      if (msg && msg.id === id) {
        return msg;
      }
    } catch (e) {
      // not JSON - skip the line
    }
  }
  return null;
}

// One JSON-RPC request; the body is read (responseType text) to check the
// result, the global discard stays for everything else.
function request(method, params, name) {
  const id = ++nextId;
  const body = JSON.stringify({ jsonrpc: '2.0', id, method, params });
  const res = http.post(MCP_URL, body, {
    headers: headers(),
    tags: { name },
    responseType: 'text',
  });
  forgetSessionOn404(res);
  return { id, res, msg: rpcMessage(res, id) };
}

// The SDK answers 404 to an unknown or terminated session id: drop the
// session so the VU's next request re-initializes instead of pinning the
// VU on a dead session for the rest of the run.
function forgetSessionOn404(res) {
  if (res.status === 404) {
    sessionId = null;
    protocolVersion = CLIENT_PROTOCOL_VERSION;
  }
}

function openSession() {
  const init = request(
    'initialize',
    {
      protocolVersion: CLIENT_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: USER_AGENT, version: '1' },
    },
    'initialize'
  );
  const id = headerValue(init.res, 'Mcp-Session-Id');
  const negotiated =
    init.msg && init.msg.result && typeof init.msg.result.protocolVersion === 'string'
      ? init.msg.result.protocolVersion
      : null;
  const ok = check(init.res, {
    'initialize: status 200': (r) => r.status === 200,
    'initialize: session id header': () => typeof id === 'string' && id.length > 0,
    'initialize: result carries protocolVersion': () => negotiated !== null,
  });
  if (!ok) {
    return false;
  }
  sessionId = id;
  protocolVersion = negotiated;

  // A notification: no id, no body to read; 202 Accepted is the answer.
  const notified = http.post(
    MCP_URL,
    JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
    { headers: headers(), tags: { name: 'notifications/initialized' } }
  );
  forgetSessionOn404(notified);
  check(notified, {
    'notifications/initialized: status 202': (r) => r.status === 202,
  });
  return true;
}

function callTool(toolName) {
  const call = request(
    'tools/call',
    { name: toolName, arguments: {} },
    `tools/call ${toolName}`
  );
  check(call.res, {
    [`tools/call ${toolName}: status 200`]: (r) => r.status === 200,
    [`tools/call ${toolName}: result without error`]: () =>
      call.msg !== null &&
      call.msg.error === undefined &&
      call.msg.result !== undefined &&
      call.msg.result.isError !== true,
  });
}

export default function () {
  if (sessionId === null && !openSession()) {
    // No session: the failed handshake is recorded through its checks;
    // back off one second, and the VU's next iteration retries instead of
    // sending requests the server would reject.
    sleep(1);
    return;
  }

  const list = request('tools/list', {}, 'tools/list');
  check(list.res, {
    'tools/list: status 200': (r) => r.status === 200,
    'tools/list: lists the read tools': () => {
      const tools = list.msg && list.msg.result && list.msg.result.tools;
      if (!Array.isArray(tools)) {
        return false;
      }
      const names = tools.map((t) => t.name);
      return names.includes('odd_config_get') && names.includes('odd_stack_status');
    },
  });

  // A 404 dropped the session: skip the rest of this iteration so one lost
  // session is one failed request, not three; the next iteration re-initializes.
  if (sessionId) {
    callTool('odd_config_get');
  }
  if (sessionId) {
    callTool('odd_stack_status');
  }
}
