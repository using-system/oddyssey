---
name: otel-guides
description: Curated map of the official OpenTelemetry documentation by language. Use when planning or implementing OpenTelemetry instrumentation for a codebase - pick the language, open its reference file, and follow the linked official docs for traces, metrics, logs, instrumentation libraries, exporters, and SDK configuration. Covers C++, .NET, Erlang/Elixir, Go, Java, JavaScript, Kotlin, PHP, Python, Ruby, Rust, Swift, and other community SDKs, plus the cross-language references for SDK configuration, semantic conventions, generative AI (the gen_ai conventions and the instrumentation library per LLM SDK or agent framework), the Collector, and profiling.
---

# OpenTelemetry Language Guides

A selection map over the official OpenTelemetry docs
(https://opentelemetry.io/docs/languages/). Pick the language of the code
you are instrumenting, read its reference file, then fetch the linked
official pages you need — links ending in `index.md` return the page as raw
markdown (the rest are external redirects), so read them directly instead of
paraphrasing from memory.

## Pick the language

| Language | Reference |
| --- | --- |
| C++ | [references/cpp.md](references/cpp.md) |
| .NET | [references/dotnet.md](references/dotnet.md) |
| Erlang/Elixir | [references/erlang.md](references/erlang.md) |
| Go | [references/go.md](references/go.md) |
| Java | [references/java.md](references/java.md) |
| JavaScript / Node.js | [references/js.md](references/js.md) |
| Kotlin | [references/kotlin.md](references/kotlin.md) |
| PHP | [references/php.md](references/php.md) |
| Python | [references/python.md](references/python.md) |
| Ruby | [references/ruby.md](references/ruby.md) |
| Rust | [references/rust.md](references/rust.md) |
| Swift | [references/swift.md](references/swift.md) |
| Anything else | [references/other.md](references/other.md) |

Each reference file lists every section of that language's official docs —
what it covers and what to do with it when planning instrumentation
(getting started, traces, metrics, logs, instrumentation libraries,
zero-code instrumentation where it exists, exporters, resources, sampling,
API references, registry).

## Cross-language references

Five things are the same whatever the language: the environment variables
that configure the SDK (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_RESOURCE_ATTRIBUTES`, ...), the conventions that name what you emit
(resource, HTTP, database, messaging, RPC, ...), the generative AI
conventions (`gen_ai.*` spans, token and duration metrics, content capture)
with the instrumentation library that emits them per SDK or framework, the
option of putting a Collector between the app and the backend (agent,
gateway, or neither), and the state of profiling (the signal's status, why
a vendor profiler bypasses the Collector, how profiles correlate with
traces).

| Topic | Reference |
| --- | --- |
| SDK configuration | [references/sdk-configuration.md](references/sdk-configuration.md) |
| Semantic conventions | [references/semconv.md](references/semconv.md) |
| Generative AI | [references/genai.md](references/genai.md) |
| Collector | [references/collector.md](references/collector.md) |
| Profiling | [references/profiling.md](references/profiling.md) |

Open the semantic conventions reference for every domain you name things
in, the generative AI reference whenever the code calls a model, an agent
framework, or an MCP server (its detection section lists the manifest names
that mean it does), the Collector reference before deciding between direct
OTLP export and a Collector, and the profiling reference before promising
profiles — its per-language table says which profiler exists for each
language.

## Rules

- Always confirm against the fetched official page before recommending a
  package name, API call, or env var — the linked docs are the source of
  truth, not memory.
- When a sentence decides a design, read the `index.md` page raw
  (`curl -sL <url>`) rather than through a summarising fetch: a summary
  dropped the Python distro page's "loaded ... via the entry points ...
  before any other code is executed", the one sentence that settles where
  code runs under the zero-code wrapper.
- Prefer zero-code/automatic instrumentation and existing instrumentation
  libraries over manual spans; check the language's registry section before
  writing any manual instrumentation.
- The registry pages render client-side, so a text fetch of them often
  returns nothing. When that happens, fall back in order: the language's
  contrib repository on GitHub (`opentelemetry-<lang>-contrib` — for Java it is `opentelemetry-java-instrumentation` — whose
  README lists the instrumentation packages), then the package index search
  (`pip index`, `npm search @opentelemetry`, Maven Central, NuGet,
  crates.io). If a page cannot be fetched at all, say so and mark whatever
  you derived from it as unverified — never present an unfetched claim as
  sourced.
- The planning notes in each reference file are a snapshot (last verified
  2026-08; the profiling reference, the `## Profiling` sections and the
  Python zero-code, resource-detector and pinning notes 2026-09-05); the
  fetched official page always overrides them — re-verify any stability
  or version claim you rely on.
- The local stack is one `odd_stack_up` away: OTLP on
  `http://localhost:4317` (gRPC) / `:4318` (HTTP). `localhost` holds only
  for host processes — a containerized app needs the host reachable from
  inside the container (e.g. `host.docker.internal`).
