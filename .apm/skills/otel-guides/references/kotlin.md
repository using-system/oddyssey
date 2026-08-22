# OpenTelemetry Kotlin

Official docs root: https://opentelemetry.io/docs/languages/kotlin/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Getting Started](https://opentelemetry.io/docs/languages/kotlin/getting-started/index.md) | Get started with the OpenTelemetry Kotlin SDK: supported platforms (Android, JVM, iOS, JavaScript), API stability/opt-in requirements, and the two supported modes (regular Kotlin Multiplatform mode vs. compatibility mode over the OpenTelemetry Java SDK). | Use first to pick a mode: regular KMP mode for multiplatform/non-JVM targets, or compatibility mode when the target is JVM/Android and should reuse the mature Java SDK/exporter ecosystem. |
| [Examples](https://opentelemetry.io/docs/languages/kotlin/examples/) | Sample code and practical demonstrations for OpenTelemetry Kotlin. | Cross-check the plan's code snippets against these examples for idiomatic, up-to-date usage patterns. |
| [Registry](https://opentelemetry.io/docs/languages/kotlin/registry/) | Catalog of instrumentation libraries, exporters, and other useful components for OpenTelemetry Kotlin. | Search here to confirm whether a library/framework in the target app already has ready-made instrumentation before writing custom code; also check the Java registry for JVM/Android targets using compatibility mode. |

## Planning notes

- Traces, Metrics, and Logs are all in **Development** status for OpenTelemetry Kotlin — treat it as less mature/stable than Java, JS, or PHP, and flag this to the user when planning production instrumentation.
- The API requires per-symbol opt-in via `@OptIn(ExperimentalApi::class)` (or a compiler-wide flag), reflecting its experimental, breaking-changes-without-notice status — call this out as a maintenance risk in any plan.
- OpenTelemetry Kotlin is a Kotlin Multiplatform implementation with two modes: regular mode (native KMP implementation, all targets) and compatibility mode, which is a façade over the OpenTelemetry Java SDK for JVM/Android targets only — for JVM/Android-only projects, compatibility mode lets a plan reuse the entire mature Java instrumentation/exporter ecosystem (see `java.md`).
- Supported platforms and minimums: Android (minSdk >=21), JVM (JDK >=11), iOS (16.0), JavaScript (ES5); Kotlin 2.0+ is required.
