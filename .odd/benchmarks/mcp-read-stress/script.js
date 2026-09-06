// mcp-read-stress - stress test of the oddyssey-mcp read surface over the
// MCP streamable HTTP transport. See manifest.yaml beside this file for the
// target, the load shape, the pacing, the thresholds and the validation
// record. Authored by k6-benchmark-expert; run through /odd-observe, never
// by hand.
//
// One MCP session per VU: the first iteration of a VU sends `initialize`
// (the server answers with an `mcp-session-id` header) and
// `notifications/initialized`; every later request of that VU carries the
// session id. A session the server no longer knows (HTTP 404) is dropped
// and re-created on the next iteration, so a server restart mid-run shows
// up as a burst of initializes, not as a VU stuck on 404 for the rest of
// the run.
//
// Every iteration: tools/list, tools/call odd_config_get, tools/call
// odd_stack_status, then a fixed think time (the pacing - see manifest).
// Only the read surface is exercised: never odd_stack_up, odd_stack_down,
// odd_stack_reset (they act on the machine-wide shared stack) and never
// odd_config_set.

import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { sha256 } from 'k6/crypto';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8803';
const MCP_URL = `${BASE_URL}/mcp`;
const BENCHMARK = 'mcp-read-stress';
// The run identity travels in the User-Agent (run-scenario's identity
// reference): the benchmark's name, plus the run slug when the caller
// passes one (-e RUN_SLUG=<slug>) so two runs stay apart in the telemetry.
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = `odd-bench/${BENCHMARK}` + (RUN_SLUG ? '/' + RUN_SLUG : '');

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

// The initialize handshake proposes this version; the server answers with
// the one it negotiated, which later requests then carry in the
// MCP-Protocol-Version header.
const PROPOSED_PROTOCOL_VERSION = '2025-06-18';
const THINK_TIME_S = 1;

export const options = {
  // The documented recommendation: discard every body by default, and set
  // responseType: 'text' on exactly the requests whose body is read below
  // (initialize, tools/list, tools/call). The notification's body is not
  // read.
  discardResponseBodies: true,
  scenarios: {
    read_stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '5m', target: 50 }, // ramp: 0 -> 50 VUs
        { duration: '2m', target: 50 }, // hold: 50 VUs (steady state)
        { duration: '1m', target: 0 }, // ramp-down: 50 -> 0 VUs
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    // The caller's one pass/fail target (issue #424): under 5 % of the
    // requests may fail (HTTP status >= 400 or a transport error).
    http_req_failed: ['rate<0.05'],
  },
};

// Per-VU state: each VU runs its own JS runtime, so these module-level
// variables are one session per VU.
let sessionId = null;
let protocolVersion = null;
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

function headers(extra) {
  const h = {
    'Content-Type': 'application/json',
    // The streamable HTTP transport requires both media types in Accept
    // (it answers 406 otherwise).
    Accept: 'application/json, text/event-stream',
    'User-Agent': USER_AGENT,
  };
  if (sessionId) {
    h['Mcp-Session-Id'] = sessionId;
  }
  if (protocolVersion) {
    h['MCP-Protocol-Version'] = protocolVersion;
  }
  if (SEND_TRACEPARENT) {
    h.traceparent = traceparent();
  }
  return Object.assign(h, extra || {});
}

// The server answers a request POST with a text/event-stream body carrying
// one `data: <json-rpc message>` event per message. Return the JSON-RPC
// response whose id matches, or null when the body carries none.
function parseSseResponse(res, id) {
  if (!res.body) {
    return null;
  }
  const contentType = res.headers['Content-Type'] || '';
  if (contentType.indexOf('application/json') === 0) {
    try {
      return JSON.parse(res.body);
    } catch (e) {
      return null;
    }
  }
  const lines = res.body.split('\n');
  let found = null;
  for (const line of lines) {
    if (line.indexOf('data:') !== 0) {
      continue;
    }
    try {
      const message = JSON.parse(line.slice(5).trim());
      if (message && message.id === id) {
        found = message;
      }
    } catch (e) {
      // a non-JSON data line (a keep-alive) is not a response
    }
  }
  return found;
}

function forgetSessionIfGone(res) {
  // 404: the server no longer knows this session (terminated, or the
  // server restarted). The next iteration re-initializes.
  if (res.status === 404) {
    sessionId = null;
    protocolVersion = null;
  }
}

function rpc(method, params, name) {
  const id = nextId++;
  const payload = { jsonrpc: '2.0', id: id, method: method };
  if (params !== undefined) {
    payload.params = params;
  }
  const res = http.post(MCP_URL, JSON.stringify(payload), {
    headers: headers(),
    responseType: 'text', // this body is read below
    tags: { name: name },
  });
  forgetSessionIfGone(res);
  return { res: res, message: parseSseResponse(res, id) };
}

function initializeSession() {
  const { res, message } = rpc(
    'initialize',
    {
      protocolVersion: PROPOSED_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: 'k6-mcp-read-stress', version: '1' },
    },
    'initialize'
  );
  const ok = check(res, {
    'initialize: status 200': (r) => r.status === 200,
    'initialize: session id header': (r) => !!r.headers['Mcp-Session-Id'],
  });
  check(message, {
    'initialize: result carries protocolVersion': (m) =>
      !!(m && m.result && m.result.protocolVersion),
  });
  if (!ok) {
    return false;
  }
  sessionId = res.headers['Mcp-Session-Id'];
  protocolVersion =
    message && message.result && message.result.protocolVersion
      ? message.result.protocolVersion
      : null;

  // The client acknowledges before any tools/* request; a notification is
  // answered 202 with no body (not read - global discard applies).
  const ack = http.post(
    MCP_URL,
    JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
    { headers: headers(), tags: { name: 'notifications/initialized' } }
  );
  forgetSessionIfGone(ack);
  check(ack, {
    'notifications/initialized: status 202': (r) => r.status === 202,
  });
  return sessionId !== null;
}

function toolsList() {
  const { res, message } = rpc('tools/list', {}, 'tools/list');
  check(res, { 'tools/list: status 200': (r) => r.status === 200 });
  check(message, {
    'tools/list: lists the read tools': (m) => {
      if (!m || !m.result || !Array.isArray(m.result.tools)) {
        return false;
      }
      const names = m.result.tools.map((t) => t.name);
      return (
        names.indexOf('odd_config_get') !== -1 &&
        names.indexOf('odd_stack_status') !== -1
      );
    },
  });
}

function toolsCall(tool) {
  const name = `tools/call ${tool}`;
  const { res, message } = rpc(
    'tools/call',
    { name: tool, arguments: {} },
    name
  );
  check(res, { [`${name}: status 200`]: (r) => r.status === 200 });
  check(message, {
    // A tool failure is an HTTP 200 carrying a JSON-RPC error or
    // result.isError: only a check sees it, http_req_failed never does.
    [`${name}: result without error`]: (m) =>
      !!(m && m.result && !m.error && m.result.isError !== true),
  });
}

export default function () {
  if (!sessionId) {
    if (!initializeSession()) {
      sleep(THINK_TIME_S);
      return;
    }
  }
  // A 404 drops the session (forgetSessionIfGone): the remaining calls of
  // this iteration are skipped so one lost session is one failed request,
  // not three; the next iteration re-initializes.
  toolsList();
  if (sessionId) {
    toolsCall('odd_config_get');
  }
  if (sessionId) {
    toolsCall('odd_stack_status');
  }
  sleep(THINK_TIME_S); // the pacing - manifest.yaml records it
}
