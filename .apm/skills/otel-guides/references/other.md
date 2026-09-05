# OpenTelemetry Other Languages

Official docs root: https://opentelemetry.io/docs/languages/other/
This page does not itself list SDKs as docs pages; instead it points to the community Registry and to open Special Interest Group (SIG) formation requests. The Registry row below is fetchable as raw markdown by appending `index.md` to its URL; the SIG-request rows link to GitHub issues, exactly as given on the page.

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [Registry](https://opentelemetry.io/ecosystem/registry/) | Catalog of unofficial/community-maintained OpenTelemetry implementations for languages not covered by an official SIG, plus instrumentation, exporters, and other components. | Search here first for any language without an official OTel docs page or SDK before writing custom instrumentation. |
| [Lua](https://github.com/open-telemetry/community/issues/1276) | Open community issue tracking interest in forming a SIG for an official Lua implementation. | No official Lua SDK exists; check the Registry for unofficial ones, and this issue for SIG-formation status. |
| [Perl](https://github.com/open-telemetry/community/issues/828) | Open community issue tracking interest in forming a SIG for an official Perl implementation. | No official Perl SDK exists; check the Registry for unofficial ones, and this issue for SIG-formation status. |
| [Julia](https://github.com/open-telemetry/community/issues/898) | Open community issue tracking interest in forming a SIG for an official Julia implementation. | No official Julia SDK exists; check the Registry for unofficial ones, and this issue for SIG-formation status. |

## Planning notes

- Languages hosted on another runtime are already covered: JVM-hosted ones (Scala, Clojure, Groovy) by the Java SDK and its zero-code agent, Node-hosted ones by the JavaScript SDK — check [references/java.md](java.md) and [references/js.md](js.md) before treating such a language as unsupported.
- OpenTelemetry is designed to be implementable in any language, so a target language having no official docs page here does not mean no SDK exists — check the Registry before concluding instrumentation is impossible.
- Community/unofficial implementations in the Registry vary widely in maturity and maintenance status; verify activity and spec compliance before depending on one.
- If nothing suitable is found, raising or gauging interest on a SIG-formation issue (as with Lua, Perl, Julia) is the documented path toward an official implementation, not something usable today.
- If you know of an unlisted implementation, the documented action is to add it to the Registry rather than build a duplicate.

## Profiling

Cross-language facts — the signal status (Alpha), why a vendor SDK bypasses the Collector, how profiles correlate with traces — live in [profiling.md](profiling.md); this section carries only what is particular to the languages this file covers. Verified 2026-09-05 against the linked pages.

| Profiler | What it is | What to do with it |
| --- | --- | --- |
| [OpenTelemetry eBPF profiler](https://github.com/open-telemetry/opentelemetry-ebpf-profiler) | Its README lists Perl and Zig beyond the languages this skill covers; host-level, Linux, privileged, OTLP profiles. Alloy's [`pyroscope.ebpf`](https://grafana.com/docs/alloy/latest/reference/components/pyroscope/pyroscope.ebpf/) has `perl_enabled`. | The answer for Perl on Linux. For a JVM-hosted or Node-hosted language, the Java or JavaScript row applies, as for tracing. |
| Anything else | Search the [Registry](https://opentelemetry.io/ecosystem/registry/) and the [Pyroscope SDK list](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/). | Record "none known" with the two places searched and the date; never a guess. |
