# OpenTelemetry Swift

Official docs root: https://opentelemetry.io/docs/languages/swift/
Every page below is fetchable as raw markdown by appending `index.md` to its URL (except the Examples and Registry rows, which are docs-site redirects to external/dynamic destinations — the URL given for those two rows is the actual redirect target).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/swift/getting-started/index.md) | Gets telemetry emitting from a simple (Vapor-based) Swift app to the console in under 5 minutes. | Use as the fastest path to a working, traces-emitting Swift app before layering in real instrumentation. |
| [Instrumentation](https://opentelemetry.io/docs/languages/swift/instrumentation/index.md) | Explains installing the full SDK when instrumenting an app vs. only the API when instrumenting a library, and configuring an exporter (e.g. OTLP) since the default `TracerProvider`/`MeterProvider` ship with none configured. | Use to decide whether the target Swift artifact needs the SDK (app) or only the API (library), and to wire up an OTLP exporter for real export. |
| [Instrumentation Libraries](https://opentelemetry.io/docs/languages/swift/libraries/index.md) | Explains consuming natively OpenTelemetry-instrumented libraries/frameworks; explicitly notes that, as of today, no Swift library is known to have native OpenTelemetry support ("help wanted"). | Do not assume auto-instrumentation exists for a Swift dependency — plan for manual instrumentation of third-party libraries. |
| [Examples](https://github.com/open-telemetry/opentelemetry-swift/tree/main/Examples) | The docs page redirects directly to the `Examples` directory of the `opentelemetry-swift` GitHub repository. | Browse this directory for runnable sample apps and patterns to copy from. |
| [Registry](https://opentelemetry.io/ecosystem/registry/?language=swift) | The docs page redirects to the OpenTelemetry ecosystem Registry, pre-filtered to Swift instrumentation libraries, exporters, and other components. | Search here for community-built Swift exporters/instrumentation before writing custom OTel code. |

## Planning notes

- Maturity: Traces are Stable; Metrics and Logs are still in Development — do not plan production dependence on Swift metrics/logs signal stability yet.
- No natively-instrumented third-party Swift libraries are known to exist — auto-instrumentation of dependencies generally is not available, so instrumentation work is manual.
- The SDK targets both server-side Swift (e.g. Vapor) and client-side Swift (iOS/macOS apps) — the same API/SDK applies regardless of runtime target.
- The default `TracerProvider`/`MeterProvider` are unconfigured out of the box (no exporter attached) — an exporter, such as OTLP, must be explicitly configured for telemetry to actually leave the process.

## Profiling

Cross-language facts — the signal status (Alpha), why a vendor SDK bypasses the Collector, how profiles correlate with traces — live in [profiling.md](profiling.md); this section carries only what is particular to this language. Verified 2026-09-05 against the linked pages.

| Profiler | What it is | What to do with it |
| --- | --- | --- |
| None known | Searched 2026-09-05: the Pyroscope SDK list (no Swift), the OTel eBPF profiler README (Swift not listed), the `opentelemetry-swift` README (no profiling mention). | A plan states "no continuous profiler found for Swift" and does not promise the signal. |
| [swift-server performance guide](https://github.com/swift-server/guides/blob/main/docs/performance.md) | Instruments' Time Profiler on macOS, `perf` flame graphs on Linux, after building with `swift build -c release`. | On-demand profiling only; **the trap**: a debug build profiles nothing representative — the guide's first instruction is release mode. |
