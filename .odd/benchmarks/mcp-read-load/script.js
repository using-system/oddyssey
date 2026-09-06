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

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8802';
const MCP_URL = `${BASE_URL}/mcp`;
// Run identity, carried the way the package's run-scenario skill does:
// a User-Agent naming the benchmark, the run slug appended when the
// caller passes one (-e RUN_SLUG=<slug>) - never substituted.
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-load' + (RUN_SLUG ? '/' + RUN_SLUG : '');
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
