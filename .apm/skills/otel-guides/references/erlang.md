# OpenTelemetry Erlang/Elixir

Official docs root: https://opentelemetry.io/docs/languages/erlang/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/erlang/getting-started/index.md) | Initial setup and introduction to using OpenTelemetry with Erlang/Elixir. | Start here: minimal app emitting telemetry in minutes; use as the baseline setup before customizing. |
| [Instrumentation](https://opentelemetry.io/docs/languages/erlang/instrumentation/index.md) | How to instrument code to generate telemetry data in Erlang/Elixir applications. | Use as the primary reference for writing manual spans and telemetry emission in application code. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/erlang/libraries/index.md) | Guidance on leveraging pre-built instrumentation libraries for frameworks like Phoenix and Ecto. | Check before writing manual spans — Phoenix, Ecto, or other common BEAM frameworks may already be covered. |
| [Exporters](https://opentelemetry.io/docs/languages/erlang/exporters/index.md) | Configuration and usage of exporters to send telemetry data to backends. | Use to pick and configure the OTLP (or other) exporter and endpoint. |
| [Propagation](https://opentelemetry.io/docs/languages/erlang/propagation/index.md) | Context propagation mechanisms for distributed tracing across services. | Use to wire up trace context propagation across process/service boundaries (e.g., HTTP headers, message metadata). |
| [Resources](https://opentelemetry.io/docs/languages/erlang/resources/index.md) | Defining and configuring resource attributes for telemetry data. | Use to attach service/deployment metadata (service.name, version, environment) to all emitted telemetry. |
| [Sampling](https://opentelemetry.io/docs/languages/erlang/sampling/index.md) | Strategies for sampling traces to manage data volume. | Use to control trace volume/cost via sampling configuration. |
| [Testing](https://opentelemetry.io/docs/languages/erlang/testing/index.md) | Testing approaches for telemetry instrumentation. | Use to validate that instrumentation actually emits the expected spans/attributes before shipping. |
| [API reference](https://opentelemetry.io/docs/languages/erlang/api/) | Complete API documentation for OpenTelemetry Erlang/Elixir. | Consult for exact function signatures and types when writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/erlang/examples/) | Code examples demonstrating OpenTelemetry usage patterns. | Use as working reference implementations to copy patterns from for setup, spans, or exporters. |
| [Registry](https://opentelemetry.io/docs/languages/erlang/registry/) | Catalog of instrumentation libraries, exporters, and other useful components. | Search here before building custom instrumentation to see if a component/library/exporter already exists. |

## Planning notes

- Traces are Stable; metrics and logs remain in development status — plan trace instrumentation as the primary, production-ready signal and treat metrics/logs support as still maturing.
- No zero-code/automatic instrumentation section is listed in the official docs index for Erlang/Elixir — instrumentation is manual code or via pre-built libraries (e.g., for Phoenix, Ecto), so check the Registry and "Using instrumentation libraries" page first.
- A dedicated Testing page exists for this language — use it to validate instrumentation, which is not called out as a standalone top-level section for every language.
