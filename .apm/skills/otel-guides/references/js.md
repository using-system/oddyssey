# OpenTelemetry JavaScript / Node.js

Official docs root: https://opentelemetry.io/docs/languages/js/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started by Example](https://opentelemetry.io/docs/languages/js/getting-started/index.md) | Get started with OpenTelemetry in Node.js and in the browser. | Use as the fastest path to a working end-to-end example; mirror its setup steps for the plan's bootstrap step, choosing the Node.js or browser track. |
| [Instrumentation](https://opentelemetry.io/docs/languages/js/instrumentation/index.md) | Manual instrumentation: adding traces, metrics, and logs to code yourself using the API/SDK. Points to [automatic instrumentation](https://opentelemetry.io/docs/zero-code/js/index.md) as the recommended starting point, enriched with manual instrumentation as needed. | Decide the instrumentation strategy here first: default to zero-code automatic instrumentation for fast coverage, and use this page's API guidance only for custom spans/metrics/logs the agent can't produce. |
| [Using instrumentation libraries](https://opentelemetry.io/docs/languages/js/libraries/index.md) | How to instrument libraries an app depends on. | Use to decide whether a dependency already ships native/instrumentation-library support versus needing manual wrapping. |
| [Exporters](https://opentelemetry.io/docs/languages/js/exporters/index.md) | Process and export your telemetry data. | Reference when choosing and configuring exporters (OTLP, console, vendor-specific) for the target backend. |
| [Context](https://opentelemetry.io/docs/languages/js/context/index.md) | OpenTelemetry JavaScript Context API documentation. | Consult when the plan involves async operations or custom context propagation across callbacks/promises. |
| [Propagation](https://opentelemetry.io/docs/languages/js/propagation/index.md) | Context propagation for the JS SDK. | Use to plan trace-context propagation across service boundaries (HTTP headers, message queues) for distributed tracing. |
| [Resources](https://opentelemetry.io/docs/languages/js/resources/index.md) | Add details about your application's environment to your telemetry. | Use to plan resource attributes (service name, version, deployment environment) that should be set at SDK init. |
| [Sampling](https://opentelemetry.io/docs/languages/js/sampling/index.md) | Reduce the amount of telemetry created. | Include in the plan when trace volume/cost needs to be controlled; pick and configure a sampler. |
| [Serverless](https://opentelemetry.io/docs/languages/js/serverless/index.md) | Instrument your serverless functions with OpenTelemetry JavaScript. | Use when the target workload runs on serverless/FaaS platforms; follow its guidance instead of the generic Node.js setup. |
| [Benchmarks](https://opentelemetry.io/docs/languages/js/benchmarks/index.md) | Performance measurement documentation for the JavaScript SDK. | Reference if the plan needs to justify or bound the performance overhead of adding instrumentation. |
| [API reference](https://opentelemetry.io/docs/languages/js/api/) | OpenTelemetry JavaScript API reference (external page). | Use as the authoritative signature/method reference when writing manual instrumentation code. |
| [Examples](https://opentelemetry.io/docs/languages/js/examples/) | Explore more examples for OpenTelemetry JavaScript (external page). | Cross-check the plan's code snippets against these examples for idiomatic, up-to-date usage patterns. |
| [Registry](https://opentelemetry.io/docs/languages/js/registry/) | Instrumentation libraries, exporters, and other useful components for OpenTelemetry JavaScript. | Search here to confirm whether a library/framework in the target app already has ready-made instrumentation before writing custom code. |

## Planning notes

- Traces and Metrics are **Stable**; Logs are still in **Development** — flag log instrumentation as less mature when planning for JS/Node.js.
- Zero-code automatic instrumentation (https://opentelemetry.io/docs/zero-code/js/) is the recommended starting point for Node.js; it lives outside `/docs/languages/js/` but is the default path the "Instrumentation" page points to before reaching for manual API calls.
- Browser (client) instrumentation is explicitly called out as **experimental and mostly unspecified** — treat browser-side plans as higher-risk/lower-confidence than Node.js server-side plans.
- Node.js support follows active/maintenance LTS versions; older Node versions may work but are untested, which is worth noting if the target app runs on an old runtime.

## Profiling

Cross-language facts — the signal status (Alpha), why a vendor SDK bypasses the Collector, how profiles correlate with traces — live in [profiling.md](profiling.md); this section carries only what is particular to this language. Verified 2026-09-05 against the linked pages.

| Profiler | What it is | What to do with it |
| --- | --- | --- |
| [Pyroscope Node.js](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/nodejs/) | `@pyroscope/nodejs` (`Pyroscope.init` then `Pyroscope.start`); wall and heap profiles, configurable by `PYROSCOPE_*` variables. | **The trap**: CPU time is not collected unless `wall: { collectCpuTime: true }` (or `PYROSCOPE_WALL_COLLECT_CPU_TIME`) is set — the page's own comment says it "is required for CPU profiling functionality". |
| Trace correlation | Node.js is not among the five span-profiles packages on the [span profiles page](https://grafana.com/docs/pyroscope/latest/configure-client/trace-span-profiles/) (Go, Java, Ruby, .NET, Python), and its span-profiles page returned 404 on 2026-09-05. | None known — a plan says traces and profiles will not be linked for Node.js today. |
| [`--cpu-prof`](https://nodejs.org/api/cli.html#--cpu-prof) | Node's built-in V8 CPU profile written at exit. | On-demand only. Browser JavaScript: no profiler found in the Pyroscope SDK list; the eBPF profilers cover Node.js/V8 server processes only. |
