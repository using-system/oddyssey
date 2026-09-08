---
name: k6-guides
description: Curated map of the official k6 load-testing docs - installation, running a script, scripting (checks/thresholds/scenarios), test types, protocols, and which questions a benchmark's inputs require before it can be authored. Use when authoring or reasoning about a k6 benchmark - pick the topic, open its reference file, and follow the linked official docs. Read by /odd-instrument-bench (which questions to ask), k6-benchmark-expert (authoring and validating), a stored benchmark's replay (running one), and the /odd-instrument-bench, /odd-observe, and /odd-verify preflights (ensuring k6 is present).
---

# k6 guides

Same pattern as `otel-guides` (one file per language) and
`observability-cli-guides` (one file per backend): a selection map whose
callers open exactly the reference they need instead of re-deriving k6
usage from memory. Here the selection axis is the topic.

## Fetching the docs

`grafana.com/docs/k6/latest/` serves raw markdown by appending `.md` to
any page URL, or via an `Accept: text/markdown` header.
`https://grafana.com/llms.txt` (curated index) and
`https://grafana.com/llms-full.txt` (~1.4 MB, ~1000 `docs/k6/latest`
URLs) exist at the site root - the cheapest way to enumerate the k6 doc
tree when this skill's reference files need re-verifying; per-page
fetching via the `.md` suffix is still how the content itself is read.
Both live at the site **root**, not under `/docs/k6/latest/` (that path
404s) - a natural first mistake, verify against the root before
concluding they don't exist.

**An underscore written outside backticks may come back
backslash-escaped.** Names the pages write as code keep their
underscores; names written as plain text - the metrics reference's
first column is the case that bites - are served as
`dropped\_iterations`, so a grep for the bare name finds nothing on a
page that does document the metric. It is not a property of tables:
verified live (this machine, 2026-09-06) on the fetched `.md` of
`using-k6/metrics/reference/` (56 escaped underscores, every one of
them an unbackticked name in a table's first column; `grep -c
dropped_iterations` -> `0`, `grep -c 'dropped\\_iterations'` -> `1`),
against `using-k6/k6-options/reference/` and `using-k6/thresholds/`
(143 and 7 table data rows, **zero** escaped underscores - both write
their names as code). Before concluding a metric or an option is
undocumented, grep with the underscore made optional
(`grep -i 'dropped.\?_iterations'`) or on the unambiguous fragment
alone (`grep -i dropped`).

## Which reference

| Question | Reference |
| --- | --- |
| Is k6 installed? How do I install/detect it? | [install.md](references/install.md) |
| How do I run a k6 script, read its output, know if it passed? | [running-tests.md](references/running-tests.md) |
| How do I validate a script without running the benchmark - `k6 inspect`, a one-iteration smoke? | [running-tests.md](references/running-tests.md) |
| Why is `res.body` null / why does `res.json()` throw? | [scripting.md](references/scripting.md) |
| How do I write the script - requests, checks, thresholds, staged load? | [scripting.md](references/scripting.md) |
| Which test type fits this investigation - smoke, load, stress, soak, spike, breakpoint? | [test-types.md](references/test-types.md) |
| What does a benchmark's authoring need decided, and by whom - human or agent? | [authoring-inputs.md](references/authoring-inputs.md) |
| Does k6 support the service's protocol (gRPC, WebSockets, ...)? | [protocols.md](references/protocols.md) |
| How do I drive an MCP server - the session handshake, SSE bodies, one session per VU? | [mcp.md](references/mcp.md) |
| Is this browser/frontend performance testing rather than API load? | [browser.md](references/browser.md) |

## Conventions

- Reference content is a **snapshot** ("last verified YYYY-MM") - the
  fetched official page always overrides it. Recommendations must come
  from a fetched page, never from memory; anything unfetchable is marked
  unverified rather than presented as sourced.
- **The k6 major version is stated.** `latest` currently documents k6
  **v2** - `install.md` names it, and `scripting.md` never recommends a
  removed executor or command. A skill that silently mixes v1 and v2
  guidance produces scripts that fail to start.
- These references cover k6 **itself** - never this project's
  `.odd/benchmarks/` format, never the manifest schema. That knowledge
  lives with `odd-memory`'s `benchmark` reference and
  `k6-benchmark-expert`.
