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

## Profiling

Cross-language facts — the signal status (Alpha), why a vendor SDK bypasses the Collector, how profiles correlate with traces — live in [profiling.md](profiling.md); this section carries only what is particular to this language. Verified 2026-09-05 against the linked pages.

| Profiler | What it is | What to do with it |
| --- | --- | --- |
| The Java row, on the JVM | Kotlin on the JVM (and Android in the compatibility mode this reference describes) is profiled by the JVM tools: [Pyroscope Java](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/java/) (async-profiler, `-javaagent`), JFR, and the [OTel Java agent extension](https://grafana.com/docs/pyroscope/latest/configure-client/trace-span-profiles/java-span-profiles/) for trace correlation — see [java.md](java.md). | **The trap**: nothing in the Kotlin docs or SDK is involved — the profiler attaches to the JVM, so a Kotlin plan copies the Java section verbatim and ignores the Kotlin SDK's Development status for this signal. |
| Other Kotlin Multiplatform targets | iOS and JavaScript targets: none known — searched 2026-09-05 the Pyroscope SDK list and the OTel eBPF profiler README. | State "none known" for those targets rather than borrowing the JVM answer. |
