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
| **#3** | `z-ai/glm-5.3-flashx` | opencode | 1.13.0 | 11 / 13 | 4 / 4 / 3 | 17m09s | $0.33 | $0.030 |
| **#4** | `openai/gpt-5.6-luna` | copilot | 1.13.0 | 7 / 8 | 3 / 2 / 2 | **6m29s** | **$0.11** | **$0.016** |
| **#5** | `google/gemini-3.7-flash` | opencode | 1.13.0 | 8 / 9 | 4 / 3 / 1 | 10m17s | $1.08 | $0.135 |
| **#6** | `openai/gpt-5.6-terra` | copilot | 1.13.0 | 7 / 8 | 2 / 3 / 2 | 5m58s | $0.88 | $0.126 |
| **#7** | `openai/gpt-5.6-sol` | copilot | 1.13.0 | 12 / 13 | 8 / 4 / 0 | 9m32s | $1.41 | $0.117 |
| **#8** | `google/gemini-3.8-flash` | opencode | 1.13.0 | **12 / 12** | 6 / 4 / 2 | 20m39s | $2.29 | $0.191 |
| **#9** | `anthropic/claude-opus-5` | claude | 1.13.0 | **17 / 17** | 8 / 6 / 3 | 19m31s | $6.15 | $0.362 |
| **#10** | `anthropic/claude-fable-5.1` | claude | 1.12.0 | **17 / 17** | 10 / 5 / 2 | 17m08s | $7.55 | $0.444 |
| **#11** | `z-ai/glm-5.3-flash` | opencode | 1.13.0 | 7 / 8 | 3 / 4 / 0 | 32m15s | $0.10 | $0.014 |
| **#12** | `qwen/qwen3.8-27b` | opencode | 1.12.0 | 14 / 16 | 10 / 3 / 3 | 43m52s | $2.09 | $0.150 |
| **#13** | `qwen/qwen3.8-max-0902` | opencode | 1.13.0 | 15 / 16 | 8 / 4 / 3 | 30m25s | $1.50 | $0.100 |
| **#14** | `anthropic/claude-sonnet-5` | claude | 1.13.0 | **6 / 6** | 2 / 3 / 1 | 13m55s | $3.37 | $0.561 |

<details>
<summary>Run detail — phases, turns, tokens</summary>

| Model | CLI | oddyssey | Preflight | Drive | Observation | Turns | Median turn | Input | Output | Cache | Signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `z-ai/glm-5.3` | opencode | 1.13.0 | 3m17s | 2m02s | 14m25s | 44 | 9.4s | 4.4M | 121k | 4.0M | 4/4 |
| `deepseek/deepseek-v4.1-flash` | opencode | 1.13.0 | 5m59s | 2m02s | 21m04s | 73 | 11.9s | 8.0M | 94k | 7.4M | 4/4 |
| `z-ai/glm-5.3-flashx` | opencode | 1.13.0 | 3m10s | 2m01s | 11m58s | 32 | 13.3s | 2.3M | 68k | 2.1M | 4/4 |
| `openai/gpt-5.6-luna` | copilot | 1.13.0 | 1m02s | 2m01s | 3m26s | 38 | 2.8s | 2.9M | 17k | 2.9M | 4/4 |
| `google/gemini-3.7-flash` | opencode | 1.13.0 | 2m24s | 2m02s | 5m51s | 90 | 4.3s | 6.5M | 32k | 5.8M | 4/4 |
| `openai/gpt-5.6-terra` | copilot | 1.13.0 | 0m36s | 2m01s | 3m21s | 26 | 3.2s | 2.4M | 13k | 2.4M | 4/4 |
| `openai/gpt-5.6-sol` | copilot | 1.13.0 | 1m21s | 2m00s | 6m11s | 48 | 4.2s | 3.7M | 28k | 3.5M | 4/4 |
| `google/gemini-3.8-flash` | opencode | 1.13.0 | 9m58s | 2m03s | 8m38s | 148 | 4.4s | 12.8M | 59k | 11.1M | 4/4 |
| `anthropic/claude-opus-5` | claude | 1.13.0 | 2m47s | 2m02s | 14m42s | 53 | 6.6s | 5.8M | 62k | 5.8M | 4/4 |
| `anthropic/claude-fable-5.1` | claude | 1.12.0 | 2m52s | 2m02s | 12m14s | 36 | 3.6s | 3.6M | 60k | 3.6M | 4/4 |
| `z-ai/glm-5.3-flash` | opencode | 1.13.0 | 6m42s | 2m03s | 23m30s | 34 | 22.3s | 2.3M | 74k | 1.8M | 4/4 |
| `qwen/qwen3.8-27b` | opencode | 1.12.0 | 10m51s | 2m01s | 31m00s | 80 | 24.8s | 11.5M | 121k | 10.7M | 4/4 |
| `qwen/qwen3.8-max-0902` | opencode | 1.13.0 | 4m04s | 2m01s | 24m20s | 34 | 22.5s | 2.8M | 67k | 2.5M | 4/4 |
| `anthropic/claude-sonnet-5` | claude | 1.13.0 | 2m36s | 2m02s | 9m17s | 84 | 2.0s | 10.6M | 52k | 10.6M | 4/4 |

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
