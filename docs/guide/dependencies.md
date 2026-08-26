# Component dependency map

Who invokes what across the APM package's three layers - prompts,
agents, skills - plus the MCP server tools and the report stores.
Every edge below matches an actual invocation or routing statement in
the `.apm/` sources; the diagram carries the structure, the paragraphs
carry the intent.

## Legend

- **Layers**: prompts (user entry points) - agents (dispatched
  missions) - skills (reusable contracts) - MCP tools (the oddyssey
  server piloting the local stack and the global configuration) -
  stores (the committed `.odd/` report directories).
- **Edges**: solid `-->` = dispatch or direct invocation; dashed
  `-.->` = routing or contract reference (one component hands over to
  or follows another's rules); dotted with label = recommendation
  (one component points the user at another).

```mermaid
flowchart LR
  subgraph Prompts
    instrument["/odd-instrument"]
    observe["/odd-observe"]
    verify["/odd-verify"]
    status["/odd-status"]
    config["/odd-config"]
  end

  subgraph Agents
    expert[otel-instrumentation-expert]
    runner[observe-run]
  end

  subgraph Skills
    cbc[check-backend-configuration]
    ubc[update-backend-configuration]
    sls[setup-local-stack]
    ocg[observability-cli-guides]
    og[otel-guides]
    rs[run-scenario]
    corr[create-observe-run-report]
    coir[create-otel-instrumentation-report]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
    cfgset[odd_config_set]
    stack[odd_stack_status / up / reset]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
    insdir[otel-instrumentation-reports/]
  end

  instrument --> expert
  observe --> runner
  observe --> cbc
  observe --> cfgget
  observe --> cfgset
  verify --> runner
  verify --> cbc
  verify --> cfgget
  verify -.-> corr
  verify --> obsdir
  verify --> insdir
  status --> obsdir
  status --> insdir
  config --> cbc
  config -.-> ubc

  expert --> og
  expert --> coir
  expert --> cfgget
  expert -. recommends .-> runner

  runner --> ocg
  runner --> sls
  runner --> rs
  runner --> corr
  runner --> cfgget
  runner --> stack
  runner -. recommends .-> expert

  cbc -.-> sls
  cbc -.-> ocg
  cbc --> cfgget
  ubc --> ocg
  ubc --> cfgset
  ubc -.-> cbc
  ocg -.-> sls
  sls --> cfgget
  rs -.-> stack

  corr --> obsdir
  coir --> insdir

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class instrument,observe,verify,status,config prompt
  class expert,runner agent
  class cbc,ubc,sls,ocg,og,rs,corr,coir skill
  class cfgget,cfgset,stack mcp
  class obsdir,insdir store
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
