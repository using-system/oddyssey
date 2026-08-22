# OpenTelemetry PHP

Official docs root: https://opentelemetry.io/docs/languages/php/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/php/getting-started/index.md) | Get up and running with OpenTelemetry for PHP. | Use as the fastest path to a working end-to-end example; mirror its Composer package/setup steps in the plan's bootstrap step. |
| [Instrumentation](https://opentelemetry.io/docs/languages/php/instrumentation/index.md) | Manual instrumentation for OpenTelemetry PHP. | Use when auto-instrumentation doesn't cover a code path and custom spans/metrics/logs need to be added by hand. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/php/libraries/index.md) | How to use pre-built instrumentation libraries for common PHP frameworks/libraries. | Use to decide whether a dependency (framework, HTTP client, DB driver) already has a ready-made instrumentation package before writing custom code. |
| [Exporters](https://opentelemetry.io/docs/languages/php/exporters/index.md) | Configuration and usage of telemetry data exporters. | Reference when choosing and configuring exporters (OTLP, etc.) and their transport (gRPC/HTTP) for the target backend. |
| [Context](https://opentelemetry.io/docs/languages/php/context/index.md) | How the context API works in instrumented PHP applications. | Consult when the plan needs custom context propagation, notably around PHP's request lifecycle and optional Fiber-based context storage. |
| [Propagation](https://opentelemetry.io/docs/languages/php/propagation/index.md) | Context propagation for the PHP API. | Use to plan trace-context propagation across service boundaries (HTTP headers, queues) for distributed tracing. |
| [Resources](https://opentelemetry.io/docs/languages/php/resources/index.md) | Resource configuration and management. | Use to plan resource attributes (service name, version, deployment environment) that should be set at SDK init. |
| [SDK](https://opentelemetry.io/docs/languages/php/sdk/index.md) | OpenTelemetry SDK implementation details for PHP. | Reference when wiring up providers, processors, and exporters manually instead of relying only on auto-instrumentation. |
| [API reference](https://opentelemetry.io/docs/languages/php/api/) | Complete API documentation for PHP. | Use as the authoritative signature/method reference when writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/php/examples/) | Sample code demonstrating OpenTelemetry PHP usage. | Cross-check the plan's code snippets against these examples for idiomatic, up-to-date usage patterns. |
| [Registry](https://opentelemetry.io/docs/languages/php/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry PHP. | Search here to confirm whether a library/framework in the target app already has ready-made instrumentation before writing custom code. |

## Planning notes

- Traces, Metrics, and Logs are all marked **Stable** for OpenTelemetry PHP — safe to plan for all three signals without stability caveats.
- Auto-instrumentation requires PHP 8.0+; below that, only manual instrumentation via the API/SDK is available, which is worth checking early against the target app's PHP version.
- The SDK is distributed as multiple Composer packages (minimum: `API`, `Context`, `SDK`, plus an exporter) — application/library code should depend only on the `API` package, per official guidance, so a plan should distinguish "app" dependencies from "library" dependencies accordingly.
- Several optional PHP extensions affect capability and performance: `ext-grpc` (gRPC OTLP transport), `ext-protobuf` (significantly faster OTLP/protobuf export), `ext-zlib` (export compression), `ext-mbstring` (performance), and `ext-ffi` (enables Fiber-based context storage via `OTEL_PHP_FIBERS_ENABLED`) — a thorough plan should check which of these are installed/needed on the target environment.
