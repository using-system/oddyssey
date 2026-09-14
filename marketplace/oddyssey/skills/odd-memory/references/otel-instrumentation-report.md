# Instrumentation reports

An instrumentation investigation that vanishes with the conversation must
be redone from scratch the next time the stack changes. This reference
defines the file contract that persists it: reports live **in the
investigated repository**, so git versions them, PRs review them, and
every user of the repo shares them — the next SDD instrumentation wave
starts from what the last investigation already established. What every
kind of memory shares is the contract in `SKILL.md`; this reference states
what is specific to instrumentation reports: the script that owns the
format, what each section carries (`## The body`, read at report time),
how to recall the baseline, and how a stored one is shown.

## The script owns the format

`python3 <this skill's directory>/scripts/odd_report.py` — one script for
both report kinds — fixes what the inputs fix: the path and its stamp,
the frontmatter, the section skeleton, the checks, the work branch, the
lone commit, the synthesis. Every invocation below is the whole flag
surface: `--help` has nothing to add.

```bash
python3 <this skill's directory>/scripts/odd_report.py new --kind instrumentation --repo <path in the investigated repository> --project <scope> --stack <stack> --run-name <slug> [--genai <service>]... [--repository <origin, normalized>] [--at <YYYY-MM-DDTHH:MM:SSZ>] [--no-revision]
python3 <this skill's directory>/scripts/odd_report.py persist <path> --body <draft> [--no-commit]
python3 <this skill's directory>/scripts/odd_report.py check <path>
python3 <this skill's directory>/scripts/odd_report.py read <path> [--sections 1,2,4,5]
python3 <this skill's directory>/scripts/odd_report.py show <path>
python3 <this skill's directory>/scripts/odd_report.py synthesis <path>
```

- `new --kind instrumentation` names the file
  `.odd/otel-instrumentation-reports/YYYY-MM-DD-HHmm-<run_name>.md` (UTC
  now, or `--at`; a taken name gets the next free ordinal, said on
  stderr), writes the frontmatter from the repository — `project` (the
  repository, or a path in it), `stack` (the export stack the plan
  targets), `run_name`, `date`, and from git `revision`, `tree_anchor`
  (the top-level `git ls-tree` map, the squash-proof anchor) and
  `repository` (the `origin` remote normalized: host lower-cased then
  the path, scheme, user, port, a trailing `/` and `.git` dropped, the
  SSH form read as `host/owner/name`; a token in the remote never
  reaches the file; no remote, no value — `--repository` stands in
  for it, never a local path; `--no-revision` when the code is in no
  repository the run can reach) — and prints the path, then the body
  skeleton: the title, a `<fill>` for the one-line headline, the five
  numbered headings, section 2 opening with the summary table's header
  row and an `Implementation order:` line, section 3 carrying one
  `### GenAI approach — <service>` heading per `--genai` service (one
  per service the investigation found calling a model), section 5
  opening with
  the checks' header row — and, after the skeleton, one line naming
  what `persist` checks the draft for, so the run reads neither this
  file nor the script to learn the shapes. Every `<fill>` is the run's
  to replace: the sections are the judgment — written, filled, to a
  **draft** file of the run's own with its file tool, never by editing
  the report file.
- `check` runs the memory contract's checks — what a host's hook
  enforces after a write, the title and the one-line headline before
  section 1, the five sections in order, no placeholder left, and the
  shapes of `## The body` below: the summary table's columns, `Service`
  first, with one row at least, and the `Implementation order:` line;
  section 5's checks in the replayable
  form; no credential in a check (a key, token, password or
  connection-string value, a `--query` projecting a credential field —
  an env var name, a secret reference or a placeholder in that slot is
  wiring, and passes); the GenAI approach as prose (a section 3 table
  whose first column names it is refused). One stderr line per
  problem, exit 2; `persist` refuses a report that fails it.
- `read` prints the frontmatter and the named sections, nothing else
  (default 1, 2, 4 and 5 on this kind).
- `persist --body <draft>` writes the draft under the file's
  frontmatter (a frontmatter the draft carries is dropped), runs
  `check` — a failing draft leaves the file as `new` wrote it and
  names what the draft lacks; nothing committed — leaves the default
  branch for `docs/odd-instrumentation-report-<run_name>`, commits the
  file alone (`docs(odd): instrumentation investigation <run_name>`),
  and prints the return value (`## Return value` below). `--no-commit`
  when the caller said not to; outside a repository it says
  `not committed` and why.
- `synthesis` prints the synthesis block quoted from the stored file;
  `show` renders the closing synthesis from it (`## Show` below).

## The body

Five sections, numbered, under these headings, read by number — the
agent's contract, stated here once and read at report time:

1. **Stack inventory** — per service: language + version, frameworks,
   entry point, how it starts, where it runs, existing telemetry.
   Evidence: file paths. Open with the recalled baseline: the previous
   report's path and what changed since it, or "no previous report".
2. **Summary table** — the whole plan at a glance, one row per service,
   under the header row `new` wrote:

   | Service | Language + version | Runtime shape | Approach | Signals (maturity) | Key packages (pinned) | OTLP endpoint | Effort (S/M/L) | Risk flags |

   The pinned packages ARE what the implementation wave will add.
   Follow it with the recommended **implementation order** across
   services on the `Implementation order:` line — edge services first,
   so context propagation is testable as the plan moves inward.
3. **Decisions made, with rationale — per service** — the recommended
   approach (zero-code / libraries / manual) with the exact packages and
   setup steps sourced from the official docs, the doc links used (so
   the main agent can re-read them during implementation), the signals
   to enable and in what order, where the instrumentation is applied
   (image / startup / environment), and the `OTEL_*` configuration
   block: service name, resource attributes, the OTLP endpoint reachable
   from where that service runs, and the OTLP protocol — `grpc` on
   `:4317` or `http/protobuf` on `:4318` — matching the exporter package
   recommended. Every entry carries its rationale; nothing here is an
   unlabeled default. For a service the investigation found calling a
   model, a **GenAI approach** under its `### GenAI approach — <service>`
   heading — prose, never a table, since a table row in section 3 reads
   as a finding to the status renderer (`check` refuses a section 3
   table whose first column names it): the
   instrumentation library the plan adopts — the row of the
   `otel-guides` skill's generative AI reference it comes from, pinned
   and doc-linked like every package — what it emits (the `gen_ai.*`
   spans, the token and duration metrics), what stays hand-coded
   because no library covers it (cost, the agent loop), and the
   content-capture switch that library exposes with the direction the
   plan sets it — the convention's default records nothing, and two
   libraries the reference names record content by default, so the
   switch is named here even when the plan leaves the default alone.
4. **Decisions the spec must settle** — one numbered or bulleted item
   each: sampling strategy; **Collector topology**: direct OTLP export
   vs an OpenTelemetry Collector (agent / sidecar vs central gateway —
   see the `otel-guides` skill's Collector reference for the documented
   patterns), with rationale — for the local oddyssey stack direct
   export is the default (otel-lgtm embeds a collector), and for a
   remote backend state which Collector features (tail sampling,
   redaction, retry buffering) would justify one; migration vs
   coexistence with any vendor agent found; context propagation across
   the discovered boundaries; log correlation; naming conventions for
   services and custom spans/metrics; what NOT to instrument. Anything
   decided belongs in section 3 with its rationale — anything not
   decided belongs here, stated as an open question.

   For a service that calls a model, two more:
   - **content capture** — whether prompts and completions go into the
     telemetry: a privacy and volume decision the user takes, off by
     default per the convention. Ask it as *which switch, in which
     direction* for the library the plan picked — the generative AI
     reference names each library's switch and which libraries invert
     the default — and, when on, where the content lands (span
     attributes, events, or references to external storage); never a
     bare yes/no whose default differs by library.
   - **cost attribution** — no convention attribute exists for it:
     whether cost is derived from the token usage and a price per model
     kept outside the repository, recorded under an application
     namespace, or not attributed at all — and who owns the price
     table.
5. **Verification protocol** — how to prove instrumentation works once
   implemented: start the export stack — `odd_stack_up` for the local
   one; for a remote stack, name the backend and the preflight it
   needs — then run each service with its `OTEL_*` block, exercise one
   scenario, and confirm each signal arrives. Every query the protocol
   states comes from the export stack's reference in the
   `observability-cli-guides` skill, never from memory — the local
   reference routes to the query sections of the backend reference it
   is built on; a custom stack's reference is
   `.odd/observability-stacks/<name>/guide.md` in the observed
   repository, with the scripts it names under `scripts/` beside it,
   and a documented command the form check finds wrong is stated in
   section 5 next to the protocol as friction with the stack, for
   `/odd-instrument-stack` to fix — never a diff of the run's
   (`odd-memory`'s `observability-stack` reference: a mission never
   edits a stack) — and when a query's **form** is checked against
   data the stack already holds (an adjacent service's series; the
   planned signals do not exist yet, and the run never starts the
   stack for it), it goes through the `setup-local-stack` skill's
   isolated CLI context (its `## Configure an isolated context`,
   `## Datasources` and `## This stack is push-based` sections), never
   through a datasource's raw HTTP API: a raw endpoint answers 404 or
   demands what the CLI supplies. Every `--from`, `--to` and report
   timestamp is computed with `date -u`: a session crossing local
   midnight while UTC has not rejects the query ("start time is after
   end time") and misdates the report. Every check is stated in the
   **replayable form** `check` reads — the table `new` opened, one row
   per planned item (spans searchable per service, each planned metric
   present, logs carrying trace IDs, resource attributes set):

   | Check | Query | Expected outcome | Attribution evidence |

   — the discovery query to run, its expected outcome, **and the
   attribution evidence**: the identity the check filters on
   (`service.instance.id` set through `OTEL_RESOURCE_ATTRIBUTES` for
   traces, metrics and logs; for profiles, a per-run tag mirroring it,
   where the stack's reference says SDK-pushed profiles carry no
   instance identity, plus the application frames the flamegraph must
   show — as **anchored** frame names read off the emitting process's
   own flamegraph, never a module-path regex, since frame naming is the
   profiler's own — `Class.method` or a bare name, never a module path
   — and `urlopen`-style names are shared with helper code) — so a
   later `/odd-verify` run can rule **closed / present, unattributed /
   still missing** on each item without interpreting prose (the
   `observe-run` agent does the confirmation). A check satisfiable by
   any process sharing the service name — a healthcheck inheriting the
   profiler env, a co-resident instance — is not replayable evidence.
   Nor is a check that can never match: a Collector health check on a
   component the plan introduces (an exporter, a processor, a receiver)
   names the component by its **configured component id** —
   `<type>/<name>` as it will stand in the Collector configuration the
   plan changes, `azure_monitor/app-insights`, never a package or type
   name the implementation may not use (`azuremonitorexporter` is a Go
   package; a literal grep for it matches nothing on a broken exporter
   too) — and says the replay reads that id from the configuration
   file at replay time and proves the grep can match (the component's
   startup line, a known error line) before "zero error lines" closes
   anything. Plan the per-run tag in section 3's configuration block so
   the verify can set it. **A check never projects a credential**
   (`check` refuses one). Its query and its expected outcome name no
   connection string, instrumentation or API key, token, password or
   auth-header value (a header sourced from an environment variable by
   name is wiring, and stays) — not through a `--query` projection, not
   by dumping a whole resource object that carries one (a backend's
   `show` command routinely does; the reference says which fields are
   credentials). The protocol is replayed verbatim by `/odd-verify` and
   its result is quoted into a committed report, so a projected
   credential is a leak deferred to the first replay. A check that must
   prove a secret is wired proves the **wiring**: the secret reference
   or env var name the configuration points at, a non-empty or redacted
   flag the backend exposes (stated in prose, never as a `--query`
   naming the credential field), the resource identity the secret binds to
   (a workspace id, an ingestion mode) — never the value; and a
   resource identity that carries a real subscription, resource group,
   workspace or account name — or any value persisted under a remote
   stack's `stack_config`, regions excepted — goes into the report as
   an obviously fake placeholder (for a `stack_config` value, the
   field's name in angle brackets, `<log_group>`), never the real one.

The frontmatter exists so future runs can filter reports **without
parsing prose**; the body is the agent's judgment as-is, whole — the
persistence adds nothing beyond the headings and the few shapes above,
and a summary cannot feed a later diff.

## Recall: reading the memory

Before a new investigation, load what is already known, per the
memory contract's recall (the script first, newest first, the baseline
by section; frontmatter only, by hand, when the script cannot run) —
the matching rules are this reference's:

1. Run the recall script in the investigated repo:
   `python3 <this skill's directory>/scripts/odd_recall.py --repo
   <path> --kind instrumentation --project <scope> [--stack <stack>]`
   — it lists `.odd/otel-instrumentation-reports/` newest first and
   prints the matches by the rule below, one tab-separated line each,
   the same ten columns as an observation's with `project` in the
   third and `-` in the observation-only ones.
2. A report matches when its `project` covers the mission's scope
   (equal to it, or a parent path of it) and its `stack` is the
   mission's when one is named.
3. The first match — the first line printed — is the baseline: its
   stack inventory, per-service decisions (their GenAI approach with
   them, when a service carries one) and pinned versions are the
   sections the new investigation diffs against (new services, changed
   frameworks, moved pins, a model SDK added or dropped) —
   `read <path> --sections 1,2,3` prints them. What the comparison
   must report belongs to the calling agent's contract, not to this
   reference.

## Rules

- **No real identifiers** (the memory contract) — a live CLI excerpt
  (a component's `show` output, a resource id) is the likeliest source:
  a subscription, workspace, account or resource-group name, or a value
  persisted under a remote stack's `stack_config`, regions excepted,
  goes in as an obviously fake placeholder (the field's name in angle
  brackets). The credential half of the rule — a check never projects
  one — is section 5's in `## The body`, and `check` enforces it.
- **The work branch and the lone commit** (the memory contract) are
  `persist`'s: `docs/odd-instrumentation-report-<run_name>`, the
  report file alone, `docs(odd): instrumentation investigation
  <run_name>`.

## Return value

`persist` prints it: `path:`, `commit:` (or `not committed` with the
reason), `headline:`, plus `branch:` and `subject:` when it committed.
The reply carries those lines verbatim — and nothing of the body: the
synthesis is rendered once, by the caller's `show`, and the next wave
reads the file at the stored path. `synthesis <path>` prints the inputs
`show` renders from, quoted from the file, for a reader who wants them
rather than the rendering.

## Show

The stored report is the input the spec-driven instrumentation plan is
built from — the right artifact for the next wave, the wrong one for
the human closing the mission: several screens of tables, env blocks,
and doc links bury the takeaways. `show <path>` renders the closing
synthesis from the stored file, by section, never from the
conversation's memory of the mission; the report file stays the
deliverable.

What it renders, in order: the **headline** — one bold line answering
"what will happen": services covered, dominant approach, pinned
package count (the summary table's package entries carrying a
version), open decisions (`2 services, zero-code approach, 7 pinned
packages, 3 decisions open`), the GenAI approach when a service
carries one, the baseline when one was recalled; **where it lives** —
the stored path and the commit that carries it, then `project`,
`stack`, `revision`, `repository` and the baseline; **the plan at a
glance** — the summary table trimmed to its service, approach, pinned
packages, effort and risk columns (the widest, endpoint and signals,
dropped first), rows beyond ten behind `+N more in the report`, and
the implementation order; the GenAI approach's services; **the
decisions the spec must settle** — the count, then one line each;
**the verification protocol** — how many replayable checks section 5
carries; and the **next action** — settle the open decisions, then
build the spec-driven plan, or build it now. The contract's synthesis
rules apply: one screen, the conversation's language, the file's path
stated, never the raw report re-inlined.
