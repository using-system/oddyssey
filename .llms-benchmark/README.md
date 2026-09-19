# Which LLM? Which CLI?

A ranking, to pick the model you run the loop with and the coding-agent
CLI you drive it through.

Each model observes the same running stack through the same replayed
traffic, and its report is graded on evidence. One model on one CLI, one
run, one row: the same model under two CLIs is two rows, ranked against
each other like any other pair. The protocol is fixed and the only
variables are the model and the CLI.

## Results

One row per model and CLI, always its latest run.

| Rank | Model | CLI | oddyssey | Confirmed / reported | Telemetry / Perf / Behavior | Total | Cost | $/confirmed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **#1** | `z-ai/glm-5.3` | opencode | 1.13.0 | 17 / 19 | 9 / 4 / 4 | 19m44s | $1.39 | $0.082 |
| **#2** | `deepseek/deepseek-v4.1-flash` | opencode | 1.13.0 | **16 / 16** | 10 / 3 / 3 | 29m05s | $0.16 | $0.010 |
| **#3** | `z-ai/glm-5.3-flashx` | opencode | 1.12.0 | 12 / 14 | 3 / 6 / 3 | 16m02s | $0.42 | $0.035 |
| **#4** | `openai/gpt-5.6-luna` | copilot | 1.12.0 | 6 / 7 | 3 / 3 / 1 | **7m02s** | **$0.10** | **$0.016** |
| **#5** | `google/gemini-3.7-flash` | opencode | 1.13.0 | 8 / 9 | 4 / 3 / 1 | 10m17s | $1.08 | $0.135 |
| **#6** | `openai/gpt-5.6-terra` | copilot | 1.12.0 | 14 / 15 | 11 / 3 / 1 | 14m50s | $2.47 | $0.176 |
| **#7** | `openai/gpt-5.6-sol` | copilot | 1.12.0 | 11 / 12 | 8 / 3 / 1 | 9m39s | $3.12 | $0.284 |
| **#8** | `google/gemini-3.8-flash` | opencode | 1.12.0 | **10 / 10** | 5 / 4 / 1 | 14m59s | $1.96 | $0.196 |
| **#9** | `anthropic/claude-opus-5` | claude | 1.12.0 | 18 / 19 | 12 / 6 / 1 | 21m55s | $6.33 | $0.352 |
| **#10** | `anthropic/claude-fable-5.1` | claude | 1.12.0 | **17 / 17** | 10 / 5 / 2 | 17m08s | $7.55 | $0.444 |
| **#11** | `z-ai/glm-5.3-flash` | opencode | 1.12.0 | 13 / 14 | 7 / 4 / 2 | 66m43s | $0.24 | $0.018 |
| **#12** | `qwen/qwen3.8-27b` | opencode | 1.12.0 | 14 / 16 | 10 / 3 / 3 | 43m52s | $2.09 | $0.150 |
| **#13** | `qwen/qwen3.8-max-0902` | opencode | 1.12.0 | **14 / 14** | 8 / 3 / 3 | 66m09s | $2.88 | $0.206 |
| **#14** | `anthropic/claude-sonnet-5` | claude | 1.12.0 | **5 / 5** | 2 / 2 / 1 | 12m20s | $2.55 | $0.511 |

<details>
<summary>Run detail — phases, turns, tokens</summary>

| Model | CLI | oddyssey | Preflight | Drive | Observation | Turns | Median turn | Input | Output | Cache | Signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `z-ai/glm-5.3` | opencode | 1.13.0 | 3m17s | 2m02s | 14m25s | 44 | 9.4s | 4.4M | 121k | 4.0M | 4/4 |
| `deepseek/deepseek-v4.1-flash` | opencode | 1.13.0 | 5m59s | 2m02s | 21m04s | 73 | 11.9s | 8.0M | 94k | 7.4M | 4/4 |
| `z-ai/glm-5.3-flashx` | opencode | 1.12.0 | 3m32s | 2m02s | 10m28s | 39 | 13.8s | 3.2M | 84k | 3.0M | 4/4 |
| `openai/gpt-5.6-luna` | copilot | 1.12.0 | 1m03s | 2m01s | 3m58s | 38 | 3.2s | 2.5M | 15k | 2.5M | 4/4 |
| `google/gemini-3.7-flash` | opencode | 1.13.0 | 2m24s | 2m02s | 5m51s | 90 | 4.3s | 6.5M | 32k | 5.8M | 4/4 |
| `openai/gpt-5.6-terra` | copilot | 1.12.0 | 1m39s | 2m00s | 11m11s | 64 | 3.9s | 6.5M | 54k | 6.5M | 4/4 |
| `openai/gpt-5.6-sol` | copilot | 1.12.0 | 1m38s | 2m00s | 6m01s | 53 | 4.6s | 3.9M | 22k | 3.8M | 4/4 |
| `google/gemini-3.8-flash` | opencode | 1.12.0 | 4m26s | 2m02s | 8m31s | 135 | 3.1s | 10.7M | 33k | 9.2M | 4/4 |
| `anthropic/claude-opus-5` | claude | 1.12.0 | 3m36s | 2m00s | 16m19s | 57 | 8.6s | 6.3M | 59k | 6.3M | 4/4 |
| `anthropic/claude-fable-5.1` | claude | 1.12.0 | 2m52s | 2m02s | 12m14s | 36 | 3.6s | 3.6M | 60k | 3.6M | 4/4 |
| `z-ai/glm-5.3-flash` | opencode | 1.12.0 | 11m45s | 2m00s | 52m58s | 46 | 48.1s | 4.0M | 115k | 2.5M | 4/4 |
| `qwen/qwen3.8-27b` | opencode | 1.12.0 | 10m51s | 2m01s | 31m00s | 80 | 24.8s | 11.5M | 121k | 10.7M | 4/4 |
| `qwen/qwen3.8-max-0902` | opencode | 1.12.0 | 9m00s | 2m02s | 55m07s | 47 | 51.1s | 5.5M | 153k | 5.2M | 4/4 |
| `anthropic/claude-sonnet-5` | claude | 1.12.0 | 2m11s | 2m00s | 8m09s | 67 | 2.1s | 7.5M | 43k | 7.5M | 4/4 |

Token counts are rounded; the exact figures are in each run's pull
request. Input includes the cached share, so Input and Cache overlap by
design.

</details>

**How to read the table**

- **Rank** weighs findings, cost and duration together. It is decided in each row's pull request, never computed: findings alone would rank a 67-minute run first, duration alone rewards whoever gives up soonest, cost alone rewards whoever barely looks. Adding a model re-sorts the whole table.
- **Confirmed / reported** is the grade: how many of the findings the model reported held up when checked against the telemetry it cited and the code it accused. 3 / 3 beats 4 / 12. Anomalies and telemetry gaps both count; a restatement counts once; a row bundling several defects counts once per defect.
- **Telemetry / Perf / Behavior** splits the reported findings by kind.
- **$/confirmed** is what one trustworthy finding costs.
- **CLI** is the coding-agent CLI the mission ran in; its version is in the row's pull request. Model and CLI identify a row; the oddyssey version does not, a new run replaces the row.
- **Signals**: how many of metrics, traces, logs and profiles the run queried. Not part of the grade, the context to read it in.
- **Preflight / Drive / Observation**: the drive is the scenario's fixed two minutes; a long preflight is a model that is lost, a long observation a model that is thorough. **Turns** and **median turn** separate groping (many short turns) from slow answering (few long ones).
- **Input / Output / Cache / Cost** come from the CLI's own session store after the run, whole session tree included. Input is the whole prompt processed, cached share included (cache is that share); output includes reasoning; cost is the provider's billed figure, cross-checked against its list prices.

A row measured under an earlier revision of the protocol is marked ⚠︎ and provisional until re-run. The table keeps no history: one row per model and CLI, its latest run.

## How a row is produced

```text
/launch-llms-benchmark opencode anthropic/claude-sonnet-5
/launch-llms-benchmark claude anthropic/claude-haiku-4.5
/launch-llms-benchmark copilot openai/gpt-5.6-luna
```

The CLI and the model id, in `vendor/name` form, are the only arguments. Prerequisites, set up once: an OpenRouter provider in opencode, a Claude Code login with the package installed at user scope, or a Copilot CLI login; and `OPENAI_API_KEY` in `docker-compose/llms-benchmark/.env` for the demo agent's own model calls (`.env.example` next to it).

The command cleans everything a run must not read (stored reports of the three services, leftovers, the local stack's data), recreates the demo stack, drives the model headless at medium effort through one `/odd-observe` mission naming the three services, the stored scenario and the local stack, grades the report finding by finding on evidence, and opens the pull request carrying the row and the rulings.

## The stack under observation

A small store assistant, three services, deliberately imperfect:

| Component | Service | What it is |
| --- | --- | --- |
| [`src/api`](src/api) | `llmbench-api` | FastAPI over a seeded SQLite catalog: products and orders |
| [`src/mcp`](src/mcp) | `llmbench-mcp` | An MCP server whose four tools call the API |
| [`src/agent`](src/agent) | `llmbench-agent` | A pydantic-ai agent calling those tools, and a model through OpenRouter |

All three export traces, metrics and logs over OTLP and profiles to Pyroscope; the agent's model calls carry the `gen_ai` conventions and their token usage.

## The scenario

[`benchmark/llmbench-store-load/`](benchmark/llmbench-store-load/), a k6 benchmark: two minutes, five virtual users walking a shopper's path through the catalog, straight at the API and through the MCP tools, plus one customer question to the agent every fifteen seconds. Each of those eight or nine questions is a real, paid model call.

## There is no answer key

The application's defects are written down nowhere in this repository, and the reports the runs produce are never committed: the graded model runs inside this repository, and anything the tree carries is one search away. The grade is not "how many of N did you find" but "of what you claimed, how much was true".

## Running the stack by hand

```bash
# once: cp ../docker-compose/llms-benchmark/.env.example \
#          ../docker-compose/llms-benchmark/.env  and fill OPENAI_API_KEY in
docker compose -f ../docker-compose/llms-benchmark/docker-compose.yml up -d --build

curl localhost:8010/health                      # the catalog API
curl localhost:8012/health                      # the agent
curl -s localhost:8012/ask -H 'content-type: application/json' \
  -d '{"question":"I need a quiet coffee grinder under 100 euros."}'
```

The local oddyssey stack must be up first (`odd_stack_up`): that is where the telemetry lands.
