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
