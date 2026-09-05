# OpenTelemetry C++

Official docs root: https://opentelemetry.io/docs/languages/cpp/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/cpp/getting-started/index.md) | Get telemetry for your app in less than 5 minutes. | Start here: minimal app emitting telemetry in minutes; use as the baseline setup before customizing. |
| [Instrumentation](https://opentelemetry.io/docs/languages/cpp/instrumentation/index.md) | Manual instrumentation for traces, metrics, and logs: initializing providers/exporters, creating spans, counters/histograms, and log records. | Use as the primary reference for writing manual spans, metrics instruments, and log emission in application code. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/cpp/library/index.md) | Guidance on leveraging pre-built instrumentation libraries in C++. | Check before writing manual spans — a pre-built library may already instrument the framework or component in use. |
| [Exporters](https://opentelemetry.io/docs/languages/cpp/exporters/index.md) | Documentation for exporting telemetry data from C++ applications. | Use to pick and configure the OTLP (or other) exporter and endpoint. |
| [API reference](https://opentelemetry.io/docs/languages/cpp/api/) | Complete API documentation for OpenTelemetry C++. | Consult for exact function signatures, types, and options when writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/cpp/examples/) | Practical code examples demonstrating OpenTelemetry C++ usage. | Use as working reference implementations to copy patterns from for setup, spans, or exporters. |
| [Registry](https://opentelemetry.io/docs/languages/cpp/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry C++. | Search here before building custom instrumentation to see if a component/library/exporter already exists. |

## Planning notes

- No zero-code/automatic instrumentation exists for C++: the docs explicitly state OpenTelemetry C++ cannot auto-instrument a library when its source code isn't available, so all instrumentation must be manual (own code) or via an existing instrumentation library.
- All three signals — traces, metrics, and logs — are marked Stable, so there is no need to gate a plan around experimental-signal caveats.
- Always check the Registry and "Using instrumentation libraries" page before hand-writing spans for a well-known library, since manual instrumentation is the default path in C++.

## Profiling

Cross-language facts — the signal status (Alpha), why a vendor SDK bypasses the Collector, how profiles correlate with traces — live in [profiling.md](profiling.md); this section carries only what is particular to this language. Verified 2026-09-05 against the linked pages.

| Profiler | What it is | What to do with it |
| --- | --- | --- |
| [OpenTelemetry eBPF profiler](https://github.com/open-telemetry/opentelemetry-ebpf-profiler) | Host-level Linux profiler emitting the OTel profiles signal; native C/C++ without DWARF debug information (unwinds through `.eh_frame`); runs as a Collector distribution (`otelcol-ebpf-profiler`). | The only continuous profiler for C++ found: there is no Pyroscope C++ SDK and the `opentelemetry-cpp` README says nothing about profiling. Needs a privileged Linux host; symbol resolution is the trap — keep symbols on the binaries or plan for "unknown" frames. |
| [Alloy `pyroscope.ebpf`](https://grafana.com/docs/pyroscope/latest/configure-client/grafana-alloy/ebpf/) | Grafana's eBPF collector, C/C++ supported, CPU profiles only, pushes to Pyroscope over Pyroscope's own API. | Same constraints (Linux, root); no memory or lock profiles for C++ from either path. |
