// llmbench-store-load - load benchmark of the llms-benchmark demo store.
//
// Two scenarios, one script (see manifest.yaml, "profile"):
//
//   catalog    the default function - 5 constant VUs for 2 minutes, ~1 s
//              of sleep per iteration. One shopper's pass over the store:
//              browse a category, search inside it, read a product, ask
//              for the catalog-wide stats, place an order and read it
//              back - over the API directly, and over the four MCP tools
//              the assistant itself would call, on one MCP session per VU
//              kept across the VU's iterations.
//
//   assistant  exec: 'assistant' - constant-arrival-rate, one iteration
//              every 15 s for 2 minutes (8 iterations), each posting one
//              customer question to the agent's POST /ask. THE RATE IS A
//              CEILING, NEVER TO BE RAISED: every iteration is a real,
//              paid call to a third-party model provider.
//
// The category, the search term, the SKUs and the question all move with
// the iteration counter, so the run walks the store instead of replaying
// one request.
//
// Three base URLs, all mission-time inputs (manifest: target):
//   API_URL        the catalog API root
//   MCP_BASE_URL   the MCP server's streamable-HTTP endpoint (with /mcp)
//   AGENT_URL      the agent's HTTP root

import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { sha256 } from 'k6/crypto';

const API_URL = __ENV.API_URL || 'http://localhost:8010';
const MCP_URL = __ENV.MCP_BASE_URL || 'http://localhost:8011/mcp';
const AGENT_URL = __ENV.AGENT_URL || 'http://localhost:8012';

// Run identity, carried the way the package's run-scenario skill does:
// a User-Agent naming the benchmark, the run slug appended when the
// caller passes one (-e RUN_SLUG=<slug>) - never substituted.
const RUN_SLUG = __ENV.RUN_SLUG || '';
const USER_AGENT = 'odd-bench/llmbench-store-load' + (RUN_SLUG ? '/' + RUN_SLUG : '');

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
//                     system variables too. The drive decides it: a remote
//                     drive sets it (the requests are the only identity there
//                     is), a local drive leaves it unset - the launched
//                     process already carries service.instance.id and a
//                     synthetic parent would cost the run its trace roots for
//                     nothing.
const SEND_TRACEPARENT = RUN_SLUG !== '' && __ENV.SEND_TRACEPARENT !== undefined;
// The trace id is 32 hex in three parts: the protocol's 8-hex prefix, baked
// in here at authoring time and recorded in the manifest (that literal is
// what the run's rows carry, whatever prefix the protocol names later);
// 8 hex derived from the run slug, hashed once in init and constant for the
// run; and the 16-hex sequence field below, which is also the span id.
const TRACEPARENT_PREFIX = '0ddc0ffe';
const SLUG_HEX = SEND_TRACEPARENT ? sha256(RUN_SLUG, 'hex').slice(0, 8) : '';

const PACING_S = 1; // sleep at the end of every catalog iteration (manifest: profile.pacing)

const CLIENT_PROTOCOL_VERSION = '2025-06-18';
const HANDSHAKE_VERSIONS = ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'];

// The store's own vocabulary, so the traffic looks like shopping rather
// than a replayed fixture.
const CATEGORIES = [
  'audio',
  'bikes',
  'cameras',
  'climbing',
  'coffee',
  'desks',
  'kitchen',
  'lighting',
  'outdoor',
  'running',
  'storage',
  'tools',
];
const SEARCH_TERMS = [
  'compact',
  'rugged',
  'featherweight',
  'insulated',
  'modular',
  'quiet',
  'frame',
  'grinder',
  'harness',
  'lantern',
  'pannier',
  'riser',
  'sleeve',
];
// One question per assistant iteration of a 2-minute run (8 of them), so
// the eight walk the four tools the assistant has: search, product
// lookup, an order placed, an order read back.
const QUESTIONS = [
  'Which audio products do you have in stock, and what do the cheapest ones cost?',
  'Find me a rugged bikes pannier and tell me its SKU and price.',
  'What climbing gear do you carry with the word harness in the name?',
  'How much does SKU-00042 cost, and is it in stock?',
  'I want a quiet coffee grinder - what do you recommend, and what does it cost?',
  'Order one unit of SKU-00100 for customer odd-bench, then tell me the order reference.',
  'Look up order ORD-000001 and tell me what was bought, or say plainly if it does not exist.',
  'Which lighting products are the most expensive, and are any of them out of stock?',
];
// Used only when a catalog listing came back with no product to pick from,
// so an iteration keeps its shape instead of collapsing to a short one.
const FALLBACK_SKUS = ['SKU-00000', 'SKU-00001'];

export const options = {
  // Discard bodies globally (the documented recommendation); every
  // request whose body is read below sets responseType: 'text'.
  discardResponseBodies: true,
  scenarios: {
    catalog: {
      executor: 'constant-vus',
      vus: 5,
      duration: '2m',
      // no `exec`: the default function, so the one-iteration smoke covers it
    },
    assistant: {
      executor: 'constant-arrival-rate',
      duration: '2m',
      rate: 1,
      timeUnit: '15s', // 1 question every 15 s = 8 over the run - a hard ceiling
      preAllocatedVUs: 2,
      maxVUs: 4,
      exec: 'assistant',
    },
  },
  thresholds: {
    // Deliberately fractional rather than equalities: the assistant
    // scenario depends on a third-party model provider, and an occasional
    // hiccup there must not fail the whole benchmark (manifest:
    // thresholds, with the cross-check).
    http_req_failed: ['rate<0.05'],
    checks: ['rate>0.90'],
  },
};

// ---------------------------------------------------------------- identity

// The sequence field, disjoint across every runtime that sends a request:
// the high 8 hex name the runtime, the low 8 hex are that runtime's own
// request counter from 1. k6 gives every runtime its own module state, so
// the counter below counts this runtime's requests and nobody else's, and
// exec.vu.idInTest - globally unique across the whole test run, so the
// catalog VUs and the assistant VUs never share one - keeps the VUs apart.
// setup() and teardown() would be two further runtimes, where
// exec.vu.idInTest reads 0 (verified on k6 v2.2.0, 2026-09-06): ffffffff
// and fffffffe are reserved for them, outside the VU index range - this
// script exports neither and sends every request from VU code, which the
// guard in traceparent() below enforces. No two requests of the run share
// an id, and the field is never all zeros: the counter starts at 1.
let runtimeRequests = 0;

function hex8(n) {
  return (n >>> 0).toString(16).padStart(8, '0');
}

function traceparent() {
  const runtime = exec.vu.idInTest;
  // 0 is setup() or teardown(), which must take a reserved high half of
  // their own: a zero one would give setup's n-th request and teardown's
  // n-th the same id. Neither exists here, so this raises rather than
  // collide silently if a later author sends a request from one.
  if (runtime === 0) {
    throw new Error(
      'traceparent: a request outside VU code needs a reserved runtime id (ffffffff for setup, fffffffe for teardown)',
    );
  }
  runtimeRequests += 1;
  const sequence = hex8(runtime) + hex8(runtimeRequests);
  return `00-${TRACEPARENT_PREFIX}${SLUG_HEX}${sequence}-${sequence}-01`;
}

// ------------------------------------------------------------- one helper

// Every request of this script - catalog, MCP and agent, handshake
// included - goes out through send(), which is where the identity headers
// are set. Nothing calls http.* directly.
function send(verb, url, body, opts) {
  const headers = Object.assign({ 'User-Agent': USER_AGENT }, opts.headers || {});
  if (SEND_TRACEPARENT) {
    headers.traceparent = traceparent();
  }
  const params = { headers: headers, tags: { name: opts.name } };
  if (opts.responseType) params.responseType = opts.responseType;
  if (opts.timeout) params.timeout = opts.timeout;
  return verb === 'GET' ? http.get(url, params) : http.post(url, body, params);
}

// A body the script reads is parsed defensively: a check that throws
// aborts the iteration exactly like a fail(), and the checks below all
// guard the null this returns.
function parseJson(res) {
  if (!res || !res.body) return null;
  try {
    return JSON.parse(res.body);
  } catch (e) {
    return null;
  }
}

// ------------------------------------------------------------------- MCP

// Module scope is per VU (k6 runs the init context once per VU), so these
// hold one MCP session per VU across its iterations.
let sessionId = null;
let negotiated = CLIENT_PROTOCOL_VERSION;
let nextRpcId = 0;

// The streamable HTTP transport answers either a JSON body or an SSE
// stream whose `data:` line carries the JSON-RPC response - parse both,
// and skip an empty priming event rather than handing it to JSON.parse.
function parseRpc(body) {
  if (!body) return null;
  const trimmed = body.trim();
  try {
    if (trimmed.charAt(0) === '{') return JSON.parse(trimmed);
    const lines = trimmed.split('\n');
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      if (line.indexOf('data:') === 0) {
        const payload = line.slice(5).trim();
        if (payload) return JSON.parse(payload);
      }
    }
  } catch (e) {
    return null;
  }
  return null;
}

// k6 v2.2.0 returns a plain string for a header, not the array the
// Response reference describes - tolerate both, and look the name up in
// canonical case.
function headerValue(res, name) {
  const value = res.headers[name];
  if (Array.isArray(value)) return value.length ? value[0] : null;
  return value === undefined ? null : value;
}

function sessionHeaders() {
  return { 'Mcp-Session-Id': sessionId, 'MCP-Protocol-Version': negotiated };
}

// Returns { res, rpc, sessionLost }; rpc is null when the body carries no
// parsable JSON-RPC response, so every caller guards it.
function rpc(name, method, params, extra) {
  const payload = { jsonrpc: '2.0', method: method };
  if (method.indexOf('notifications/') !== 0) {
    nextRpcId += 1;
    payload.id = nextRpcId;
  }
  if (params !== undefined) payload.params = params;
  const isNotification = method.indexOf('notifications/') === 0;
  const res = send('POST', MCP_URL, JSON.stringify(payload), {
    name: name,
    headers: Object.assign(
      {
        'Content-Type': 'application/json',
        Accept: 'application/json, text/event-stream',
      },
      extra || {},
    ),
    // A notification answers 202 with an empty body: nothing to read, so
    // no responseType override on it.
    responseType: isNotification ? undefined : 'text',
  });
  let sessionLost = false;
  if (res.status === 404 && sessionId !== null) {
    // The server no longer knows this session (restarted, or evicted):
    // drop the id so the next iteration re-initializes.
    sessionId = null;
    sessionLost = true;
  }
  return { res: res, rpc: isNotification ? null : parseRpc(res.body), sessionLost: sessionLost };
}

function openSession() {
  const init = rpc('initialize', 'initialize', {
    protocolVersion: CLIENT_PROTOCOL_VERSION,
    capabilities: {},
    clientInfo: { name: 'odd-bench-llmbench-store-load', version: '1' },
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

  const ack = rpc(
    'notifications/initialized',
    'notifications/initialized',
    undefined,
    sessionHeaders(),
  );
  if (!check(ack.res, { 'notifications/initialized: status 202': (r) => r.status === 202 })) {
    sessionId = null;
    return false;
  }

  // What every MCP client does once per session before its first call.
  const listed = rpc('tools/list', 'tools/list', undefined, sessionHeaders());
  const tools = listed.rpc && listed.rpc.result && listed.rpc.result.tools;
  check(listed.res, { 'tools/list: status 200': (r) => r.status === 200 });
  check(tools, {
    'tools/list: the four store tools are exposed': (t) => {
      if (!Array.isArray(t)) return false;
      const names = t.map((tool) => tool.name);
      return (
        names.indexOf('search_products') !== -1 &&
        names.indexOf('get_product') !== -1 &&
        names.indexOf('get_order') !== -1 &&
        names.indexOf('place_order') !== -1
      );
    },
  });
  return true;
}

// One tools/call, with the three assertions a tool call needs: a tool
// failure answers HTTP 200 with a JSON-RPC error or isError, and
// http_req_failed never sees either.
function toolCall(tool, args) {
  const call = rpc(`tools/call ${tool}`, 'tools/call', { name: tool, arguments: args }, sessionHeaders());
  const result = call.rpc && call.rpc.result;
  check(call.res, {
    [`${tool}: status 200`]: (r) => r.status === 200,
    [`${tool}: no JSON-RPC error`]: () => !!call.rpc && !call.rpc.error,
    [`${tool}: isError not true`]: () => !!result && result.isError !== true,
  });
  return { result: result, sessionLost: call.sessionLost };
}

// A tool answers with a content array whose first text part is the JSON
// the tool returned; null when it is shaped otherwise.
function toolPayload(result) {
  if (!result || !Array.isArray(result.content) || !result.content.length) return null;
  const first = result.content[0];
  if (!first || typeof first.text !== 'string') return null;
  try {
    return JSON.parse(first.text);
  } catch (e) {
    return null;
  }
}

// ------------------------------------------------------ the catalog shopper

function pickSku(listing, offset, fallbackIndex) {
  if (listing && Array.isArray(listing.products) && listing.products.length) {
    const product = listing.products[offset % listing.products.length];
    if (product && typeof product.sku === 'string') return product.sku;
  }
  return FALLBACK_SKUS[fallbackIndex % FALLBACK_SKUS.length];
}

export default function () {
  const step = exec.scenario.iterationInTest;
  const category = CATEGORIES[step % CATEGORIES.length];
  const term = SEARCH_TERMS[(step * 5) % SEARCH_TERMS.length];
  const customer = `odd-bench-vu${exec.vu.idInTest}`;

  // 1. Browse a category - the listing a shopper lands on.
  const listingRes = send(
    'GET',
    `${API_URL}/products?category=${encodeURIComponent(category)}`,
    null,
    { name: 'GET /products?category', responseType: 'text' },
  );
  const listing = parseJson(listingRes);
  check(listingRes, { 'GET /products?category: status 200': (r) => r.status === 200 });
  check(listing, {
    'GET /products?category: the listing carries products': (d) =>
      d !== null && Array.isArray(d.products) && typeof d.count === 'number',
  });

  const apiSku = pickSku(listing, step * 13 + 1, 0);
  const mcpSku = pickSku(listing, step * 29 + 7, 1);

  // 2. Narrow the listing with a search term.
  const searchRes = send(
    'GET',
    `${API_URL}/products?category=${encodeURIComponent(category)}&q=${encodeURIComponent(term)}`,
    null,
    { name: 'GET /products?category&q', responseType: 'text' },
  );
  const search = parseJson(searchRes);
  check(searchRes, { 'GET /products?category&q: status 200': (r) => r.status === 200 });
  check(search, {
    'GET /products?category&q: the search answered with a count': (d) =>
      d !== null && typeof d.count === 'number',
  });

  // 3. Open one product.
  const productRes = send('GET', `${API_URL}/products/${apiSku}`, null, {
    name: 'GET /products/{sku}',
    responseType: 'text',
  });
  const product = parseJson(productRes);
  check(productRes, { 'GET /products/{sku}: status 200': (r) => r.status === 200 });
  check(product, {
    'GET /products/{sku}: the requested SKU came back': (d) => d !== null && d.sku === apiSku,
  });

  // 4. The catalog-wide view. Its body is not read, so it stays discarded.
  const statsRes = send('GET', `${API_URL}/stats`, null, { name: 'GET /stats' });
  check(statsRes, { 'GET /stats: status 200': (r) => r.status === 200 });

  // 5. Buy it.
  const orderRes = send(
    'POST',
    `${API_URL}/orders`,
    JSON.stringify({ sku: apiSku, quantity: 1, customer: customer }),
    {
      name: 'POST /orders',
      headers: { 'Content-Type': 'application/json' },
      responseType: 'text',
    },
  );
  const order = parseJson(orderRes);
  check(orderRes, { 'POST /orders: status 200': (r) => r.status === 200 });
  check(order, {
    'POST /orders: answered with an order reference or a stated reason': (d) =>
      d !== null && (typeof d.order_ref === 'string' || typeof d.error === 'string'),
  });
  const apiOrderRef = order && typeof order.order_ref === 'string' ? order.order_ref : null;

  // 6. Read the order back - only when one was accepted.
  if (apiOrderRef) {
    const readRes = send('GET', `${API_URL}/orders/${apiOrderRef}`, null, {
      name: 'GET /orders/{order_ref}',
      responseType: 'text',
    });
    const read = parseJson(readRes);
    check(readRes, { 'GET /orders/{order_ref}: status 200': (r) => r.status === 200 });
    check(read, {
      'GET /orders/{order_ref}: the requested reference came back': (d) =>
        d !== null && d.order_ref === apiOrderRef,
    });
  }

  // 7. The same conversation through the MCP tools the assistant uses.
  if (sessionId === null && !openSession()) {
    // Failed handshake: recorded by its checks; nothing else can be sent
    // this iteration, the next one retries.
    sleep(PACING_S);
    return;
  }

  const searched = toolCall('search_products', { query: term, category: category });
  if (searched.sessionLost) {
    sleep(PACING_S);
    return;
  }

  const fetched = toolCall('get_product', { sku: mcpSku });
  if (fetched.sessionLost) {
    sleep(PACING_S);
    return;
  }

  const placed = toolCall('place_order', { sku: mcpSku, quantity: 1, customer: customer });
  if (placed.sessionLost) {
    sleep(PACING_S);
    return;
  }
  const placedPayload = toolPayload(placed.result);
  const mcpOrderRef =
    placedPayload && typeof placedPayload.order_ref === 'string' ? placedPayload.order_ref : null;

  // 8. Look the order up through the tools - only when one was accepted.
  const lookupRef = mcpOrderRef || apiOrderRef;
  if (lookupRef) {
    toolCall('get_order', { order_ref: lookupRef });
  }

  sleep(PACING_S);
}

// ---------------------------------------------------- the assistant scenario

// One customer question per iteration. The arrival rate paces it - no
// sleep at the end of an arrival-rate iteration - and that rate is a
// ceiling: every iteration here is a real, paid model call.
export function assistant() {
  const question = QUESTIONS[exec.scenario.iterationInTest % QUESTIONS.length];
  const res = send('POST', `${AGENT_URL}/ask`, JSON.stringify({ question: question }), {
    name: 'POST /ask',
    headers: { 'Content-Type': 'application/json' },
    responseType: 'text',
    // An answer costs a model round trip and the tool calls it makes;
    // the timeout is generous so a normal answer is never recorded as a
    // transport failure.
    timeout: '120s',
  });
  const body = parseJson(res);
  check(res, { 'POST /ask: status 200': (r) => r.status === 200 });
  check(body, {
    'POST /ask: an answer came back': (d) =>
      d !== null && typeof d.answer === 'string' && d.answer.length > 0,
  });
}
