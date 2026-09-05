# OpenTelemetry Go

Official docs root: https://opentelemetry.io/docs/languages/go/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/go/getting-started/index.md) | Introduction to using OpenTelemetry with Go for generating and collecting telemetry data. | Start here: minimal app emitting telemetry in minutes; use as the baseline setup before customizing. |
| [Instrumentation](https://opentelemetry.io/docs/languages/go/instrumentation/index.md) | Manual instrumentation for OpenTelemetry Go: tracer/meter/logger provider setup, spans, metrics instruments, log bridges, and a note on combining with eBPF-based zero-code instrumentation. | Use as the primary reference for writing manual spans, metrics instruments, and log emission; check the warning about not setting a global TracerProvider when combining with eBPF zero-code instrumentation. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/go/libraries/index.md) | Guidance on leveraging pre-built instrumentation libraries for Go applications. | Check before writing manual spans — a library may already instrument the framework or client in use (e.g., net/http, gRPC, database drivers). |
| [Exporters](https://opentelemetry.io/docs/languages/go/exporters/index.md) | Tools for sending collected telemetry data to backend systems. | Use to pick and configure the OTLP (or other) exporter and endpoint. |
| [Resources](https://opentelemetry.io/docs/languages/go/resources/index.md) | Configuration and management of resource attributes in Go instrumentation. | Use to attach service/deployment metadata (service.name, version, environment) to all emitted telemetry. |
| [Sampling](https://opentelemetry.io/docs/languages/go/sampling/index.md) | Techniques for controlling telemetry data collection volume in Go. | Use to control trace volume/cost via sampling configuration. |
| [API reference](https://opentelemetry.io/docs/languages/go/api/) | Technical documentation for OpenTelemetry Go APIs. | Consult for exact API signatures and types when writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/go/examples/) | Code samples demonstrating OpenTelemetry Go implementation patterns. | Use as working reference implementations to copy patterns from for setup, spans, or exporters. |
| [Registry](https://opentelemetry.io/docs/languages/go/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry Go. | Search here before building custom instrumentation to see if a component/library/exporter already exists. |

## Planning notes

- Traces and Metrics are Stable; Logs are currently in Beta status — treat logs support as less mature when planning.
- Zero-code/automatic instrumentation is available for Go via eBPF (e.g., OBI) and the Auto SDK, documented separately at `/docs/zero-code/go/` and `/docs/zero-code/go/autosdk/` — consider it as an alternative or complement to manual instrumentation, especially for apps that can't be recompiled.
- If combining manual spans with eBPF-based zero-code instrumentation, do not set a global TracerProvider — this is called out explicitly as a conflict to avoid.

## Profiling

Cross-language facts — the signal status (Alpha), why a vendor SDK bypasses the Collector, how profiles correlate with traces — live in [profiling.md](profiling.md); this section carries only what is particular to this language. Verified 2026-09-05 against the linked pages.

| Profiler | What it is | What to do with it |
| --- | --- | --- |
| [`runtime/pprof`](https://pkg.go.dev/runtime/pprof) / [`net/http/pprof`](https://pkg.go.dev/net/http/pprof) | Standard-library profiling: write profiles in pprof format, or serve them on `/debug/pprof/*`. | The zero-dependency baseline; Alloy can [pull `/debug/pprof/*`](https://grafana.com/docs/pyroscope/latest/configure-client/grafana-alloy/go_pull/) continuously without any SDK in the binary. |
| [Pyroscope Go](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/go_push/) | `github.com/grafana/pyroscope-go`, push mode; CPU, allocation, in-use, goroutine, mutex, block profiles. | **The trap**: mutex and block profiles are off in the Go runtime until `runtime.SetMutexProfileFraction` / `runtime.SetBlockProfileRate` are set — the page sets both before `pyroscope.Start`; a plan promising those types names the two calls. |
| [`github.com/grafana/otel-profiling-go`](https://grafana.com/docs/pyroscope/latest/configure-client/trace-span-profiles/go-span-profiles/) | A `TracerProvider` wrapper that labels samples with span IDs (root span by default, every span on request). | The trace correlation package; combine with the go.md note on not setting a global `TracerProvider` when eBPF zero-code tracing is in play. |
