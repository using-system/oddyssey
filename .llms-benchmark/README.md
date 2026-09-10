# Which LLM can run oddyssey?

A ranking, to pick the model you run the loop with.

Each model observes the same running stack through the same replayed
traffic, and its report is graded on evidence. One model on one CLI, one
run, one row. The protocol is fixed and the only variables are the model
and the CLI it is driven through.

## Results

One section per observation depth. **Full** queries all four signals;
**quick** queries metrics and traces only, so a quick row can reach
performance anomalies and little else, and is ranked among quick rows,
never against the full ones. Within a section, one row per model and
CLI, always its latest run.

### Full report

| Rank | Model | CLI | oddyssey | Confirmed / reported | Telemetry / Perf / Behavior | Total | Cost | $/confirmed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **#1** | `google/gemini-3.7-flash` | opencode | 1.11.5 | **10 / 10** | 3 / 6 / 1 | **8m08s** | $0.95 | $0.095 |
| **#2** | `google/gemini-3.8-flash` | opencode | 1.11.5 | **9 / 9** | 4 / 4 / 1 | 14m29s | $1.61 | $0.179 |
| **#3** | `anthropic/claude-opus-5` | claude | 1.11.5 | **22 / 22** | 14 / 3 / 5 | 19m51s | $5.54 | $0.252 |
| **#4** | `anthropic/claude-fable-5.1` | claude | 1.11.5 | **18 / 18** | 10 / 6 / 2 | 17m29s | $7.48 | $0.416 |
| **#5** | `z-ai/glm-5.3-flash` | opencode | 1.11.5 | 15 / 16 | 8 / 3 / 5 | 25m15s | **$0.14** | **$0.009** |
| **#6** | `qwen/qwen3.8-max-0902` | opencode | 1.11.5 | **22 / 22** | 15 / 3 / 4 | 52m30s | $2.15 | $0.098 |
| **#7** | `qwen/qwen3.8-27b` | opencode | 1.11.5 | 16 / 18 | 11 / 4 / 3 | 51m04s | $1.65 | $0.103 |
| **#8** | `z-ai/glm-5.3` | opencode | 1.11.5 | 15 / 17 | 10 / 4 / 3 | 52m28s | $2.56 | $0.171 |
| **#9** | `anthropic/claude-sonnet-5` | claude | 1.11.5 | **7 / 7** | 4 / 3 / 0 | 16m01s | $3.22 | $0.459 |
| **#10** | `anthropic/claude-sonnet-5` | opencode | 1.11.5 | **7 / 7** | 4 / 2 / 1 | 20m47s | $3.46 | $0.494 |
| **#11** | `anthropic/claude-opus-5` | opencode | 1.11.3 ⚠︎ | **17 / 17** | 11 / 3 / 3 | 27m36s | $10.35 | $0.609 |
| **#12** | `openai/gpt-6-astra` | opencode | 1.11.3 ⚠︎ | **15 / 15** | 8 / 3 / 4 | 23m27s | **$19.58** | $1.305 |
| **#13** | `anthropic/claude-haiku-4.5` | claude | 1.11.5 | **2 / 5** | 0 / 5 / 0 | 10m13s | $0.79 | $0.393 |
| **#14** | `anthropic/claude-haiku-4.5` | opencode | 1.11.5 | **0 / 2** | 0 / 2 / 0 | 8m13s | $0.58 | — |

<details>
<summary>Run detail — phases, turns, tokens</summary>

| Model | CLI | oddyssey | Preflight | Drive | Observation | Turns | Median turn | Input | Output | Cache | Signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `google/gemini-3.7-flash` | opencode | 1.11.5 | 1m12s | 2m01s | 4m55s | 81 | 3.4s | 6.8M | 30k | 6.4M | 4/4 |
| `google/gemini-3.8-flash` | opencode | 1.11.5 | 4m58s | 2m02s | 7m29s | 139 | 3.6s | 11.8M | 53k | 11.0M | 4/4 |
| `anthropic/claude-opus-5` | claude | 1.11.5 | 2m52s | 2m02s | 14m57s | 43 | 4.4s | 4.2M | 70k | 4.2M | 4/4 |
| `anthropic/claude-fable-5.1` | claude | 1.11.5 | 2m55s | 2m02s | 12m32s | 30 | 5.5s | 2.9M | 56k | 2.9M | 4/4 |
| `z-ai/glm-5.3-flash` | opencode | 1.11.5 | 4m44s | 2m02s | 18m29s | 59 | 13.0s | 5.7M | 114k | 5.3M | 4/4 |
| `qwen/qwen3.8-max-0902` | opencode | 1.11.5 | 11m35s | 2m02s | 38m53s | 38 | 24.6s | 3.8M | 112k | 3.4M | 4/4 |
| `qwen/qwen3.8-27b` | opencode | 1.11.5 | 7m30s | 2m02s | 41m32s | 75 | 35.4s | 11.3M | 123k | 10.4M | 4/4 |
| `z-ai/glm-5.3` | opencode | 1.11.5 | 14m24s | 2m01s | 36m03s | 44 | 13.0s | 4.7M | 173k | 4.2M | 4/4 |
| `anthropic/claude-sonnet-5` | claude | 1.11.5 | 3m50s | 2m02s | 10m09s | 86 | 3.7s | 10.4M | 54k | 10.4M | 4/4 |
| `anthropic/claude-sonnet-5` | opencode | 1.11.5 | 6m01s | 2m01s | 12m45s | 81 | 9.5s | 9.9M | 65k | 9.9M | 4/4 |
| `anthropic/claude-opus-5` | opencode | 1.11.3 ⚠︎ | 3m52s | 2m01s | 21m43s | 64 | 8.9s | 8.4M | 104k | 8.4M | 4/4 |
| `openai/gpt-6-astra` | opencode | 1.11.3 ⚠︎ | 3m08s | 2m02s | 18m17s | 103 | 4.5s | 11.4M | 54k | 11.4M | 4/4 |
| `anthropic/claude-haiku-4.5` | claude | 1.11.5 | 2m17s | 2m01s | 5m55s | 61 | 2.0s | 4.2M | 33k | 4.2M | 4/4 |
| `anthropic/claude-haiku-4.5` | opencode | 1.11.5 | 1m08s | 2m00s | 5m05s | 45 | 3.6s | 2.6M | 28k | 2.6M | 0/4 |

Token counts are rounded; the exact figures are in each run's pull
request. Input includes the cached share, so Input and Cache overlap by
design.

</details>

### Quick report

| Rank | Model | CLI | oddyssey | Confirmed / reported | Telemetry / Perf / Behavior | Total | Cost | $/confirmed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **#1** | `google/gemini-3.7-flash` | opencode | 1.11.5 | 5 / 6 | 1 / 3 / 2 | 8m11s | $0.86 | $0.172 |

<details>
<summary>Run detail — phases, turns, tokens</summary>

| Model | CLI | oddyssey | Preflight | Drive | Observation | Turns | Median turn | Input | Output | Cache | Signals |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `google/gemini-3.7-flash` | opencode | 1.11.5 | 2m17s | 2m02s | 3m52s | 81 | 3.2s | 4.9M | 24k | 4.3M | 4/4 |

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
its placement is provisional until it is re-run. What that is worth was
settled once: `qwen/qwen3.8-27b` scored 25 of 26 when it was allowed to
read the application before observing it, and **15 of 15** on the same
scenario once it was not. Ten of its findings came from the code, not
from the telemetry.

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

**CLI** is the coding-agent CLI the mission ran in — `opencode` or
`claude`; its version is in each run's pull request, since two runs of
one model under different CLI versions are not the same measurement. The
cost is the API list price under either: a subscription changes the
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
```

The CLI, the model id and the depth are the only arguments — `opencode`
for any model OpenRouter serves, `claude` for Anthropic's models through
Claude Code's headless mode; the model always written in the same
`vendor/name` form, so one model's rows line up; `full` or `quick`, the
observation depth, which picks the results section the row lands in.
The credentials are
prerequisites you set up once and the command never asks for: an
OpenRouter provider configured in opencode, or a Claude Code login and
the package installed at user scope for it, and an `OPENAI_API_KEY` in
`docker-compose/llms-benchmark/.env` for the demo agent's own model calls
(see `.env.example` next to it).

That command runs the whole protocol and comes back with a pull request
adding or replacing the row. What it does:

1. Brings the demo stack up (`docker-compose/llms-benchmark/`) against
   the local oddyssey observability stack, and waits for the three
   services to answer.
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

That second rate is a hard ceiling. Every one of its eight iterations is
a real, paid model call, on every run, for every model ever tested.

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
