# Protocol support beyond plain HTTP

Official docs: https://grafana.com/docs/k6/latest/using-k6/protocols/

Native (verified 2026-08, `using-k6/protocols`):

- **HTTP/1.1** - the default.
- **HTTP/2** - k6 upgrades automatically if the server reports support.
- **WebSockets** - a different test structure and VU lifecycle than
  request/response protocols - read the dedicated page before scripting
  one.
- **gRPC** - via `k6/net/grpc`.

Beyond those, via `xk6` extensions (not in core k6, a separate build
step): SQL, Kafka, ZeroMQ, Redis, and others.

An **MCP server** is not a protocol k6 needs support for: its streamable
HTTP transport is plain `POST` over HTTP/1.1, driven with `k6/http`. It
does carry a handshake, a session header and event-stream bodies that a
script must handle explicitly - [mcp.md](mcp.md).

Relevant when the target service isn't a plain HTTP API -
`k6-benchmark-expert` checks this reference before assuming HTTP is the
right protocol for a benchmark.
