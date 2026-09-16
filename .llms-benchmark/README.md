# Which LLM? Which CLI?

A ranking, to pick the model you run the loop with and the coding-agent
CLI you drive it through.

Each model observes the same running stack through the same replayed
traffic, and its report is graded on evidence. One model on one CLI, one
run, one row: the same model under two CLIs is two rows, ranked against
each other like any other pair. The protocol is fixed and the only
variables are the model and the CLI.

## Results

One section per observation depth. **Full** queries all four signals;
**quick** queries metrics and traces only, so a quick row can reach
performance anomalies and little else, and is ranked among quick rows,
never against the full ones. Within a section, one row per model and
CLI, always its latest run.

### Full report

| Rank | Model | CLI | oddyssey | Confirmed / reported | Telemetry / Perf / Behavior | Total | Cost | $/confirmed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **#1** | `z-ai/glm-5.3` | opencode | 1.12.0 | 18 / 19 | 12 / 4 / 3 | 12m23s | $1.98 | $0.110 |
| **#2** | `deepseek/deepseek-v4.1-flash` | opencode | 1.12.0 | **10 / 10** | 5 / 3 / 2 | 9m54s | $0.20 | $0.020 |
| **#3** | `openai/gpt-5.6-luna` | copilot | 1.12.0 | 6 / 7 | 3 / 3 / 1 | **7m02s** | **$0.10** | **$0.016** |
| **#4** | `google/gemini-3.7-flash` | opencode | 1.12.0 | **7 / 7** | 3 / 3 / 1 | 8m34s | $0.87 | $0.124 |
| **#5** | `openai/gpt-5.6-terra` | copilot | 1.12.0 | 14 / 15 | 11 / 3 / 1 | 14m50s | $2.47 | $0.176 |
| **#6** | `openai/gpt-5.6-sol` | copilot | 1.12.0 | 11 / 12 | 8 / 3 / 1 | 9m39s | $3.12 | $0.284 |
| **#7** | `google/gemini-3.8-flash` | opencode | 1.12.0 | **10 / 10** | 5 / 4 / 1 | 14m59s | $1.96 | $0.196 |
| **#8** | `anthropic/claude-opus-5` | claude | 1.12.0 | 18 / 19 | 12 / 6 / 1 | 21m55s | $6.33 | $0.352 |
| **#9** | `anthropic/claude-fable-5.1` | claude | 1.12.0 | **17 / 17** | 10 / 5 / 2 | 17m08s | $7.55 | $0.444 |
| **#10** | `z-ai/glm-5.3-flash` | opencode | 1.12.0 | 13 / 14 | 7 / 4 / 2 | 66m43s | $0.24 | $0.018 |
| **#11** | `qwen/qwen3.8-27b` | opencode | 1.12.0 | 14 / 16 | 10 / 3 / 3 | 43m52s | $2.09 | $0.150 |
| **#12** | `qwen/qwen3.8-max-0902` | opencode | 1.12.0 | **14 / 14** | 8 / 3 / 3 | 66m09s | $2.88 | $0.206 |
| **#13** | `anthropic/claude-sonnet-5` | claude | 1.12.0 | **5 / 5** | 2 / 2 / 1 | 12m20s | $2.55 | $0.511 |

<details>
<summary>Run detail — phases, turns, tokens</summary>

| Model | CLI | oddyssey | Preflight | Drive | Observation | Turns | Median turn | Input | Output | Cache | Signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `z-ai/glm-5.3` | opencode | 1.12.0 | 1m28s | 2m01s | 8m54s | 46 | 6.1s | 4.2M | 139k | 4.0M | 4/4 |
| `deepseek/deepseek-v4.1-flash` | opencode | 1.12.0 | 1m27s | 2m01s | 6m26s | 48 | 4.2s | 4.1M | 76k | 3.8M | 4/4 |
| `openai/gpt-5.6-luna` | copilot | 1.12.0 | 1m03s | 2m01s | 3m58s | 38 | 3.2s | 2.5M | 15k | 2.5M | 4/4 |
| `google/gemini-3.7-flash` | opencode | 1.12.0 | 2m11s | 2m02s | 4m21s | 71 | 4.3s | 4.2M | 31k | 3.5M | 4/4 |
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

### Quick report

| Rank | Model | CLI | oddyssey | Confirmed / reported | Telemetry / Perf / Behavior | Total | Cost | $/confirmed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **#1** | `deepseek/deepseek-v4.1-flash` | opencode | 1.12.0 | **8 / 8** | 4 / 3 / 1 | 8m50s | **$0.09** | **$0.011** |
| **#2** | `google/gemini-3.7-flash` | opencode | 1.12.0 | **5 / 5** | 1 / 4 / 0 | **8m24s** | $0.73 | $0.146 |
| **#3** | `anthropic/claude-opus-5` | claude | 1.12.0 | **15 / 15** | 10 / 4 / 1 | 14m30s | $5.19 | $0.346 |

<details>
<summary>Run detail — phases, turns, tokens</summary>

| Model | CLI | oddyssey | Preflight | Drive | Observation | Turns | Median turn | Input | Output | Cache | Signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `deepseek/deepseek-v4.1-flash` | opencode | 1.12.0 | 1m01s | 2m02s | 5m47s | 58 | 4.1s | 5.0M | 66k | 4.8M | 2/4 |
| `google/gemini-3.7-flash` | opencode | 1.12.0 | 3m00s | 2m01s | 3m23s | 85 | 3.2s | 4.1M | 21k | 3.6M | 4/4 |
| `anthropic/claude-opus-5` | claude | 1.12.0 | 2m20s | 2m00s | 10m10s | 51 | 2.8s | 4.8M | 50k | 4.8M | 4/4 |

</details>

**Rank** is the answer to the question in the title, in one column. It
is a judgement on **three axes together — findings, cost and duration** —
and it is decided rather than computed. **Cost and duration weigh
heavily**: a run nobody can afford, or nobody will wait for, is not a
usable answer however much it finds. The findings are what stop that from
collapsing into "cheapest wins" — a model that reports little, or reports
wrong, does not rise on being quick. Ranking on findings alone would
put a 67-minute run first; ranking on duration alone would reward
whichever model gives up soonest; ranking on cost alone would reward the
one that barely looks. Adding or updating a model re-sorts the whole
table, never just inserts a line, and the pull request that does it
argues the placement on those three axes.

A row measured under an earlier revision of the protocol is marked ⚠︎ and
its placement is provisional until it is re-run; a row the maintainer
stops maintaining is removed rather than left to age. What a revision is
worth was settled once: `qwen/qwen3.8-27b` scored 25 of 26 when it was
allowed to read the application before observing it, and **15 of 15** on
the same scenario once it was not. Ten of its findings came from the
code, not from the telemetry.

**How the reported count is arrived at.** A report splits its findings
between an anomalies section and a telemetry-gaps section, and the two
are not used the same way by every model: absent database spans are an
anomaly for two of these rows and a gap for another. So both sections
count, an entry that restates one already counted does not count twice,
and a row that bundles defects with different root causes and different
fixes counts once per defect. Without that, the denominator would measure
how a model organises a document.

**Confirmed / reported** is the grade. The denominator is how many
findings the model reported; the numerator is how many of them held up
when each was checked back against the telemetry it cited and the code it
accused. A model that reports three findings and gets three right scores
`3 / 3`; a model that reports twelve and gets four right scores `4 / 12`
— and the second is the worse report, however long it is. A finding the
report itself labels uncertain still counts when its numbers check out:
grading honesty down would only teach models to hide it.

**CLI** is the coding-agent CLI the mission ran in — `opencode`,
`claude` or `copilot`; its version is in each run's pull request, since
two runs of one model under different CLI versions are not the same
measurement. The cost is the model vendor's API list price under all
three: a subscription, a premium request or an AI credit changes the
bill, not the row.
Model and CLI together identify a row: the same model driven through two
CLIs is two rows. The oddyssey version is not part of that identity — a
new run of a model on the same CLI replaces its row, whatever version the
old row was measured under.

**Signals** is how many of the four — metrics, traces, logs, profiles —
the run actually queried. It is not part of the grade; it is what the
grade should be read against. A ratio earned across two signals and one
earned across four are not the same achievement, and the column is the
only thing that shows it.

**$/confirmed** is cost divided by confirmed findings — what one
trustworthy finding costs with this model. It is the column that actually
answers the question in the title, because cost and duration alone reward
whichever model gives up soonest.

**Telemetry / Perf / Behavior** breaks the reported findings into the
three kinds, in that order. A run can score well and still have looked at
one kind of problem only; the ratio does not say which.

**Preflight / Drive / Observation** split the total because the three are
not interchangeable. The drive is fixed by the scenario; the preflight is
how long the model takes to orient itself; the observation is the work.
A model whose total is dominated by observation is thorough, one whose
preflight runs long is lost. And **Turns** with **Median turn** separate
the two ways of being slow: many small turns means the model is groping,
few long ones means it is simply slow to answer.

### What the numbers mean

The four token and cost columns come from opencode's own session store,
read after the run exits — never from the model's account of itself,
which is written mid-run and cannot include its own last turns. They sum
the whole session tree: opencode dispatches the observation to a
subagent, and that subagent is usually the larger half of the bill.

- **Input** is the whole prompt processed — uncached tokens plus what was
  written to and read from cache. The provider's raw `input` counter is
  not used on its own: under prompt caching it holds only the residue
  that missed the cache entirely, which can be a few hundred tokens for a
  run that processed millions, and which differs so much between
  providers that two rows would not compare.
- **Cache** is the cached share of Input, so the two columns overlap by
  design. It is what explains a multi-million-token run costing a couple
  of dollars.
- **Output** includes reasoning tokens, which are billed as output.
- **Cost** is the provider's own billed figure, cross-checked against its
  published per-token prices before it is written down.

The table carries no history: one row per model and CLI, always its
latest run.

## How a row is produced

```text
/launch-llms-benchmark opencode anthropic/claude-sonnet-5 full
/launch-llms-benchmark claude anthropic/claude-haiku-4.5 full
/launch-llms-benchmark opencode google/gemini-3.7-flash quick
/launch-llms-benchmark copilot openai/gpt-5.6-luna full
```

The CLI, the model id and the depth are the only arguments — `opencode`
for any model OpenRouter serves, `claude` for Anthropic's models through
Claude Code's headless mode, `copilot` for the models GitHub Copilot
CLI serves; the model always written in the same
`vendor/name` form, so one model's rows line up; `full` or `quick`, the
observation depth, which picks the results section the row lands in.
The credentials are
prerequisites you set up once and the command never asks for: an
OpenRouter provider configured in opencode, a Claude Code login and
the package installed at user scope for it, or a Copilot CLI login, and
an `OPENAI_API_KEY` in
`docker-compose/llms-benchmark/.env` for the demo agent's own model calls
(see `.env.example` next to it).

That command runs the whole protocol and comes back with a pull request
adding or replacing the row. What it does:

1. Cleans what the run must not read — any observation report of the
   three services, the leftovers of a previous run, the local oddyssey
   stack's data (reset, so the window holds this run's traffic and
   nothing else) — then recreates the demo stack
   (`docker-compose/llms-benchmark/`) against the local stack and waits
   for the three services to answer.
2. Drives the model through the CLI you named — **opencode** on
   OpenRouter, or **claude** — at **medium** reasoning effort — headless,
   one session.
3. Gives it one mission — a single `/odd-observe` invocation naming the
   three services, the stored scenario `benchmark/llmbench-store-load/`,
   the **depth** you named and the **local** stack — states that the scenario's
   paid model calls are accepted, and asks for every kind of
   anomaly, not only the slow ones: performance, outright errors, wrong
   behavior, and telemetry that is missing or lying. Each of the four is
   named on purpose. The services, so the run never guesses its scope
   from what happens to be running. The scenario, so every row comes from
   the same replayed traffic. The stack, so no row is observed against a
   backend the others were not. The depth, because a shallower one
   queries metrics and traces only, and a run under it can reach
   performance anomalies and nothing else however good the model is.
4. Grades the report finding by finding, on evidence: the cited query is
   re-run, the accused line is opened. Both hold, or the finding does not
   count. Telemetry gaps are findings like any other.
5. Opens the run's issue, then the results PR from a clean `main`,
   carrying the row and the per-finding rulings — and nothing else.

The scenario itself is two minutes; the run around it is dominated by
the model's own observation.

## The stack under observation

A small store assistant, three services, deliberately imperfect:

| Component | Service | What it is |
| [`src/api`](src/api) | `llmbench-api` | FastAPI over a seeded SQLite catalog — products and orders |
| [`src/mcp`](src/mcp) | `llmbench-mcp` | An MCP server whose four tools call the API |
| [`src/agent`](src/agent) | `llmbench-agent` | A pydantic-ai agent calling those tools, and a model through OpenRouter |

All three export the four signals — traces, metrics and logs over OTLP,
profiles to Pyroscope — so every one of them is observable, and the
agent's model calls carry the `gen_ai` semantic conventions and their
token usage.

## The scenario

[`benchmark/llmbench-store-load/`](benchmark/llmbench-store-load), a k6
benchmark authored through `/odd-instrument-bench`. Two minutes, two
scenarios: five virtual users walking a shopper's conversation with the
catalog — browse, search, open a product, read the stats, order, read it
back — both straight at the API and through the four MCP tools; and one
customer question to the agent every fifteen seconds.

That second rate is a hard ceiling. Every one of its eight (sometimes
nine) iterations is a real, paid model call, on every run, for every
model ever tested.

## There is no answer key

The application's defects are written down nowhere in this repository.
Not in a comment, not in this README, not in the benchmark manifest, not
in an issue.

That is not an oversight, it is the design. The model being graded runs
as a coding agent **inside this repository**: anything the tree carries
is one search away from it, and a graded run that found the list would be
measuring reading comprehension, not observation. It is also why the
observation reports these runs produce are never committed — a stored
report names what it found, and the next model to be benchmarked could
read it.

So the grade is not "how many of the N did you find". It is "of what you
claimed, how much was true" — which is the question that matters about an
observation report anyway.

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

The local oddyssey stack must be up first (`odd_stack_up`) — that is
where the telemetry lands.
