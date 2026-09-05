---
description: Where is the ODD loop? Read the repository's .odd/ history and render it as a one-screen synthesis - the loop state per lineage, its burn-down, the next recommended action - or, on request, the full tables (per-service loop state, findings ledger, trends, open telemetry gaps) - reports read-only, no backend queries, no report written; can record finding decisions (wontfix) into .odd/decisions.md
---

Answer "where is the loop?" for this repository, from its committed
memory alone.

- Arguments: $ARGUMENTS
- Expected fields (optional, free-form): service name(s), a stack
  (`local`, `grafana`, ...) and/or a deployment environment (`prod`,
  `uat`, ...) to restrict the status to - they map onto the scope the
  `get-status` skill renders. No arguments = the whole picture.
- Or a request for the full tables - "full", "everything", "every
  finding", "the whole ledger", "the trends" - which maps onto the
  skill's full rendering; a scoped status renders them by itself.
- Or a decision request on a finding - "wontfix finding F4 of
  <report>", "decline F2: <rationale>", "reopen F4". It may arrive in
  the arguments, or as a follow-up once a status has been rendered.

When the arguments already carry a decision request, skip the
render-first flow and route straight to **Record** below - the render
happens after the recording, so the finding is shown in its new state
rather than twice.

**Render.** Invoke the `get-status` skill, handing it the scope the
arguments named - the service name(s), the stack, the environment,
whether the full tables were asked for - and nothing named means the
whole picture on one screen. It owns the sources, the build order, the
two renderings, what a filter matching nothing produces, and the
graceful degradation; this prompt adds no rendering rule of its own.
The reply is the synthesis, the tables are the working data - the
status renders in the conversation, never as a committed artifact.

**Record.** When, and only when, the user asks for a decision on a
finding, record it per `odd-memory`'s `decisions` reference with the
request as the user phrased it: the finding reference, the verdict,
the rationale. The reference owns resolving it to a report and a
finding ID, the
ledger's format, and the commit - including asking back when the
reference is ambiguous or the rationale is missing. Never record a
decision that was not asked for. Once it has recorded, re-render the
affected finding's row through `get-status` - under the scope the status
was rendered with, or, when the request came in the arguments and no
status was rendered yet, under whatever else those arguments named - so
the user sees the state change the decision produced.

Reports are read-only here: this prompt never writes or edits a report,
and its only write surface is the decisions ledger, per `odd-memory`'s
`decisions` reference. Never query a backend, never start the
stack.
