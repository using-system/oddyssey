# ODD finding decisions

Decisions the maintainer took on findings recorded in
`.odd/observe-run-reports/` — the committed memory that lets
`/odd-status` stop rendering a declined finding as open. Rows are
appended, never rewritten; a later row for the same finding supersedes
the earlier one. Reports themselves are never edited — this ledger is
the only place a decision lives.

| Date | Finding | Verdict | Rationale |
|---|---|---|---|
| 2026-08-29 | 2026-08-26-1003-config-set-env-preservation.md / F4 | wontfix | Port-move is rare and interactive; the ~14.5 s hang is accepted |
| 2026-08-29 | 2026-08-26-1003-config-set-env-preservation.md / F5 | accepted-by-design | Next-restart-only telemetry endpoint is documented (telemetry.py); a port-moving session going dark is the design |
| 2026-08-29 | 2026-08-22-2154-mcp-otel-instrumentation-verification.md / A6 | accepted-by-design | Transient of the injected engine-kill scenario; a clean reset clears it (confirmed by 2026-08-22-2227) |
| 2026-08-29 | 2026-08-28-1531-stack-config-lifecycle.md / N2 | tracked | Real attribution gap; carried by issue #148 instead of the loop |
| 2026-08-29 | 2026-08-28-1531-stack-config-lifecycle.md / N2 | open | #148 shipped the opt-in (v1.8.2) and the 2026-08-29-1107 verification rules N2 FIXED - back to what the reports rule |
| 2026-09-03 | 2026-08-28-1531-stack-config-lifecycle.md / N5 | wontfix | 25 ms absolute on a stack_config-only write; the state-inspect is not worth removing |
| 2026-09-03 | 2026-08-28-1531-stack-config-lifecycle.md / N6 | accepted-by-design | stack_down(flush=True) is the terminal-down design: the wiper's own C0/C1 telemetry dies with the store it destroys |
| 2026-09-16 | 2026-09-04-1107-mcp-read-tools.md / F4 | accepted-by-design | The run slug is the per-run identity (spec decision 9): cumulative SDK histograms describe the last process, and the protocol counts with spanmetrics and the trace list (section 7) |
| 2026-09-16 | 2026-09-04-1107-mcp-read-tools.md / F5 | accepted-by-design | Prometheus's 5 min lookback is the store's, not the service's: the protocol pins --time or uses range queries (section 7) |
| 2026-09-16 | 2026-09-04-1107-mcp-read-tools.md / O2 | wontfix | A dev-machine venv artifact: the replay re-syncs the venv (uv sync) before driving, so service.version names the build under test |
| 2026-09-16 | 2026-09-04-1107-mcp-read-tools.md / O3 | wontfix | Driver-side: the inspector's cold npx cache on a fresh HOME; warmup calls are discarded from every measured number |
| 2026-09-16 | 2026-09-03-1710-mcp-read-tools.md / F1 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F1, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1710-mcp-read-tools.md / F2 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F2, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1710-mcp-read-tools.md / F3 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F3, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1710-mcp-read-tools.md / F4 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F4, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1710-mcp-read-tools.md / F5 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F5, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1756-remeasure-mcp-read-tools.md / F1 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F1, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1756-remeasure-mcp-read-tools.md / F2 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F2, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1756-remeasure-mcp-read-tools.md / F3 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F3, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1756-remeasure-mcp-read-tools.md / F4 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F4, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1756-remeasure-mcp-read-tools.md / F5 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F5, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1756-remeasure-mcp-read-tools.md / O1 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / O1, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1830-status-quick-check.md / F1 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F1, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1830-status-quick-check.md / F2 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F2, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1830-status-quick-check.md / F3 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F3, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-03-1830-status-quick-check.md / F4 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F4, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-04-1038-status-quick-check.md / F1 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F1, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-04-1038-status-quick-check.md / F2 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F2, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-04-1038-status-quick-check.md / F3 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F3, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-04-1038-status-quick-check.md / F4 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F4, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-09-04-1038-status-quick-check.md / F5 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F5, the lineage's current baseline, where it is ruled and verified |
| 2026-09-16 | 2026-08-26-1003-config-set-env-preservation.md / F1 | not-an-anomaly | A pass recorded in the findings table (the #62 fix under test held), ruled still passing by 2026-08-26-1039-verify-config-set-env-preservation.md |
| 2026-09-16 | 2026-08-28-1531-stack-config-lifecycle.md / N1 | not-an-anomaly | A pass recorded in the findings table (the #117 lifecycle contract held), ruled still correct 6 of 6 by 2026-08-29-1107-verify-stack-config-lifecycle.md |
| 2026-09-16 | 2026-08-22-2154-mcp-otel-instrumentation-verification.md / A5 | fixed-elsewhere | Fixed by #149 (the oddyssey.stack.probe.failures counter), ruled FIXED then holds-fixed by the 2026-08-29-0953 and 2026-08-29-1107 verifications outside this report's chain |
| 2026-09-16 | 2026-08-26-1003-config-set-env-preservation.md / F2 | fixed-elsewhere | Fixed by #149 (the image inspect span is oddyssey.docker.image-inspect carrying the image), ruled FIXED then holds-fixed by the 2026-08-29-0953 and 2026-08-29-1107 verifications outside this report's chain |
| 2026-09-16 | 2026-09-16-1951-mcp-read-tools.md / F9 | accepted-by-design | The httpcore import moved off the request path into process startup on purpose: a one-shot process pays it once either way and a long-lived MCP session pays it once for all its calls; the start span now measures it |
| 2026-09-16 | 2026-09-16-1951-mcp-read-tools.md / F3 | accepted-by-design | The one-shot driver's process lifecycle (interpreter, SDK init, transport handshake, flush) is the scenario's cost, not the request path's; the start and shutdown spans make it measurable and a long-lived session pays it once |
| 2026-09-16 | 2026-09-16-1951-mcp-read-tools.md / F8 | accepted-by-design | Time before the package's import and after the provider's shutdown is the launcher's (npx, the inspector, the interpreter) - outside anything the server can stamp |
| 2026-09-16 | 2026-09-16-1951-mcp-read-tools.md / F7 | wontfix | 0.4 ms per odd_config_get for the installed-version lookup, on a tool whose whole root is under 1 ms - not worth a cache |
| 2026-09-16 | 2026-09-16-1951-mcp-read-tools.md / F4 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F4, ruled accepted-by-design there |
| 2026-09-16 | 2026-09-16-1951-mcp-read-tools.md / F5 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / F5, ruled accepted-by-design there |
| 2026-09-16 | 2026-09-16-1951-mcp-read-tools.md / O3 | superseded | The same finding as 2026-09-04-1107-mcp-read-tools.md / O3, ruled wontfix there |
| 2026-09-16 | 2026-09-16-1931-verify-mcp-read-tools.md / F6 | fixed-elsewhere | Fixed by b1ed04c (httpcore imported at module load): the interval measured 4.2 ms on the p50 trace of 2026-09-16-1951-mcp-read-tools.md, under the 5 ms bar |
| 2026-09-16 | 2026-09-16-1931-verify-mcp-read-tools.md / F7 | superseded | The same finding as 2026-09-16-1951-mcp-read-tools.md / F7, ruled wontfix there |
| 2026-09-16 | 2026-09-16-1931-verify-mcp-read-tools.md / F8 | superseded | The same finding as 2026-09-16-1951-mcp-read-tools.md / F8, ruled accepted-by-design there |
| 2026-09-16 | 2026-09-04-1107-mcp-read-tools.md / F1 | fixed-elsewhere | Fixed by c68faf2 (no TLS context for http probes) and b1ed04c (httpcore imported at load): 28.8 ms then 14.9 ms (2026-09-16-1931-verify-mcp-read-tools.md) then 4.2 ms (2026-09-16-1951-mcp-read-tools.md), under the 5 ms bar |
| 2026-09-16 | 2026-09-04-1107-mcp-read-tools.md / F3 | accepted-by-design | The one-shot driver's process lifecycle is the scenario's cost, not the request path's; c68faf2 added the start and shutdown spans that make it measurable (2026-09-16-1931-verify-mcp-read-tools.md ruled it reduced, 2026-09-16-1951-mcp-read-tools.md measures it) |
