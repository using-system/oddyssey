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
