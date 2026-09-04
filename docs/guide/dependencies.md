# Component dependency map

Who invokes what across the package's three layers - prompts, agents,
skills - plus the MCP server tools and the report stores. Every edge
matches an actual invocation in the `.apm/` sources; the per-layer
tables at the end are the component catalog. One diagram per prompt,
limited to that prompt's reachable subgraph; a component from another
prompt's path appears as a **boundary node**, expanded in its own
diagram.

## Legend

- **Layers**: prompts (user entry points) - agents (dispatched
  missions) - skills (reusable contracts) - MCP tools (the oddyssey
  server piloting the local stack and the global configuration) -
  stores (the committed `.odd/` report directories, plus the findings
  decision ledger `.odd/decisions.md` and the benchmark sources under
  `.odd/benchmarks/`).
- **Edges**: solid `-->` = dispatch or direct invocation; dashed
  `-.->` = routing or contract reference (one component hands over to
  or follows another's rules); dotted with label = recommendation or
  hand-off (one component points the user, or the next step, at
  another).

## /odd-instrument-otel

Dispatches `otel-instrumentation-expert`, which maps services to the
official docs, takes the protocol's queries from the export stack's
`observability-cli-guides` reference (validating them locally through
`setup-local-stack`'s gcx context), persists through
`odd-memory`'s `otel-instrumentation-report` reference, and closes
with that reference's `## Show` synthesis.
`observe-run` is a boundary node: the report hands it the confirmation
of landed signals.

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
    ocg[observability-cli-guides]
    sls[setup-local-stack]
    mem[odd-memory]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
  end

  subgraph Stores[".odd/ stores"]
    insdir[otel-instrumentation-reports/]
  end

  instrument --> expert
  instrument --> mem
  expert --> og
  expert --> ocg
  expert -.-> sls
  expert --> mem
  expert --> cfgget
  expert -. hands off .-> runner
  ocg -.-> sls
  mem --> insdir


  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class instrument prompt
  class expert,runner agent
  class og,ocg,sls,mem skill
  class cfgget mcp
  class insdir store
```

## /odd-instrument-bench

Asks the user what only a human decides, ensures `k6` is present per
`k6-guides`, dispatches `k6-benchmark-expert`, which persists through
`odd-memory`'s `benchmark` reference, and closes with that reference's
synthesis.

```mermaid
flowchart LR
  subgraph Prompts
    bench["/odd-instrument-bench"]
  end

  subgraph Agents
    k6x[k6-benchmark-expert]
  end

  subgraph Skills
    kg[k6-guides]
    mem[odd-memory]
  end

  subgraph Stores[".odd/ stores"]
    benchdir[benchmarks/]
    obsdir[observe-run-reports/]
  end

  bench --> k6x
  bench --> kg
  bench --> mem

  k6x --> kg
  k6x --> mem
  k6x --> obsdir

  mem --> benchdir


  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef store fill:#f3e8fd,stroke:#a142f4
  class bench prompt
  class k6x agent
  class kg,mem skill
  class benchdir,obsdir store
```

## /odd-observe

Preflights in the main conversation - the stack through
`odd_config_get`/`odd_config_set`, the CLI through
`backend-configuration`'s `## Check`, `k6` through `k6-guides` when a
benchmark is named - then dispatches `observe-run` and closes with
the `observe-run-report` reference's `## Show` synthesis
(`odd-memory`). `otel-instrumentation-expert`
is a boundary node, recommended when a service emits no telemetry.

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
    bc[backend-configuration]
    ocg[observability-cli-guides]
    sls[setup-local-stack]
    rs[run-scenario]
    kg[k6-guides]
    mem[odd-memory]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
    cfgset[odd_config_set]
    stack[odd_stack_status / up / reset]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
    benchdir[benchmarks/]
  end

  observe --> runner
  observe --> bc
  observe --> mem
  observe --> cfgget
  observe --> cfgset
  observe --> kg
  observe --> ocg
  observe --> benchdir
  mem --> obsdir

  runner --> ocg
  runner --> sls
  runner --> rs
  runner --> mem
  runner --> cfgget
  runner --> stack
  runner -. recommends .-> expert

  bc -.-> sls
  bc --> ocg
  bc --> cfgget
  ocg -.-> sls
  sls --> cfgget
  sls --> stack
  rs -.-> stack
  rs -.-> sls
  rs --> kg
  rs --> benchdir



  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class observe prompt
  class runner,expert agent
  class bc,ocg,sls,rs,kg,mem skill
  class cfgget,cfgset,stack mcp
  class obsdir,benchdir store
```

## /odd-verify

Resolves the baseline across both `.odd/` stores, preflights against
the report's `stack` (never `odd_config_set` here), follows
the `observe-run-report` reference's verification rules
(`odd-memory`), ensures `k6` when a
drive replay carries a benchmark, dispatches `observe-run`, and closes
with the `observe-run-report` reference's `## Show` synthesis
(`odd-memory`). `otel-instrumentation-expert`
is the same boundary node as in `/odd-observe`.

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
    bc[backend-configuration]
    ocg[observability-cli-guides]
    sls[setup-local-stack]
    rs[run-scenario]
    kg[k6-guides]
    mem[odd-memory]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
    stack[odd_stack_status / up / reset]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
    insdir[otel-instrumentation-reports/]
    benchdir[benchmarks/]
  end

  verify --> runner
  verify --> bc
  verify --> mem
  verify --> cfgget
  verify --> kg
  verify --> obsdir
  verify --> insdir
  mem --> obsdir

  runner --> ocg
  runner --> sls
  runner --> rs
  runner --> mem
  runner --> cfgget
  runner --> stack
  runner -. recommends .-> expert

  bc -.-> sls
  bc --> ocg
  bc --> cfgget
  ocg -.-> sls
  sls --> cfgget
  sls --> stack
  rs -.-> stack
  rs -.-> sls
  rs --> kg
  rs --> benchdir



  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef agent fill:#fef7e0,stroke:#f9ab00
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  classDef store fill:#f3e8fd,stroke:#a142f4
  class verify prompt
  class runner,expert agent
  class bc,ocg,sls,rs,kg,mem skill
  class cfgget,stack mcp
  class obsdir,insdir,benchdir store
```

## /odd-status

Dispatches no agent: `get-status` renders the loop's state from both
stores, git, and the decisions ledger; a decision is recorded per
`odd-memory`'s `decisions` reference
only when the user asks for a decision, and the prompt re-renders
afterwards. The two recommended prompts are boundary nodes.

```mermaid
flowchart LR
  subgraph Prompts
    status["/odd-status"]
    instrument["/odd-instrument-otel"]
    observe["/odd-observe"]
  end

  subgraph Skills
    gs[get-status]
    mem[odd-memory]
  end

  subgraph Stores[".odd/ stores"]
    obsdir[observe-run-reports/]
    insdir[otel-instrumentation-reports/]
    dec[decisions.md]
  end

  status --> gs
  status -.-> mem

  gs --> obsdir
  gs --> insdir
  gs --> dec
  gs -. recommends .-> instrument
  gs -. recommends .-> observe

  mem --> obsdir
  mem --> dec

  gs --> mem

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef store fill:#f3e8fd,stroke:#a142f4
  class status,instrument,observe prompt
  class gs,mem skill
  class obsdir,insdir,dec store
```

## /odd-config

Displays through `backend-configuration`'s `## Check` and routes a
switch to its `## Switch`, which ends in `## Check` for the connection
proof; a missing CLI binary or a targeting value that fails to resolve
routes the other way, inside the same skill.

```mermaid
flowchart LR
  subgraph Prompts
    config["/odd-config"]
  end

  subgraph Skills
    bc[backend-configuration]
    ocg[observability-cli-guides]
    sls[setup-local-stack]
  end

  subgraph MCP["MCP tools"]
    cfgget[odd_config_get]
    cfgset[odd_config_set]
    stack[odd_stack_status / up / reset]
  end

  config --> bc
  config --> ocg

  bc --> ocg
  bc --> cfgset

  bc -.-> sls
  bc --> cfgget
  ocg -.-> sls
  sls --> cfgget
  sls --> stack

  classDef prompt fill:#e8f0fe,stroke:#4285f4
  classDef skill fill:#e6f4ea,stroke:#34a853
  classDef mcp fill:#fce8e6,stroke:#ea4335
  class config prompt
  class bc,ocg,sls skill
  class cfgget,cfgset,stack mcp
```

## Prompts

The user entry points. Each builds a mission from the arguments, runs
its preflight in the main conversation, dispatches (or routes to
skills), and closes with a show skill's synthesis of what was stored.

| Prompt | Role | Invokes |
| --- | --- | --- |
| [`/odd-instrument-otel`](../../.apm/prompts/odd-instrument-otel.prompt.md) | Entry point: point the `otel-instrumentation-expert` agent at a codebase | `otel-instrumentation-expert`; `odd-memory` (the `otel-instrumentation-report` reference's `## Show`) |
| [`/odd-instrument-bench`](../../.apm/prompts/odd-instrument-bench.prompt.md) | Entry point: ask what only a human decides, ensure `k6`, then point the `k6-benchmark-expert` agent at a service | `k6-benchmark-expert`; `k6-guides` (`authoring-inputs.md`, `install.md`); `odd-memory` (the `benchmark` reference: its `## Show`, and its recall when new-versus-update is ambiguous) |
| [`/odd-observe`](../../.apm/prompts/odd-observe.prompt.md) | Entry point: resolve the stack, prove the CLI connected, resolve the depth, build the mission and invoke the `observe-run` agent | `observe-run`; `backend-configuration` (`## Check`); `observability-cli-guides` (`builtin-stacks.md`); `k6-guides` (`install.md`); `odd-memory` (the `observe-run-report` reference's `## Show`); `odd_config_get`, `odd_config_set`; reads `.odd/benchmarks/` |
| [`/odd-verify`](../../.apm/prompts/odd-verify.prompt.md) | Entry point: replay a stored report's protocol through the `observe-run` agent and rule on everything it recorded; preflights against the report's stack and asks before a remote drive replay | `observe-run`; `backend-configuration` (`## Check`); `k6-guides` (`install.md`); `odd-memory` (the `observe-run-report` reference: its `## Show`, and its verification rules); `odd_config_get`; reads `.odd/observe-run-reports/`, `.odd/otel-instrumentation-reports/` |
| [`/odd-status`](../../.apm/prompts/odd-status.prompt.md) | Where is the loop? Rendered from the `.odd/` history and git alone; records decisions on findings. Dispatches no agent | `get-status`; `odd-memory` (the `decisions` reference) when, and only when, the user asks for a decision on a finding, then re-renders |
| [`/odd-config`](../../.apm/prompts/odd-config.prompt.md) | Show the configured backend - stack, targeted instance, connection proof - and guide a backend switch | `backend-configuration` (`## Check` to display, `## Switch` when the user picks a backend); `observability-cli-guides` |

## Agents

The dispatched missions. They investigate and report, never modify
the code, and persist through the create skills that own the stores.

| Agent | Role | Invokes |
| --- | --- | --- |
| [`otel-instrumentation-expert`](../../.apm/agents/otel-instrumentation-expert.agent.md) | Investigate a codebase and hand back every input for a spec-driven plan to implement OpenTelemetry | `otel-guides`; `observability-cli-guides` (the export stack's query surface, for the protocol's queries); routes to `setup-local-stack` to validate a query on the local stack; `odd-memory` (the `otel-instrumentation-report` reference); `odd_config_get`; hands the confirmation of landed signals off to `observe-run` |
| [`observe-run`](../../.apm/agents/observe-run.agent.md) | Observe a running service through its telemetry, on the local stack or a remote backend, and hand back every input for a plan of fixes | `observability-cli-guides`; `setup-local-stack`; `run-scenario` (ad-hoc requests, or a stored benchmark run unmodified); `odd-memory` (the `observe-run-report` reference); `odd_config_get`; `odd_stack_status` / `odd_stack_up` / `odd_stack_reset`; recommends `otel-instrumentation-expert` when a named service emits no telemetry at all |
| [`k6-benchmark-expert`](../../.apm/agents/k6-benchmark-expert.agent.md) | Investigate a service and author its k6 benchmark as reviewed code, validated but never run as a benchmark | `k6-guides` (`scripting.md`, `running-tests.md`); `odd-memory` (the `benchmark` reference); reads `.odd/observe-run-reports/` for the service's hot operations |

## Skills

The reusable contracts. A skill invokes another only where an edge is
drawn: the guides and the show skills invoke nothing, the create
skills own their store, and the two configuration skills route to
each other.

| Skill | Role | Invokes |
| --- | --- | --- |
| [`otel-guides`](../../.apm/skills/otel-guides/SKILL.md) | Curated map of the official OpenTelemetry docs: every supported language plus the cross-language guides (SDK configuration, semantic conventions, Collector deployment) | Nothing |
| [`k6-guides`](../../.apm/skills/k6-guides/SKILL.md) | Curated map of the official k6 docs: install, running a script, scripting (checks, thresholds, scenarios), test types, protocols - and which of a benchmark's inputs a human must decide rather than an agent | Nothing |
| [`odd-memory`](../../.apm/skills/odd-memory/SKILL.md) | The `.odd/` memory: the contract every kind shares, and one reference per kind - observation reports, instrumentation reports, the finding-decision ledger, benchmarks - saying how to persist, recall and show it; owns the four stores | Nothing - read by the three agents at persist and recall time, by the prompts at show time, by `get-status`; never invoked on its own |
| [`observability-cli-guides`](../../.apm/skills/observability-cli-guides/SKILL.md) | One reference per stack - query surface, configuration display, what to persist - plus the built-in stack list: the local stack, Grafana (gcx), Datadog (Pup), Dynatrace (dtctl), Azure Monitor (az), CloudWatch (aws), Splunk | Routes the local-stack case to `setup-local-stack` |
| [`setup-local-stack`](../../.apm/skills/setup-local-stack/SKILL.md) | Configure gcx against the local stack without touching the user's contexts, with the datasource UIDs and the push-model caveats | `odd_config_get`; `odd_stack_status` / `odd_stack_up` / `odd_stack_reset` |
| [`backend-configuration`](../../.apm/skills/backend-configuration/SKILL.md) | The configured backend, in two sections: `## Check` displays the configured stack's CLI context, proves it connected, guides the setup and hands the preflight over to the mission; `## Switch` owns the change - CLI presence with a guided install offer, the switch and the per-stack `stack_config` values persisted, then `## Check` for the proof | `observability-cli-guides` (`builtin-stacks.md`, the stack's four preflight sections); `odd_config_get`, `odd_config_set`; routes to `setup-local-stack` for the local stack |
| [`run-scenario`](../../.apm/skills/run-scenario/SKILL.md) | Drive a reproducible request scenario - ad-hoc requests or a stored benchmark - and record it verbatim for the replay | `k6-guides` (`running-tests.md`, `install.md`); reads `.odd/benchmarks/<name>/` (never writes there); orders the clean-base sequence around `odd_stack_reset` and follows `setup-local-stack` |
| [`get-status`](../../.apm/skills/get-status/SKILL.md) | Render the state of the ODD loop from the committed `.odd/` history and git alone, read-only | `odd-memory`; reads `.odd/observe-run-reports/`, `.odd/otel-instrumentation-reports/`, and `.odd/decisions.md` (under `odd-memory`'s `decisions` reference); recommends `/odd-instrument-otel` or `/odd-observe` |

## Hooks

| Hook | Role | Invoked by |
| --- | --- | --- |
| [`odd-guards`](../../.apm/hooks/odd-guards.json), branch guard | Refuse a `git commit` on the default branch, or a `git push` to it, before it runs - the persistence skills' rule made deterministic | The host's pre-tool event, on every target with hooks; never a prompt, agent, or skill |
| [`odd-guards`](../../.apm/hooks/odd-guards.json), `.odd/` scan | After a tool wrote a file under `.odd/`, flag every line carrying a GUID, a home-directory path, or a value of the global configuration's `stack_config` - AGENTS.md's no-secrets rule, checked before the report is persisted; the write already happened, the message reaches the agent | The host's post-tool event, on every target with hooks |

A hook deploys with the package; a host can be told not to run it
(`apm deny using-system/oddyssey` before installing, or the host's own
hooks setting).

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
  P[6 prompts] --> A[3 agents]
  P --> S[15 skills]
  A --> S
  P --> M[MCP tools]
  A --> M
  S --> M
  P --> D[".odd/ stores"]
  A --> D
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
