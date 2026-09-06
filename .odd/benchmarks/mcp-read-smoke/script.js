// Benchmark mcp-read-smoke - the oddyssey-mcp server's read surface over the
// MCP streamable HTTP transport. Authored by k6-benchmark-expert; the
// manifest beside this file (manifest.yaml) records the target, the load
// shape, the thresholds, and the validation.
//
// Read surface only: initialize, tools/list, tools/call odd_config_get,
// tools/call odd_stack_status. Never odd_stack_up, odd_stack_down,
// odd_stack_reset (they act on the machine-wide shared stack) nor
// odd_config_set (it writes the global configuration).
//
// One MCP session per VU: the session is opened on the VU's first
// iteration (init code cannot make HTTP requests) and reused for every
// later iteration - module-level state is per VU in k6; a 404 answer
// drops the session id so the next request re-initializes. One request
// at a time, paced by sleep(PACING_S) at the end of each iteration.

import http from 'k6/http';
import { check, sleep } from 'k6';

// Mission-time inputs. BASE_URL: the streamable HTTP server; the default
// is the local launcher of the manifest, any other target is a
// mission-time decision (-e BASE_URL=<url>). RUN_SLUG: the run's
// identity, appended to the User-Agent (-e RUN_SLUG=<slug>); the
// benchmark name always stays in it.
const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8801';
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/mcp-read-smoke' + (RUN_SLUG ? '/' + RUN_SLUG : '');
const ENDPOINT = `${BASE_URL}/mcp`;
const PROTOCOL_VERSION = '2025-06-18';
const PACING_S = 1;
const READ_TOOLS = ['odd_config_get', 'odd_stack_status'];

export const options = {
  // Discard bodies globally (the documented recommendation); every request
  // whose body the script reads sets responseType: 'text' explicitly.
  discardResponseBodies: true,
  scenarios: {
    read_surface: {
      executor: 'constant-vus',
      vus: 1,
      duration: '1m',
    },
  },
  thresholds: {
    // Every request answers, none fails: an equality, not a small fraction.
    http_req_failed: ['rate==0'],
    // Every check passes.
    checks: ['rate==1.00'],
  },
};

// Per-VU state (init context runs once per VU).
let sessionId = null;
let negotiatedVersion = PROTOCOL_VERSION;
let nextId = 0;

function headers(extra) {
  const base = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
    'User-Agent': USER_AGENT,
  };
  return Object.assign(base, extra || {});
}

function sessionHeaders() {
  return {
    'Mcp-Session-Id': sessionId,
    'MCP-Protocol-Version': negotiatedVersion,
  };
}

// The streamable HTTP transport answers a request with either a JSON body
// or an event stream whose `data:` line carries the JSON-RPC response.
function parseRpc(body) {
  if (!body) {
    return null;
  }
  const trimmed = body.trim();
  try {
    if (trimmed.startsWith('{')) {
      return JSON.parse(trimmed);
    }
    const lines = trimmed.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].startsWith('data:')) {
        return JSON.parse(lines[i].slice(5).trim());
      }
    }
  } catch (e) {
    return null;
  }
  return null;
}

function headerValue(res, name) {
  const value = res.headers[name];
  if (Array.isArray(value)) {
    return value.length > 0 ? value[0] : null;
  }
  return value === undefined ? null : value;
}

// One JSON-RPC request whose response body is read (responseType 'text').
function rpc(name, method, params, extraHeaders) {
  nextId += 1;
  const payload = { jsonrpc: '2.0', id: nextId, method: method };
  if (params !== undefined) {
    payload.params = params;
  }
  const res = http.post(ENDPOINT, JSON.stringify(payload), {
    headers: headers(extraHeaders),
    tags: { name: name },
    responseType: 'text',
  });
  if (res.status === 404 && sessionId !== null) {
    // The server no longer knows this session: drop it so the next
    // request re-initializes. This request's checks record the miss.
    sessionId = null;
  }
  return { res: res, rpc: parseRpc(res.body) };
}

function rpcResult(rpcResponse) {
  if (!rpcResponse || rpcResponse.error || !rpcResponse.result) {
    return null;
  }
  return rpcResponse.result;
}

function toolText(result) {
  if (!result || !Array.isArray(result.content) || result.content.length === 0) {
    return null;
  }
  try {
    return JSON.parse(result.content[0].text);
  } catch (e) {
    return null;
  }
}

function openSession() {
  const init = rpc('initialize', 'initialize', {
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {},
    clientInfo: { name: USER_AGENT, version: '1' },
  });
  const session = headerValue(init.res, 'Mcp-Session-Id');
  const result = rpcResult(init.rpc);
  check(init.res, {
    'initialize: status 200': (r) => r.status === 200,
    'initialize: session id header present': () =>
      typeof session === 'string' && session.length > 0,
    'initialize: result carries protocolVersion': () =>
      result !== null && typeof result.protocolVersion === 'string',
  });
  if (!session || result === null) {
    return false;
  }
  sessionId = session;
  negotiatedVersion = result.protocolVersion;

  // The client sends notifications/initialized before any tools/call. A
  // notification has no id and no response body to read (202, empty).
  const notified = http.post(
    ENDPOINT,
    JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
    { headers: headers(sessionHeaders()), tags: { name: 'notifications/initialized' } }
  );
  const accepted = check(notified, {
    'notifications/initialized: status 202': (r) => r.status === 202,
  });
  if (!accepted) {
    sessionId = null;
    return false;
  }
  return true;
}

export default function () {
  if (sessionId === null && !openSession()) {
    // No session: the checks above already recorded the failure; pace and
    // let the next iteration retry the handshake.
    sleep(PACING_S);
    return;
  }

  const list = rpc('tools/list', 'tools/list', undefined, sessionHeaders());
  const listResult = rpcResult(list.rpc);
  const toolNames =
    listResult && Array.isArray(listResult.tools) ? listResult.tools.map((t) => t.name) : [];
  check(list.res, {
    'tools/list: status 200': (r) => r.status === 200,
    'tools/list: no JSON-RPC error': () => listResult !== null,
    'tools/list: lists the two read tools': () =>
      READ_TOOLS.every((name) => toolNames.indexOf(name) !== -1),
  });

  // A 404 drops the session inside rpc(): the remaining calls of this
  // iteration are skipped - one lost session is one failed request, not
  // three - and the next iteration re-initializes.
  if (sessionId) {
    const configGet = rpc(
      'tools/call odd_config_get',
      'tools/call',
      { name: 'odd_config_get', arguments: {} },
      sessionHeaders()
    );
    const configResult = rpcResult(configGet.rpc);
    const configText = toolText(configResult);
    check(configGet.res, {
      'odd_config_get: status 200': (r) => r.status === 200,
      'odd_config_get: no JSON-RPC error': () => configResult !== null,
      'odd_config_get: isError not true': () =>
        configResult !== null && configResult.isError !== true,
      'odd_config_get: result names the configured stack': () =>
        configText !== null && typeof configText.stack === 'string',
    });
  }

  if (sessionId) {
    const status = rpc(
      'tools/call odd_stack_status',
      'tools/call',
      { name: 'odd_stack_status', arguments: {} },
      sessionHeaders()
    );
    const statusResult = rpcResult(status.rpc);
    const statusText = toolText(statusResult);
    check(status.res, {
      'odd_stack_status: status 200': (r) => r.status === 200,
      'odd_stack_status: no JSON-RPC error': () => statusResult !== null,
      'odd_stack_status: isError not true': () =>
        statusResult !== null && statusResult.isError !== true,
      // A down stack is a status (running: false), never an error.
      'odd_stack_status: result carries running': () =>
        statusText !== null && typeof statusText.running === 'boolean',
    });
  }

  sleep(PACING_S);
}
