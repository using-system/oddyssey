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
// See manifest.yaml beside this file for the profile, the thresholds and
// the validation record. An authoring mission never runs this script as a
// benchmark: /odd-observe runs it.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8806';
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-breakpoint' + (RUN_SLUG ? '/' + RUN_SLUG : '');
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
