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
  stores (the committed `.odd/` report directories, plus the findings
  decision ledger `.odd/decisions.md`).
- **Edges**: solid `-->` = dispatch or direct invocation; dashed
  `-.->` = routing or contract reference (one component hands over to
  or follows another's rules); dotted with label = recommendation or
  hand-off (one component points the user, or the next step, at
  another).

## /odd-instrument-otel

A dispatcher to `otel-instrumentation-expert`, which maps
services to the official docs (`otel-guides`), reads effective ports
from `odd_config_get`, and persists through
`create-otel-instrumentation-report`. The prompt closes the mission
with `show-otel-instrumentation-report`, rendering a synthesis of the
stored report as the final answer. `observe-run` is a boundary node
here - the report hands the confirmation of landed signals to it, and
its own path is the `/odd-observe` diagram.

```mermaid
flowchart LR
  subgraph Prompts
    instrument["/odd-instrument-otel"]
  end

  subgraph Agents
    expert[otel-instrumentation-expert]
    runner[observe-run]
  end

  subgraph Skills
    og[otel-guides]
    coir[create-otel-instrumentation-report]
    soir[show-otel-instrumentation-report]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
  end

  subgraph Stores[".odd/ stores"]
    insdir[otel-instrumentation-reports/]
  end

  instrument --> expert
  instrument --> soir
  expert --> og
  expert --> coir
  expert --> cfgget
  expert -. hands off .-> runner
  coir --> insdir
  soir --> insdir

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class instrument prompt
  class expert,runner agent
  class og,coir,soir skill
  class cfgget mcp
  class insdir store
```

## /odd-observe

The preflight runs in the main conversation first - resolve the stack
(`odd_config_get`, persisting a switch with `odd_config_set`) and
prove the CLI connected (`check-backend-configuration`) - then the
mission dispatches to `observe-run`, and the prompt closes it with
`show-observe-run-report`, rendering a synthesis of the stored report
as the final answer. `otel-instrumentation-expert` is
a boundary node - recommended when a named service emits no telemetry
at all; its path is the `/odd-instrument-otel` diagram.

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
    sorr[show-observe-run-report]
    ubc[update-backend-configuration]
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
  observe --> sorr
  observe --> cfgget
  observe --> cfgset
  sorr --> obsdir

  runner --> ocg
  runner --> sls
  runner --> rs
  runner --> corr
  runner --> cfgget
  runner --> stack
  runner -. recommends .-> expert

  cbc -.-> sls
  cbc -.-> ubc
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
  class cbc,ocg,sls,rs,corr,sorr,ubc skill
  class cfgget,cfgset,stack mcp
  class obsdir store
```

## /odd-verify

Resolves the baseline report across both `.odd/` stores, preflights
against the report's `stack` (never silently retargeting the
configured one - so no `odd_config_set` in this subgraph), mandates
`create-observe-run-report`'s verification rules for the report its
agent will persist, dispatches to `observe-run`, and closes the
mission with `show-observe-run-report`'s synthesis of the stored
report - verdict first.
`otel-instrumentation-expert` is the same boundary node as in
`/odd-observe` - its path is the `/odd-instrument-otel` diagram.

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
    sorr[show-observe-run-report]
    ubc[update-backend-configuration]
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
  verify --> sorr
  verify --> cfgget
  verify -.-> corr
  verify --> obsdir
  verify --> insdir
  sorr --> obsdir

  runner --> ocg
  runner --> sls
  runner --> rs
  runner --> corr
  runner --> cfgget
  runner --> stack
  runner -. recommends .-> expert

  cbc -.-> sls
  cbc -.-> ubc
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
  class cbc,ocg,sls,rs,corr,sorr,ubc skill
  class cfgget,stack mcp
  class obsdir,insdir store
```

## /odd-status

Dispatches no agent: a thin router over two skills, both running in
the main conversation. `get-status` renders - it reads both stores,
git, and the decisions ledger, read-only, and recommends the next loop
step. `record-finding-decision` runs only when the user asks for a
decision on a finding (in the arguments or as a follow-up): it resolves
the reference against the observation reports, appends a row to
`.odd/decisions.md`, commits that file alone, and the prompt then
re-renders through `get-status`. Neither skill invokes another
component; `get-status` reads the ledger through the format contract
`record-finding-decision` owns, but never calls it. The two
recommended prompts are boundary nodes - their paths are their own
diagrams.

```mermaid
flowchart LR
  subgraph Prompts
    status["/odd-status"]
    instrument["/odd-instrument-otel"]
    observe["/odd-observe"]
  end

  subgraph Skills
    gs[get-status]
    rfd[record-finding-decision]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
    insdir[otel-instrumentation-reports/]
    dec[decisions.md]
  end

  status --> gs
  status -.-> rfd

  gs --> obsdir
  gs --> insdir
  gs --> dec
  gs -. recommends .-> instrument
  gs -. recommends .-> observe

  rfd --> obsdir
  rfd --> dec

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef store fill:#f3e8fd,stroke:#a142f4
  class status,instrument,observe prompt
  class gs,rfd skill
  class obsdir,insdir,dec store
```

## /odd-config

Composes two skills - display through
`check-backend-configuration`, and the backend switch routed to
`update-backend-configuration` when the user picks one, which verifies
by handing back to `check-backend-configuration`. The routing goes the
other way too: when the backend CLI's binary is absent, or — on the
backends whose reference defines a targeting proof — when a persisted
targeting value fails to resolve, `check-backend-configuration` routes
to `update-backend-configuration`: to its guided install offer in the
first case, to a correction of the stored value in the second.

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
  cbc -.-> ubc
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

`/odd-instrument-otel` and `/odd-observe` are dispatchers: they build
a mission block, hand it to their agent, and close the mission with
their show-report skill's synthesis of the stored report
(`show-otel-instrumentation-report` and `show-observe-run-report`
respectively; `/odd-verify` closes with the latter too, verdict
first). `/odd-observe`'s preflight
runs in the main conversation first - resolve the stack
(`odd_config_get`, persisting a switch with `odd_config_set`) and
prove the CLI connected (`check-backend-configuration`). `/odd-verify`
resolves the baseline report across both `.odd/` stores, preflights
against the report's `stack` (never silently retargeting the
configured one), and mandates `create-observe-run-report`'s
verification rules for the report its agent will persist.
`/odd-status` dispatches no agent: it is a thin router over two skills
running in the main conversation - `get-status` for the render, and
`record-finding-decision` when, and only when, the user asks for a
decision on a finding, followed by a re-render. `/odd-config` composes
two skills - display through `check-backend-configuration`, and the
backend switch routed to `update-backend-configuration` when the user
picks one.

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
`setup-local-stack`, remote backends to their
`observability-cli-guides` reference, a missing CLI binary to the
guided install offer of `update-backend-configuration`, and — where a
reference defines a targeting proof — a persisted targeting value that
does not resolve to the same skill for correction.
`update-backend-configuration`
owns the switch: CLI presence via the guides' `## CLI binary`
sections, persistence via `odd_config_set`, verification handed back
to `check-backend-configuration`. `observability-cli-guides` routes
the local-stack case to `setup-local-stack`, which reads the effective
ports from `odd_config_get`. `run-scenario` orders the clean-base
sequence around `odd_stack_reset`. The two create-report skills own
the stores: naming, frontmatter contracts, recall - everything else
goes through them rather than touching `.odd/` directly. The two
show-report skills (`show-observe-run-report`,
`show-otel-instrumentation-report`) read a stored report and render
its closing synthesis - display only: they follow the create skills'
file contracts, write nothing, and invoke no other component. `get-status` owns
the status surface - its sources (both stores, git, the decisions
ledger), the build order, the empty-filter answer, the degradation -
and invokes no other component: it only reads.
`record-finding-decision` owns `.odd/decisions.md` - the row format,
the resolution of a finding reference to `<report filename> / <finding
ID>`, and the commit of that file alone; it reads the observation
reports to resolve the reference, never edits one, and invokes no
other component either. `get-status` follows that ledger contract when
it reads the file, without calling the skill.

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
this view keeps only the cross-layer edges. The last block is not a
component layer but the **machine state** the MCP tools sit on - the
global configuration and the local stack container never appear in the
per-prompt diagrams because nothing invokes them directly: every
access goes through the tools.

```mermaid
flowchart LR
  P[5 prompts] --> A[2 agents]
  P --> S[12 skills]
  A --> S
  P --> M[MCP tools]
  A --> M
  S --> M
  P --> D[".odd/ stores"]
  S --> D
  M --> C["global configuration"]
  M --> K["local stack container"]

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  classDef state fill:#f1f3f4,stroke:#5f6368,stroke-dasharray: 4 3
  class P prompt
  class A agent
  class S skill
  class M mcp
  class D store
  class C,K state
```
