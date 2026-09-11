# Custom backends

Every backend the package ships is listed in
[backends.md](backends.md). Any other observability backend — Seq,
SigNoz, Uptrace, Elastic APM, a homegrown Kibana — becomes a **custom
stack**: a directory in your repository,
`.odd/observability-stacks/<name>/`, holding `guide.md` — the same
sections as a built-in backend's reference — and `scripts/`, the
query scripts the guide names, so a run against it composes nothing.
`/odd-instrument-stack` writes it, verified live against your backend,
and your runs' reports say where it rubs. This page says how to create
it, edit it, fix it from a report, and share it across repositories.
The contracts are the `odd-memory` skill's
[observability-stack.md](../../.apm/skills/odd-memory/references/observability-stack.md)
and the `observability-cli-guides` skill's
[reference contract](../../.apm/skills/observability-cli-guides/references/CONTRACT.md);
on any divergence, they win.

## Create

```text
/odd-instrument-stack create a stack seq
/odd-instrument-stack create a stack seq from https://datalust.co/docs/command-line-client
/odd-instrument-stack create a stack seq from ./docs/seq/ : query it with seqcli, the connection is set with seqcli config, no profiling
```

Name the backend; add the documentation to read first — a URL or a
local path — and your own instructions after a colon when you already
know how the backend is queried (your word wins over the
documentation where they disagree). The prompt asks you once what
only you can answer — how the backend is reached from your machine,
by name, never a value — then dispatches the stack expert, which
researches the rest, writes the guide with every command linked to
the page it came from, writes the scripts the guide names, and runs
every invocation against the backend before writing it as verified.
**The backend must answer from your machine**: a creation stops when
it does not, and an invocation that could not be run is marked
unverified with the date. A name the package ships (`grafana`,
`datadog`, ...) is refused here: those change through the package.

What comes out: `.odd/observability-stacks/<name>/` — `guide.md` and
`scripts/` — committed on a work branch (`docs/odd-stack-<name>`) for
you to review like code, a one-screen synthesis (where it lives, the
query surface, the scripts, the fields it declares, what is verified),
and the offer to switch to it. The switch checks the stack against
the contract first — headings, and every script the guide names
present and compiling — and ends in the connection proof.

## Edit

The stack is source: edit it in a branch and review it like code, or
dictate the change:

```text
/odd-instrument-stack for stack seq: the traces endpoint is /api/traces, it takes a service query parameter
```

The instruction becomes a diff to the sections and the scripts it
touches, verified live and shown to you before it is committed. An
instruction never marks a command verified on its own — the expert's
run does. To check a stack by hand, run the switch's check from your
repository's root:

```text
python3 <the observability-cli-guides skill's directory>/scripts/check_stack_reference.py --declaration .odd/observability-stacks/seq
```

It lists the headings the guide lacks and the named scripts it cannot
find or compile, or prints the declaration the switch stores; a stack
that fails it is never switched to.

## What a run teaches the stack

An observe or verify run against the custom stack never edits it. Its
report carries an eighth section, **Stack friction**: one bullet per
point where the stack as shipped did not carry the run — a script
that failed as written, an output shape the guide did not state, a
flag it lacked, a query the run had to compose by hand — with the
invocation, what it answered and what the run did instead; the
closing synthesis shows the count. Then:

```text
/odd-instrument-stack from report .odd/observe-run-reports/2026-09-11-0710-roastery-web-frontend-seq.md
```

turns that section into the fix — each bullet verified live, the diff
shown, committed on the stack's own branch for you to review like any
other change. The observing and the authoring stay two
responsibilities: a run reports, the expert fixes.

## Link a guide another repository carries

One guide can serve a whole team: the directory in your repository
then only points at it —

```text
/odd-instrument-stack create a stack seq linked to https://github.com/example-org/obs-guides stacks/seq
```

— and carries no body and no scripts of its own. The switch fetches
the linked stack (a repository's directory brings the guide and its
scripts; a bare URL brings the guide alone, which then names no
script), checks it, and reads the copy; the directory in your
repository never changes. A change — your instruction, a fix from a
report — goes to the linked repository as a pull request when you can
push there (opened only with your go), or is shown to you to apply
there yourself when you cannot.

## Try it

This repository carries a throwaway [Seq](https://datalust.co/seq) and
a custom stack for it, written from Seq's documentation and verified
with `seqcli`:

```text
docker compose -f docker-compose/seq/docker-compose.yml up -d
dotnet tool install --global seqcli
/odd-config switch to seq
```

The connection proof shows `"status":"healthy"` from
`seqcli node health --json`, and a `/odd-observe` against the sample
data Seq ships (`seqcli sample ingest --confirm`, stopped after a
minute) runs the stack's scripts for logs and traces.
`docker compose -f docker-compose/seq/docker-compose.yml down -v`
removes the instance and its data.
