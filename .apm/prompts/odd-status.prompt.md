---
description: Where is the ODD loop? Read the repository's .odd/ history and render per-service loop state, the findings ledger, trends, open telemetry gaps, and the next recommended action - reports read-only, no backend queries, no report written; can record finding decisions (wontfix) into .odd/decisions.md
---

Answer "where is the loop?" for this repository, from its committed
memory alone.

- Arguments: $ARGUMENTS
- Expected fields (optional, free-form): service name(s), a stack
  (`local`, `grafana`, ...) and/or a deployment environment (`prod`,
  `uat`, ...) to restrict the status to - they map onto the scope the
  `get-status` skill renders. No arguments = the whole picture.
- Or a decision request on a finding - "wontfix finding F4 of
  <report>", "decline F2: <rationale>", "reopen F4". It may arrive in
  the arguments, or as a follow-up once a status has been rendered.

**Render.** Invoke the `get-status` skill, handing it the scope the
arguments named - the service name(s), the stack, the environment, and
nothing named means the whole picture. It owns the sources, the build
order, what a filter matching nothing produces, and the graceful
degradation; this prompt adds no rendering rule of its own. The status
renders in the conversation, as tables - never a committed artifact.

**Record.** When, and only when, the user asks for a decision on a
finding, invoke the `record-finding-decision` skill with the request as
the user phrased it: the finding reference, the verdict, the rationale.
It owns resolving the reference to a report and a finding ID, the
ledger's format, and the commit - including asking back when the
reference is ambiguous or the rationale is missing. Never record a
decision that was not asked for. Once it has recorded, re-render the
affected finding's row through `get-status`, under the scope the status
was rendered with, so the user sees the state change the decision
produced.

Reports are read-only here: this prompt never writes or edits a report,
and its only write surface is the decisions ledger, through
`record-finding-decision`. Never query a backend, never start the
stack.
