# OpenTelemetry .NET

Official docs root: https://opentelemetry.io/docs/languages/dotnet/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/dotnet/getting-started/index.md) | Get telemetry for your app in less than 5 minutes. | Start here: minimal app emitting telemetry in minutes; use as the baseline setup before customizing. |
| [Traces](https://opentelemetry.io/docs/languages/dotnet/traces/index.md) | Collect and export trace telemetry data using OpenTelemetry .NET. | Use when writing manual spans/activities and configuring the TracerProvider. |
| [Metrics](https://opentelemetry.io/docs/languages/dotnet/metrics/index.md) | Collect and export metric telemetry data using OpenTelemetry .NET. | Use when defining counters/histograms/gauges and configuring the MeterProvider. |
| [Logs](https://opentelemetry.io/docs/languages/dotnet/logs/index.md) | Collect and export log telemetry data using OpenTelemetry .NET. | Use when wiring up `ILogger`/log providers to emit OpenTelemetry-correlated logs. |
| [Instrumentation](https://opentelemetry.io/docs/languages/dotnet/instrumentation/index.md) | Instrumentation capabilities for OpenTelemetry .NET, including manual setup via `System.Diagnostics` (Activity API) and a pointer to zero-code/automatic instrumentation. | Decide here whether to use manual instrumentation, automatic (zero-code, currently beta) instrumentation, or both together. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/dotnet/libraries/index.md) | Guidance on leveraging pre-built instrumentation libraries with OpenTelemetry .NET. | Check before writing manual spans — a NuGet instrumentation library may already cover the framework in use (ASP.NET Core, HttpClient, EF Core, etc.). |
| [Resources](https://opentelemetry.io/docs/languages/dotnet/resources/index.md) | Learn about resources and how to use them in OpenTelemetry .NET. | Use to attach service/deployment metadata (service.name, version, environment) to all emitted telemetry. |
| [Exporters](https://opentelemetry.io/docs/languages/dotnet/exporters/index.md) | Exporter options for sending telemetry data. | Use to pick and configure the OTLP (or other) exporter and endpoint. |
| [Sampling](https://opentelemetry.io/docs/languages/dotnet/sampling/index.md) | Configure sampling behavior in OpenTelemetry .NET. | Use to control trace volume/cost via head or tail sampling configuration. |
| [.NET Framework instrumentation configuration](https://opentelemetry.io/docs/languages/dotnet/netframework/index.md) | Configuration guidance specific to .NET Framework (as opposed to modern .NET/.NET Core) environments. | Consult when the target app runs on classic .NET Framework rather than .NET/.NET Core, since setup differs. |
| [Troubleshooting](https://opentelemetry.io/docs/languages/dotnet/troubleshooting/index.md) | How to troubleshoot OpenTelemetry .NET. | Use when telemetry isn't appearing or exporters fail, to diagnose configuration issues. |
| [OpenTelemetry Tracing Shim](https://opentelemetry.io/docs/languages/dotnet/shim/index.md) | Migration/compatibility layer for existing tracing implementations. | Use when migrating an app off an older tracing API without rewriting all instrumentation at once. |
| [Tracing API reference](https://opentelemetry.io/docs/languages/dotnet/traces-api/) | API documentation for tracing functionality. | Consult for exact tracing API signatures and types when writing manual spans. |
| [Metrics API reference](https://opentelemetry.io/docs/languages/dotnet/metrics-api/) | API documentation for metrics functionality. | Consult for exact metrics API signatures and types when writing manual instruments. |
| [Examples](https://opentelemetry.io/docs/languages/dotnet/examples/) | Code examples demonstrating OpenTelemetry .NET usage. | Use as working reference implementations to copy patterns from for setup, spans, or exporters. |
| [Registry](https://opentelemetry.io/docs/languages/dotnet/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry .NET. | Search here before building custom instrumentation to see if a component/library/exporter already exists. |

## Planning notes

- Zero-code/automatic instrumentation is available for .NET (currently in beta) and can be combined with manual instrumentation — the docs explicitly say you are "not limited to using one kind of instrumentation," so a plan can start with automatic instrumentation and layer in manual spans where needed.
- All three signals — traces, metrics, and logs — are marked Stable.
- .NET Framework (the legacy, Windows-only runtime) has its own configuration page separate from modern .NET, since setup and supported features differ; confirm which runtime the target app uses before following the general instrumentation guide.
- The Tracing Shim exists specifically to ease migration from pre-existing tracing APIs (e.g., OpenTracing) without a full rewrite.
