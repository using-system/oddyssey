# OpenTelemetry Ruby

Official docs root: https://opentelemetry.io/docs/languages/ruby/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/ruby/getting-started/index.md) | Get telemetry from your app in less than 5 minutes. | Start here to get a minimal working setup before diving into manual instrumentation. |
| [Instrumentation](https://opentelemetry.io/docs/languages/ruby/instrumentation/index.md) | Instrumentation for OpenTelemetry Ruby — setting up providers and manually creating traces/metrics/logs in application code. | Use as the reference for hand-writing spans and metrics where no instrumentation library exists for a given dependency. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/ruby/libraries/index.md) | Using pre-built instrumentation libraries with OpenTelemetry Ruby. | Check first for an existing gem-based instrumentation before writing manual code for a framework or library. |
| [Exporters](https://opentelemetry.io/docs/languages/ruby/exporters/index.md) | Exporters for sending telemetry data to backends. | Use to select and configure the exporter (e.g. OTLP) for traces/metrics/logs collected by the SDK. |
| [Sampling](https://opentelemetry.io/docs/languages/ruby/sampling/index.md) | Sampling configuration and strategies for the Ruby SDK. | Use when the plan needs to control trace volume/cost via head or parent-based sampling. |
| [API reference](https://opentelemetry.io/docs/languages/ruby/api/) | Generated API documentation for the Ruby API/SDK. | Use to look up exact method signatures while writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/ruby/examples/) | Code examples demonstrating OpenTelemetry Ruby usage. | Use as a working reference implementation to copy patterns from for the current instrumentation task. |
| [Registry](https://opentelemetry.io/docs/languages/ruby/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry Ruby. | Search here first for any gem/framework in the target app to find an existing instrumentation library before writing manual code. |

## Planning notes

- Signal status per the docs index: Traces = Stable, Metrics = Development, Logs = Development — plan traces first; treat metrics and logs instrumentation as less mature and verify current behavior against the fetched page before relying on it.
- There is no dedicated zero-code/automatic-instrumentation section in the official index; instrumentation is applied through the `Instrumentation` and `Using instrumentation libraries` pages (gem-based auto-instrumentation of dependencies configured via `OpenTelemetry::SDK.configure`), not a standalone agent command like Python's `opentelemetry-instrument`.
- No dedicated Resources or Propagation top-level sections were listed on the index; check the Instrumentation and API reference pages for resource attribute and context-propagation configuration.
