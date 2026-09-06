// mcp-read-spike - a k6 spike benchmark of the oddyssey-mcp server's read
// surface over the MCP SDK's streamable HTTP transport.
//
// See manifest.yaml next to this file for the target, the launcher, the
// profile with its stage boundaries, the pacing, the thresholds and the
// validation record. Never run this file by hand as a benchmark: the
// /odd-observe prompt drives it (run-scenario's benchmark-replay reference).
//
// One MCP session per VU: the first iteration of a VU sends `initialize`
// (which answers the session id) and `notifications/initialized`; every
// iteration then sends `tools/list`, `tools/call odd_config_get` and
// `tools/call odd_stack_status`. Read surface only - never a tool that acts
// on the machine-wide shared stack (odd_stack_up/down/reset) nor on the
// configuration (odd_config_set).

import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';

// Mission-time inputs: -e BASE_URL=http://127.0.0.1:8805 (the default is
// the local launcher the manifest describes, never a remote target) and
// -e RUN_SLUG=<run slug> (appended to the User-Agent; the benchmark name
// always stays in it).
const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8805';
const MCP_URL = `${BASE_URL}/mcp`;
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-spike' + (RUN_SLUG ? '/' + RUN_SLUG : '');
const PROTOCOL_VERSION = '2025-06-18';
const READ_TOOLS = ['odd_config_get', 'odd_stack_status'];

// The load shape confirmed by the caller (issue #424), in order. The stage
// names below are the `stage` tag every request and check carries, so a
// threshold can be scoped to one stage - the boundaries are cumulative
// seconds since the scenario started, derived from this same array.
const STAGES = [
  { name: 'baseline', duration: '30s', target: 1 },
  { name: 'ramp-up', duration: '10s', target: 100 },
  { name: 'burst', duration: '30s', target: 100 },
  { name: 'ramp-down', duration: '10s', target: 1 },
  { name: 'recovery', duration: '30s', target: 1 },
];

const STAGE_ENDS_MS = (() => {
  let total = 0;
  return STAGES.map((s) => {
    total += parseInt(s.duration, 10) * 1000; // durations above are whole seconds
    return total;
  });
})();

export const options = {
  // Discard bodies globally (the documented recommendation); every request
  // whose body the script parses overrides with responseType: 'text'.
  discardResponseBodies: true,
  scenarios: {
    spike: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: STAGES.map((s) => ({ duration: s.duration, target: s.target })),
      // Defaults spelled out so the manifest and the script agree: an
      // iteration in flight when its VU is ramped down, or when the test
      // ends, gets this long to finish.
      gracefulRampDown: '30s',
      gracefulStop: '30s',
    },
  },
  thresholds: {
    // Caller-decided (issue #424): fewer than 10 % of the requests sent
    // during the burst hold may fail (status >= 400 or a transport error).
    'http_req_failed{stage:burst}': ['rate<0.10'],
    // Agent-proposed recovery check, stated as thresholds on the last
    // stage: every request of the recovery answers - no failed request
    // and every check green after the burst.
    'http_req_failed{stage:recovery}': ['rate==0'],
    'checks{stage:recovery}': ['rate==1'],
  },
};

// Per-VU state: each VU has its own JS runtime, so these are one session
// and one JSON-RPC id counter per VU, kept across its iterations.
let session = null; // { id, protocolVersion }
let nextRpcId = 0;

// The stage the scenario is in right now, from the elapsed time since it
// started against the boundaries above.
function currentStage() {
  const elapsed = Date.now() - exec.scenario.startTime;
  for (let i = 0; i < STAGE_ENDS_MS.length; i++) {
    if (elapsed < STAGE_ENDS_MS[i]) {
      return STAGES[i].name;
    }
  }
  // A request sent during the graceful stop after the last stage still
  // belongs to the recovery: it is the last stage's traffic draining.
  return STAGES[STAGES.length - 1].name;
}

function headers() {
  const h = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
    'User-Agent': USER_AGENT,
  };
  if (session !== null) {
    h['Mcp-Session-Id'] = session.id;
    h['MCP-Protocol-Version'] = session.protocolVersion;
  }
  return h;
}

// One response header's first value as a string. k6 v2.2.0 exposes
// res.headers values as strings (verified live, 2026-09-06), while its
// reference page describes arrays - accept both, so the script survives
// either shape.
function headerValue(res, name) {
  const v = res.headers[name];
  if (v === undefined || v === null) {
    return '';
  }
  return Array.isArray(v) ? String(v[0] || '') : String(v);
}

// The transport answers a JSON-RPC request as one SSE stream
// (`event: message` / `data: {...}`), and an error (unknown session, parse
// error) as a plain JSON body. Returns the parsed JSON-RPC message, or null.
function rpcMessage(res) {
  if (res.body === null || res.body === undefined || res.body === '') {
    return null;
  }
  const contentType = headerValue(res, 'Content-Type');
  try {
    if (contentType.indexOf('text/event-stream') === -1) {
      return JSON.parse(res.body);
    }
    let last = null;
    const lines = res.body.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].replace(/\r$/, '');
      if (line.indexOf('data:') === 0) {
        last = line.slice(5).trim();
      }
    }
    return last === null || last === '' ? null : JSON.parse(last);
  } catch (e) {
    return null;
  }
}

// Sends one JSON-RPC message. The `stage` tag is computed here, right
// before the request goes out - never once per iteration - so a request
// sent after a stage boundary carries the new stage: the thresholds are
// scoped on exactly those boundaries. readBody sets responseType: 'text'
// on the requests whose answer rpcMessage() parses; a notification's
// empty 202 is never read. Returns the response and the stage it was sent
// in, so the checks on it carry the same tag.
function send(name, body, readBody) {
  const stage = currentStage();
  const params = { headers: headers(), tags: { name: name, stage: stage } };
  if (readBody) {
    params.responseType = 'text'; // the body is parsed by rpcMessage()
  }
  const res = http.post(MCP_URL, JSON.stringify(body), params);
  if (res.status === 404 && session !== null) {
    // The server no longer knows this session (restarted, or evicted):
    // count the failure and re-initialize on the next request.
    session = null;
  }
  return { res: res, stage: stage };
}

// The tag object every check carries: `stage` scopes the recovery
// thresholds, `name` keeps the per-operation sub-metrics readable.
function checkTags(name, stage) {
  return { name: name, stage: stage };
}

function ensureSession() {
  if (session !== null) {
    return true;
  }
  const init = send(
    'initialize',
    {
      jsonrpc: '2.0',
      id: ++nextRpcId,
      method: 'initialize',
      params: {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: 'k6-mcp-read-spike', version: '1' },
      },
    },
    true
  );
  const initMsg = rpcMessage(init.res);
  const sessionId = headerValue(init.res, 'Mcp-Session-Id');
  const ok = check(
    init.res,
    {
      'initialize: status 200': (r) => r.status === 200,
      'initialize: result carries protocolVersion': () =>
        initMsg !== null &&
        initMsg.result !== undefined &&
        typeof initMsg.result.protocolVersion === 'string',
      'initialize: Mcp-Session-Id header set': () => sessionId !== '',
    },
    checkTags('initialize', init.stage)
  );
  if (!ok) {
    return false;
  }
  session = { id: sessionId, protocolVersion: initMsg.result.protocolVersion };

  // A notification has no id and no response body: the transport
  // acknowledges it with 202 Accepted.
  const notif = send(
    'notifications/initialized',
    { jsonrpc: '2.0', method: 'notifications/initialized' },
    false
  );
  check(
    notif.res,
    { 'notifications/initialized: status 202': (r) => r.status === 202 },
    checkTags('notifications/initialized', notif.stage)
  );
  return true;
}

function toolsList() {
  const name = 'tools/list';
  const sent = send(name, { jsonrpc: '2.0', id: ++nextRpcId, method: name }, true);
  const msg = rpcMessage(sent.res);
  const tools =
    msg !== null && msg.result !== undefined && Array.isArray(msg.result.tools)
      ? msg.result.tools
      : [];
  check(
    sent.res,
    {
      'tools/list: status 200': (r) => r.status === 200,
      'tools/list: lists odd_config_get and odd_stack_status': () =>
        READ_TOOLS.every((wanted) => tools.some((t) => t && t.name === wanted)),
    },
    checkTags(name, sent.stage)
  );
}

function toolsCall(toolName) {
  const name = `tools/call ${toolName}`;
  const sent = send(
    name,
    {
      jsonrpc: '2.0',
      id: ++nextRpcId,
      method: 'tools/call',
      params: { name: toolName, arguments: {} },
    },
    true
  );
  const msg = rpcMessage(sent.res);
  const checks = {};
  checks[`${name}: status 200`] = (r) => r.status === 200;
  checks[`${name}: result, not an error`] = () =>
    msg !== null && msg.result !== undefined && msg.result.isError !== true;
  check(sent.res, checks, checkTags(name, sent.stage));
}

export default function () {
  if (!ensureSession()) {
    // No session: nothing else can be sent this iteration. The failed
    // handshake is on record through its checks; pace all the same, so a
    // server that refuses every initialize is not hammered.
    sleep(1);
    return;
  }
  // After a 404 dropped the session (send() sets it to null), the
  // remaining calls of this iteration are skipped: one lost session is
  // one failed request, not three, and the next iteration re-initializes.
  const calls = [
    () => toolsList(),
    () => toolsCall('odd_config_get'),
    () => toolsCall('odd_stack_status'),
  ];
  for (let i = 0; i < calls.length; i++) {
    if (session === null) {
      break;
    }
    calls[i]();
  }
  // Pacing: one second of think time per iteration (manifest, profile).
  sleep(1);
}
