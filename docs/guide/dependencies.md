# Component dependency map

Who invokes what across the APM package's three layers - prompts,
agents, skills - plus the MCP server tools and the report stores.
Every edge below matches an actual invocation or routing statement in
the `.apm/` sources; the diagrams carry the structure, the paragraphs
carry the intent.

The map is split into **one diagram per prompt**, each limited to that
prompt's reachable subgraph. Shared plumbing (the preflight routing,
the report skills owning the stores) repeats where reachable - a
little repetition is the price of legibility. A component that belongs
to another prompt's path appears only as a **boundary node** (the
target of a hand-off or recommendation edge), without its own
dependencies - the diagram named in the prose expands it.

## Legend

- **Layers**: prompts (user entry points) - agents (dispatched
  missions) - skills (reusable contracts) - MCP tools (the oddyssey
  server piloting the local stack and the global configuration) -
  stores (the committed `.odd/` report directories).
- **Edges**: solid `-->` = dispatch or direct invocation; dashed
  `-.->` = routing or contract reference (one component hands over to
  or follows another's rules); dotted with label = recommendation or
  hand-off (one component points the user, or the next step, at
  another).

## /odd-instrument

A pure dispatcher to `otel-instrumentation-expert`, which maps
services to the official docs (`otel-guides`), reads effective ports
from `odd_config_get`, and persists through
`create-otel-instrumentation-report`. `observe-run` is a boundary node
here - the report hands the confirmation of landed signals to it, and
its own path is the `/odd-observe` diagram.

```mermaid
flowchart LR
  subgraph Prompts
    instrument["/odd-instrument"]
  end

  subgraph Agents
    expert[otel-instrumentation-expert]
    runner[observe-run]
  end

  subgraph Skills
    og[otel-guides]
    coir[create-otel-instrumentation-report]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
  end

  subgraph Stores[".odd/ stores"]
    insdir[otel-instrumentation-reports/]
  end

  instrument --> expert
  expert --> og
  expert --> coir
  expert --> cfgget
  expert -. hands off .-> runner
  coir --> insdir

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class instrument prompt
  class expert,runner agent
  class og,coir skill
  class cfgget mcp
  class insdir store
```

## /odd-observe

The preflight runs in the main conversation first - resolve the stack
(`odd_config_get`, persisting a switch with `odd_config_set`) and
prove the CLI connected (`check-backend-configuration`) - then the
mission dispatches to `observe-run`. `otel-instrumentation-expert` is
a boundary node - recommended when a named service emits no telemetry
at all; its path is the `/odd-instrument` diagram.

```mermaid
flowchart LR
  subgraph Prompts
    observe["/odd-observe"]
  end

  subgraph Agents
    runner[observe-run]
    expert[otel-instrumentation-expert]
  end

  subgraph Skills
    cbc[check-backend-configuration]
    ocg[observability-cli-guides]
    sls[setup-local-stack]
    rs[run-scenario]
    corr[create-observe-run-report]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
    cfgset[odd_config_set]
    stack[odd_stack_status / up / reset]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
  end

  observe --> runner
  observe --> cbc
  observe --> cfgget
  observe --> cfgset

  runner --> ocg
  runner --> sls
  runner --> rs
  runner --> corr
  runner --> cfgget
  runner --> stack
  runner -. recommends .-> expert

  cbc -.-> sls
  cbc --> ocg
  cbc --> cfgget
  cbc --> stack
  ocg -.-> sls
  sls --> cfgget
  sls --> stack
  rs -.-> stack
  rs -.-> sls

  corr --> obsdir

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class observe prompt
  class runner,expert agent
  class cbc,ocg,sls,rs,corr skill
  class cfgget,cfgset,stack mcp
  class obsdir store
```

## /odd-verify

Resolves the baseline report across both `.odd/` stores, preflights
against the report's `stack` (never silently retargeting the
configured one - so no `odd_config_set` in this subgraph), mandates
`create-observe-run-report`'s verification rules for the report its
agent will persist, and dispatches to `observe-run`.
`otel-instrumentation-expert` is the same boundary node as in
`/odd-observe` - its path is the `/odd-instrument` diagram.

```mermaid
flowchart LR
  subgraph Prompts
    verify["/odd-verify"]
  end

  subgraph Agents
    runner[observe-run]
    expert[otel-instrumentation-expert]
  end

  subgraph Skills
    cbc[check-backend-configuration]
    ocg[observability-cli-guides]
    sls[setup-local-stack]
    rs[run-scenario]
    corr[create-observe-run-report]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
    stack[odd_stack_status / up / reset]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
    insdir[otel-instrumentation-reports/]
  end

  verify --> runner
  verify --> cbc
  verify --> cfgget
  verify -.-> corr
  verify --> obsdir
  verify --> insdir

  runner --> ocg
  runner --> sls
  runner --> rs
  runner --> corr
  runner --> cfgget
  runner --> stack
  runner -. recommends .-> expert

  cbc -.-> sls
  cbc --> ocg
  cbc --> cfgget
  cbc --> stack
  ocg -.-> sls
  sls --> cfgget
  sls --> stack
  rs -.-> stack
  rs -.-> sls

  corr --> obsdir

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class verify prompt
  class runner,expert agent
  class cbc,ocg,sls,rs,corr skill
  class cfgget,stack mcp
  class obsdir,insdir store
```

## /odd-status

Dispatches nothing: it reads the stores and git in the main
conversation, read-only, and recommends the next loop step. The two
recommended prompts are boundary nodes - their paths are their own
diagrams.

```mermaid
flowchart LR
  subgraph Prompts
    status["/odd-status"]
    instrument["/odd-instrument"]
    observe["/odd-observe"]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
    insdir[otel-instrumentation-reports/]
  end

  status --> obsdir
  status --> insdir
  status -. recommends .-> instrument
  status -. recommends .-> observe

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef store fill:#f3e8fd,stroke:#a142f4
  class status,instrument,observe prompt
  class obsdir,insdir store
```

## /odd-config

Composes two skills - display through
`check-backend-configuration`, and the backend switch routed to
`update-backend-configuration` when the user picks one, which verifies
by handing back to `check-backend-configuration`.

```mermaid
flowchart LR
  subgraph Prompts
    config["/odd-config"]
  end

  subgraph Skills
    cbc[check-backend-configuration]
    ubc[update-backend-configuration]
    ocg[observability-cli-guides]
    sls[setup-local-stack]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
    cfgset[odd_config_set]
    stack[odd_stack_status / up / reset]
  end

  config --> cbc
  config -.-> ubc

  ubc --> ocg
  ubc --> cfgset
  ubc -.-> cbc

  cbc -.-> sls
  cbc --> ocg
  cbc --> cfgget
  cbc --> stack
  ocg -.-> sls
  sls --> cfgget
  sls --> stack

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  class config prompt
  class cbc,ubc,ocg,sls skill
  class cfgget,cfgset,stack mcp
```

## Prompts

`/odd-instrument` and `/odd-observe` are pure dispatchers: they build
a mission block and hand it to their agent. `/odd-observe`'s preflight
runs in the main conversation first - resolve the stack
(`odd_config_get`, persisting a switch with `odd_config_set`) and
prove the CLI connected (`check-backend-configuration`). `/odd-verify`
resolves the baseline report across both `.odd/` stores, preflights
against the report's `stack` (never silently retargeting the
configured one), and mandates `create-observe-run-report`'s
verification rules for the report its agent will persist.
`/odd-status` dispatches nothing: it reads the stores and git in the
main conversation, read-only. `/odd-config` composes two skills -
display through `check-backend-configuration`, and the backend switch
routed to `update-backend-configuration` when the user picks one.

## Agents

`otel-instrumentation-expert` maps each service to the official docs
through `otel-guides`, derives effective ports from `odd_config_get`,
and persists through `create-otel-instrumentation-report`; its report
hands the confirmation of landed signals to `observe-run`.
`observe-run` owns the observation method: backend commands come from
`observability-cli-guides`, the local stack is configured through
`setup-local-stack`, drive-mode traffic goes through `run-scenario`,
the stack is piloted with the `odd_stack_*` tools, and the report is
recalled and persisted through `create-observe-run-report`. When a
named service emits no telemetry at all, it recommends
`otel-instrumentation-expert`.

## Skills

`check-backend-configuration` is the routing hub of the preflight: it
resolves the configured stack (`odd_config_get`), routes `local` to
`setup-local-stack` and remote backends to their
`observability-cli-guides` reference. `update-backend-configuration`
owns the switch: CLI presence via the guides' `## CLI binary`
sections, persistence via `odd_config_set`, verification handed back
to `check-backend-configuration`. `observability-cli-guides` routes
the local-stack case to `setup-local-stack`, which reads the effective
ports from `odd_config_get`. `run-scenario` orders the clean-base
sequence around `odd_stack_reset`. The two report skills own the
stores: naming, frontmatter contracts, recall - everything else goes
through them rather than touching `.odd/` directly.

## MCP tools

`odd_config_get` / `odd_config_set` read and write the global
configuration (stack, local ports, per-stack `stack_config`);
`odd_stack_status` / `odd_stack_up` / `odd_stack_reset` pilot the
local otel-lgtm container. They are the only components with machine
state - every prompt, agent, and skill above is a prose contract.

## Bird's-eye view

Layers only - the per-component edges live in the per-prompt diagrams
above, and so does the intra-layer routing (prompt-to-prompt
recommendations, the agents' mutual hand-off, skill-to-skill routing):
this view keeps only the cross-layer edges.

```mermaid
flowchart LR
  P[5 prompts] --> A[2 agents]
  P --> S[8 skills]
  A --> S
  P --> M[MCP tools]
  A --> M
  S --> M
  P --> D[".odd/ stores"]
  S --> D

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class P prompt
  class A agent
  class S skill
  class M mcp
  class D store
```
