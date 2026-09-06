# Which LLM can run oddyssey?

oddyssey does not need the largest model on the market. Observing a
running system is reading — telemetry first, then the code the telemetry
points at — and a model that reads carefully beats a model that reasons
brilliantly about the wrong query. This directory is where that claim
gets measured instead of asserted.

One model, one run, one row. The protocol is fixed, the traffic is
replayed identically, and the only variable is the model.

## Results

| Model | Run duration | Input tokens | Output tokens | Cache tokens | Confirmed / reported | oddyssey |
| --- | --- | --- | --- | --- | --- | --- |
| _no run recorded yet_ | | | | | | |

**Confirmed / reported** is the grade. The denominator is how many
findings the model reported; the numerator is how many of them held up
when each was checked back against the telemetry it cited and the code it
accused. A model that reports three findings and gets three right scores
`3 / 3`; a model that reports twelve and gets four right scores `4 / 12`
— and the second is the worse report, however long it is.

The table carries no history: one row per model, always its latest run.
The token counts come from the opencode session export, not from the
model's own account of itself.

## How a row is produced

```text
/launch-llms-benchmark anthropic/claude-sonnet-5 <your OpenRouter key>
```

That command runs the whole protocol and comes back with a pull request
adding or replacing the model's row. What it does:

1. Brings the demo stack up (`docker-compose/llms-benchmark/`) against
   the local oddyssey observability stack, and waits for the three
   services to answer.
2. Drives the model through the **opencode** CLI, on OpenRouter, at
   **medium** reasoning effort — headless, one session.
3. Gives it one mission: `/odd-observe` in **quick** mode, running the
   stored scenario `benchmark/llmbench-store-load/`, on the **local**
   stack. Both halves are named on purpose — the scenario, so every row
   comes from the same replayed traffic; the stack, so no row is observed
   against a backend the others were not.
4. Grades the report finding by finding, on evidence: the cited query is
   re-run, the accused line is opened. Both hold, or the finding does not
   count.
5. Opens the results PR from a clean `main`, carrying the row and the
   per-finding rulings — and nothing else.

A run takes roughly twenty to forty minutes, almost all of it the
model's own observation. The scenario itself is two minutes.

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
export OPENAI_API_KEY=<an OpenRouter key>
docker compose -f ../docker-compose/llms-benchmark/docker-compose.yml up -d --build

curl localhost:8010/health                      # the catalog API
curl localhost:8012/health                      # the agent
curl -s localhost:8012/ask -H 'content-type: application/json' \
  -d '{"question":"I need a quiet coffee grinder under 100 euros."}'
```

The local oddyssey stack must be up first (`odd_stack_up`) — that is
where the telemetry lands.
