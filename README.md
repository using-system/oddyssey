# oddyssey

**A CLI toolbox for Observability-Driven Development (ODD).**

## The idea

Spec-Driven Development gets a coding agent to write the right code. ODD is
the step around it: the agent works **with the telemetry**, not against
stdout — it observes what a service really does before planning, and
verifies with real signals after implementing. An N+1 query is invisible in
logs and unmissable in a trace.

This repo is a toolbox for that, packaged for any coding agent
([APM](https://microsoft.github.io/apm/): Claude Code, Copilot, Cursor,
Codex, Gemini, and friends) — not a fixed measurement product: the agents
and skills compose with whatever the investigation needs.

## The MCP server

One job: **pilot a local Grafana stack with an OpenTelemetry endpoint**.
One container ([grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm),
pinned) exposes Grafana on `:3000` and OTLP on `:4317`/`:4318`; apps export
their telemetry there. Tempo traces, Prometheus metrics, and Loki logs are
all queried through the Grafana datasource proxy
(`:3000/api/datasources/proxy/uid/...`), so the same paths work against any
Grafana; on remote environments the stack behind it can be something other
than the local otel-lgtm container.

| Tool | What it does |
| --- | --- |
| `odd_stack_up` | Start the local stack and wait until it is ready |
| `odd_stack_down` | Stop it |
| `odd_stack_status` | Probe whether it is up |

## The agents and skills

| Primitive | Role |
| --- | --- |
| [`plan-otel-instrumentation`](agents/plan-otel-instrumentation.agent.md) (agent) | Investigate a codebase and hand back every input for a spec-driven plan to implement OpenTelemetry: stack inventory, per-service approach sourced from the official docs, open decisions, verification protocol |
| [`observe-local-run`](agents/observe-local-run.agent.md) (agent) | Observe a running service (metrics, traces, logs, profiles via the [gcx](https://github.com/grafana/gcx) skills) and hand back every input for a spec-driven plan of fixes and improvements |
| [`otel-language-guides`](skills/otel-language-guides/SKILL.md) (skill) | Curated map of the official OpenTelemetry docs for all supported languages — pick the language, follow the linked sections (traces, metrics, logs, libraries, exporters, SDK config) |

The loop: **investigate** (agents) → **spec & implement** (the main
agent's spec-driven workflow) → **observe again** — telemetry on both ends.

## Install

```bash
apm install using-system/oddyssey
```

Or wire the server into any `mcpServers` config:

```json
{
  "mcpServers": {
    "oddyssey": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/using-system/oddyssey#subdirectory=src/mcp-server",
        "oddyssey-mcp"
      ]
    }
  }
}
```

From a clone, run it from the working tree instead:
`uv run --project src/mcp-server oddyssey-mcp`.

## Development

```bash
uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server
```

The project under `src/` is a self-contained uv project (own
`pyproject.toml`); `tests/` mirrors `src/`.

## License

[MIT](LICENSE)
