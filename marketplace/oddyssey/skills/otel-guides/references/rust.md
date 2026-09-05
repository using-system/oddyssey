# OpenTelemetry Rust

Official docs root: https://opentelemetry.io/docs/languages/rust/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/rust/getting-started/index.md) | How to use OpenTelemetry with Rust to generate and collect telemetry data. | Start here for the minimal working setup (crates, provider setup) before writing broader instrumentation. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/rust/libraries/index.md) | How to instrument libraries an app depends on. | Check first for an existing crate-based instrumentation before writing manual spans/metrics for a dependency. |
| [Exporters](https://opentelemetry.io/docs/languages/rust/exporters/index.md) | Backend integration options for exporting telemetry data (OTLP, Zipkin, Stackdriver, and vendor integrations such as AWS, Datadog, Dynatrace, Jaeger, Prometheus). | Use to select and configure the exporter crate for the target backend or Collector. |
| [API reference](https://opentelemetry.io/docs/languages/rust/api/) | Generated API/SDK documentation for the `opentelemetry` and `opentelemetry-sdk` crates. | Use to look up exact trait/struct/function signatures while writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/rust/examples/) | Code samples demonstrating OpenTelemetry Rust usage. | Use as a working reference implementation to copy patterns from for the current instrumentation task. |
| [Registry](https://opentelemetry.io/docs/languages/rust/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry Rust. | Search here first for any crate/framework in the target app to find an existing instrumentation component before writing manual code. |

## Planning notes

- Signal status per the docs index: Traces = Beta, Metrics = Beta, Logs = Beta — all three signals are still pre-stable; verify current maturity against the fetched index page before committing to an approach.
- The official index lists no dedicated Traces, Metrics, Logs, Resources, Sampling, Propagation, or zero-code/automatic-instrumentation sections as separate top-level pages; that content is folded into Getting Started, Using instrumentation libraries, and the API reference. There is no Rust equivalent of Python's `opentelemetry-instrument` zero-code agent — instrumentation is done in code via the `opentelemetry` / `opentelemetry-sdk` crates.
- OpenTelemetry publishes multiple crates (core `opentelemetry`, `opentelemetry-sdk`, plus exporter and vendor-integration crates); check the Registry and Exporters pages to avoid hand-rolling something an existing crate already provides.

## Profiling

Cross-language facts — the signal status (Alpha), why a vendor SDK bypasses the Collector, how profiles correlate with traces — live in [profiling.md](profiling.md); this section carries only what is particular to this language. Verified 2026-09-05 against the linked pages.

| Profiler | What it is | What to do with it |
| --- | --- | --- |
| [Pyroscope Rust](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/rust/) | The `pyroscope` crate with the `backend-pprof-rs` feature (`PyroscopeAgentBuilder`), built on [pprof-rs](https://github.com/tikv/pprof-rs), a sampling CPU profiler; sample rate 100 Hz by default. | **The trap**: CPU only, per the [profile types table](https://grafana.com/docs/pyroscope/latest/configure-client/profile-types/), and Rust is not among the span-profiles packages — no trace correlation known (2026-09-05). |
| [OpenTelemetry eBPF profiler](https://github.com/open-telemetry/opentelemetry-ebpf-profiler) / Alloy `pyroscope.ebpf` | Native Rust binaries are unwound without frame pointers or debug symbols on the host. | The no-code alternative on a privileged Linux host. |
