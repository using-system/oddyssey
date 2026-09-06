# Which LLM can run oddyssey?

oddyssey does not need the largest model on the market. Observing a
running system is reading — telemetry first, then the code the telemetry
points at — and a model that reads carefully beats a model that reasons
brilliantly about the wrong query. This directory is where that claim
gets measured instead of asserted.

One model, one run, one row. The protocol is fixed, the traffic is
replayed identically, and the only variable is the model.

## Results

| Rank | Model | Preflight | Drive | Observation | Total | Turns | Median turn | Input | Output | Cache | Cost | $/confirmed | Signals | Kind | Confirmed / reported | oddyssey |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **#1** | `z-ai/glm-5.3` | 6m38s | 2m02s | 22m21s | **31m01s** | 49 | 19.7s | 6,986,615 | 188,492 | 6,445,056 | $2.49 | $0.113 | 4/4 | tel 13 · perf 5 · beh 4 | **22 / 23** | 1.11.3 |
| **#2** | `qwen/qwen3.8-27b` ⚠︎ | 14m27s | 2m02s | 51m08s | 1h07m37s | 67 | 44.8s | 13,897,126 | 220,744 | 12,769,392 | $2.22 | **$0.089** | 4/4 | tel 18 · perf 4 · beh 3 | **25 / 26** | 1.11.3 |

**Rank** is the answer to the question in the title, in one column. It
is a judgement on **three axes together — findings, cost and duration** —
and it is decided rather than computed. Ranking on findings alone would
put a 67-minute run first; ranking on duration alone would reward
whichever model gives up soonest; ranking on cost alone would reward the
one that barely looks. Adding or updating a model re-sorts the whole
table, never just inserts a line, and the pull request that does it
argues the placement on those three axes.

⚠︎ marks a row measured under an earlier revision of the protocol, whose
placement is therefore provisional until it is re-run.

**Confirmed / reported** is the grade. The denominator is how many
findings the model reported; the numerator is how many of them held up
when each was checked back against the telemetry it cited and the code it
accused. A model that reports three findings and gets three right scores
`3 / 3`; a model that reports twelve and gets four right scores `4 / 12`
— and the second is the worse report, however long it is. A finding the
report itself labels uncertain still counts when its numbers check out:
grading honesty down would only teach models to hide it.

**Signals** is how many of the four — metrics, traces, logs, profiles —
the run actually queried. It is not part of the grade; it is what the
grade should be read against. A ratio earned across two signals and one
earned across four are not the same achievement, and the column is the
only thing that shows it.

**$/confirmed** is cost divided by confirmed findings — what one
trustworthy finding costs with this model. It is the column that actually
answers the question in the title, because cost and duration alone reward
whichever model gives up soonest.

**Kind** breaks the reported findings into telemetry, performance and
behavior. A run can score well and still have looked at one kind of
problem only; the ratio does not say which.

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

The table carries no history: one row per model, always its latest run.

## How a row is produced

```text
/launch-llms-benchmark anthropic/claude-sonnet-5
```

The model id is the only argument. Two credentials are prerequisites you
set up once and the command never asks for: an OpenRouter provider
configured in opencode, and an `OPENAI_API_KEY` in
`docker-compose/llms-benchmark/.env` for the demo agent's own model calls
(see `.env.example` next to it).

That command runs the whole protocol and comes back with a pull request
adding or replacing the model's row. What it does:

1. Brings the demo stack up (`docker-compose/llms-benchmark/`) against
   the local oddyssey observability stack, and waits for the three
   services to answer.
2. Drives the model through the **opencode** CLI, on OpenRouter, at
   **medium** reasoning effort — headless, one session.
3. Gives it one mission — a single `/odd-observe` invocation naming the
   three services, the stored scenario `benchmark/llmbench-store-load/`,
   **full** depth and the **local** stack — and asks for every kind of
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
| --- | --- | --- |
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
