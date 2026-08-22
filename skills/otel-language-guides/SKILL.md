---
name: otel-language-guides
description: Curated map of the official OpenTelemetry documentation by language. Use when planning or implementing OpenTelemetry instrumentation for a codebase - pick the language, open its reference file, and follow the linked official docs for traces, metrics, logs, instrumentation libraries, exporters, and SDK configuration. Covers C++, .NET, Erlang/Elixir, Go, Java, JavaScript, Kotlin, PHP, Python, Ruby, Rust, Swift, and other community SDKs.
---

# OpenTelemetry Language Guides

A selection map over the official OpenTelemetry docs
(https://opentelemetry.io/docs/languages/). Pick the language of the code
you are instrumenting, read its reference file, then fetch the linked
official pages you need — every linked page is raw markdown (URLs end in
`index.md`), so read them directly instead of paraphrasing from memory.

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

## Cross-language SDK configuration

Whatever the language, the exporter and resource knobs are the same
environment variables (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_RESOURCE_ATTRIBUTES`, ...):
[references/sdk-configuration.md](references/sdk-configuration.md).

## Rules

- Always confirm against the fetched official page before recommending a
  package name, API call, or env var — the linked docs are the source of
  truth, not memory.
- Prefer zero-code/automatic instrumentation and existing instrumentation
  libraries over manual spans; check the language's registry section before
  writing any manual instrumentation.
- A local export target is one `odd_stack_up` away: OTLP on
  `http://localhost:4317` (gRPC) / `:4318` (HTTP).
