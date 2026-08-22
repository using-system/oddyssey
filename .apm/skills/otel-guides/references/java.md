# OpenTelemetry Java

Official docs root: https://opentelemetry.io/docs/languages/java/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Intro to OpenTelemetry Java](https://opentelemetry.io/docs/languages/java/intro/index.md) | Intro to the OpenTelemetry Java ecosystem. | Read first for orientation on how the API, SDK, and instrumentation ecosystem fit together before planning. |
| [Getting Started by Example](https://opentelemetry.io/docs/languages/java/getting-started/index.md) | Get telemetry for your app in less than 5 minutes. | Use as the fastest path to a working end-to-end example; mirror its dependency and setup steps in the plan's bootstrap step. |
| [Instrumentation ecosystem](https://opentelemetry.io/docs/languages/java/instrumentation/index.md) | Overview of instrumentation categories: zero-code Java agent, zero-code Spring Boot starter, library instrumentation, native instrumentation, manual instrumentation, and shims; also covers context propagation, semantic conventions, and log instrumentation. Links out to the dedicated [Java agent](https://opentelemetry.io/docs/zero-code/java/agent/index.md) and [Spring Boot starter](https://opentelemetry.io/docs/zero-code/java/spring-boot-starter/index.md) zero-code pages. | Decide the instrumentation strategy here first: default to the zero-code Java agent (or Spring Boot starter) for fast, low-risk coverage, and fall back to manual/library instrumentation only where the agent doesn't reach. |
| [Record Telemetry with API](https://opentelemetry.io/docs/languages/java/api/) | How to record telemetry (traces, metrics, logs) using the OpenTelemetry API. | Use when manual instrumentation is required (custom spans, metrics, log correlation) to know exactly which API calls to add to application code. |
| [Manage Telemetry with SDK](https://opentelemetry.io/docs/languages/java/sdk/index.md) | How to manage telemetry with the OpenTelemetry SDK (providers, processors, exporters wiring). | Use to plan how the SDK is initialized and wired to exporters/processors when not relying solely on the zero-code agent. |
| [Configure the SDK](https://opentelemetry.io/docs/languages/java/configuration/index.md) | Configuration guidance for the OpenTelemetry SDK (env vars, system properties, declarative config). | Reference when defining the concrete environment variables/config file the plan should set for endpoints, resource attributes, sampling, etc. |
| [JMX Metrics](https://opentelemetry.io/docs/languages/java/jmx/index.md) | Collect metrics from JMX MBeans using OpenTelemetry. | Include when the target app runs on the JVM and exposes useful JMX MBeans (e.g. app servers, connection pools) that should be scraped as metrics. |
| [Examples](https://opentelemetry.io/docs/languages/java/examples/) | Example implementations and code samples for OpenTelemetry Java. | Cross-check the plan's code snippets against these examples for idiomatic, up-to-date usage patterns. |
| [Registry](https://opentelemetry.io/docs/languages/java/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry Java. | Search here to confirm whether a library/framework in the target app already has ready-made instrumentation before writing custom code. |

## Planning notes

- Traces, metrics, and logs are all marked **Stable** for OpenTelemetry Java — safe to plan for all three signals without stability caveats.
- The zero-code Java agent is the officially recommended starting point: it auto-detects and instruments a large set of libraries with no code changes, so an instrumentation plan should default to it unless there's a specific reason for manual/library instrumentation.
- Spring Boot apps have a dedicated zero-code option (Spring Boot starter) that layers on top of library instrumentation via Spring autoconfigure — prefer it over the generic Java agent when the target is a Spring Boot service and code-level integration is acceptable.
- JMX metrics collection is a Java-specific capability worth calling out separately in a plan when the target runs on the JVM and exposes MBeans (e.g., JVM internals, application servers).
