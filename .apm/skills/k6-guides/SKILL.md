---
name: k6-guides
description: Curated map of the official k6 load-testing docs - installation, running a script, scripting (checks/thresholds/scenarios), test types, protocols, and which questions a benchmark's inputs require before it can be authored. Use when authoring or reasoning about a k6 benchmark - pick the topic, open its reference file, and follow the linked official docs. Read by /odd-instrument-bench (which questions to ask) and k6-benchmark-expert (authoring); run-scenario reads it separately at execution time.
---

# k6 guides

Same pattern as `otel-guides` (one file per language) and
`observability-cli-guides` (one file per backend): a selection map whose
callers open exactly the reference they need instead of re-deriving k6
usage from memory. Here the selection axis is the topic.

## Fetching the docs

`grafana.com/docs/k6/latest/` serves raw markdown by appending `.md` to
any page URL, or via an `Accept: text/markdown` header - the same
convention `observability-cli-guides/references/datadog.md` documents
for Datadog's docs. `https://grafana.com/llms.txt` (curated index) and
`https://grafana.com/llms-full.txt` (~1.4 MB, ~1000 `docs/k6/latest`
URLs) exist at the site root - the cheapest way to enumerate the k6 doc
tree when this skill's reference files need re-verifying; per-page
fetching via the `.md` suffix is still how the content itself is read.
Both live at the site **root**, not under `/docs/k6/latest/` (that path
404s) - a natural first mistake, verify against the root before
concluding they don't exist.

## Which reference

| Question | Reference |
| --- | --- |
| Is k6 installed? How do I install/detect it? | [install.md](references/install.md) |
| How do I run a k6 script, read its output, know if it passed? | [running-tests.md](references/running-tests.md) |
| How do I write the script - requests, checks, thresholds, staged load? | [scripting.md](references/scripting.md) |
| Which test type fits this investigation - smoke, load, stress, soak, spike, breakpoint? | [test-types.md](references/test-types.md) |
| What does a benchmark's authoring need decided, and by whom - human or agent? | [authoring-inputs.md](references/authoring-inputs.md) |
| Does k6 support the service's protocol (gRPC, WebSockets, ...)? | [protocols.md](references/protocols.md) |
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
  lives with `create-update-benchmark` and `k6-benchmark-expert`.
