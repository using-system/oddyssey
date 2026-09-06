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
// Optional: -e RUN_SLUG=<slug>, appended to the User-Agent.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8804';
const MCP_URL = `${BASE_URL}/mcp`;
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-soak' + (RUN_SLUG ? '/' + RUN_SLUG : '');
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
