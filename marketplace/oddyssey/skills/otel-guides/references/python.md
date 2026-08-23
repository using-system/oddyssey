# OpenTelemetry Python

Official docs root: https://opentelemetry.io/docs/languages/python/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started by Example](https://opentelemetry.io/docs/languages/python/getting-started/index.md) | Get telemetry for your app in less than 5 minutes, using a Flask example; walks through zero-code instrumentation via `opentelemetry-instrument`, then layering manual traces/metrics on top, then exporting to a Collector. | Start here to confirm the fastest working path: run `opentelemetry-instrument` first, then decide if manual spans/metrics are needed on top. |
| [Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/index.md) | Manual instrumentation for OpenTelemetry Python: setting up TracerProvider/MeterProvider/LoggerProvider, creating and configuring spans (attributes, events, links, status, exceptions), synchronous/asynchronous metric instruments, and logging integration. | Use as the reference for hand-writing spans, metrics, and log correlation when zero-code instrumentation and libraries do not cover a code path. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/python/libraries/index.md) | Guidance on leveraging pre-built instrumentation libraries for common Python frameworks/packages instead of writing manual code. | Check this before writing manual instrumentation; prefer installing and configuring an existing `opentelemetry-instrumentation-*` package for the framework in use. |
| [Exporters](https://opentelemetry.io/docs/languages/python/exporters/index.md) | Processing and exporting collected telemetry data (traces, metrics, logs) to backends. | Use to pick and configure the exporter (e.g. OTLP) and span/metric processors for the target backend or Collector. |
| [Propagation](https://opentelemetry.io/docs/languages/python/propagation/index.md) | Context propagation for the Python SDK — how trace context crosses process/service boundaries. | Reference when wiring distributed tracing across services or non-HTTP transports that need custom propagators. |
| [Cookbook](https://opentelemetry.io/docs/languages/python/cookbook/index.md) | Practical recipes and common instrumentation patterns. | Consult for ready-made snippets covering frequent tasks before writing bespoke code. |
| [OpenTelemetry Distro](https://opentelemetry.io/docs/languages/python/distro/index.md) | How to build a custom OpenTelemetry Python distribution. | Use only if the plan requires shipping a pre-configured, opinionated distribution instead of assembling packages manually. |
| [Using mypy](https://opentelemetry.io/docs/languages/python/mypy/index.md) | Type-checking integration between OpenTelemetry Python and mypy. | Use when the target codebase enforces static typing and instrumentation code must pass mypy checks. |
| [Benchmarks](https://opentelemetry.io/docs/languages/python/benchmarks/index.md) | Performance benchmarking data/methodology for the Python SDK. | Reference when evaluating instrumentation overhead or justifying sampling/exporter batching decisions. |
| [API reference](https://opentelemetry.io/docs/languages/python/api/) | Generated API documentation for the Python API/SDK. | Use to look up exact function/class signatures while writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/python/examples/) | Sample code implementations. | Use as a working reference implementation to copy patterns from for the current instrumentation task. |
| [Registry](https://opentelemetry.io/docs/languages/python/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for Python. | Search here first for any framework/library in the target app to find an existing instrumentation package before writing manual code. |

## Planning notes

- Zero-code instrumentation is first-class: the `opentelemetry-instrument` command auto-instruments an app without code changes and is the recommended starting point (covered in Getting Started, not as a separate top-level section).
- Signal status per the docs index: Traces = Stable, Metrics = Stable, Logs = Development — treat log instrumentation as less mature and verify current behavior against the fetched page before relying on it.
- Requires Python 3.10+; base packages are `opentelemetry-api` and `opentelemetry-sdk`, with `opentelemetry-exporter-{exporter}` and `opentelemetry-instrumentation-{name}` as the naming convention for extension packages.
- Manual instrumentation is designed to layer on top of zero-code/automatic instrumentation (linking custom spans/metrics into the auto-instrumented app), not to replace it.
