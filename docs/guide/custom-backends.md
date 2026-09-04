# Custom backends

Every backend the package ships is listed in
[backends.md](backends.md). Any other observability backend — Seq,
SigNoz, Uptrace, Elastic APM, a homegrown Kibana — becomes a **custom
stack**: one file in your repository,
`.odd/observability-stacks/<name>.md`, with the same sections as a
built-in backend's reference, that `/odd-config` writes for you and
your runs improve. This page says how to create it, edit it, let the
runs amend it, and share it across repositories. The contracts are the
`odd-memory` skill's
[observability-stack.md](../../.apm/skills/odd-memory/references/observability-stack.md)
and the `observability-cli-guides` skill's
[reference contract](../../.apm/skills/observability-cli-guides/references/CONTRACT.md);
on any divergence, they win.

## Create

```text
/odd-config create a stack seq
/odd-config create a stack seq from https://datalust.co/docs/command-line-client
/odd-config create a stack seq from ./docs/seq/ : query it with seqcli, the connection is set with seqcli config, no profiling
```

Name the backend; add the documentation to read first — a URL or a
local path — and your own instructions after a colon when you already
know how the backend is queried (your word wins over the
documentation where they disagree). The prompt researches the rest on
the web, writes the file with every command linked to the page it
came from, runs each command against the backend when it answers from
your machine, and asks you once for what nothing settled — the
instance's address, the name of the credential — by name, never a
value. A name the package ships (`grafana`, `datadog`, ...) is refused
here: those change through the package. A backend the package used to
ship is recreated the same way (`/odd-config create a stack splunk`);
its former reference is in the package's git history.

What comes out: `.odd/observability-stacks/<name>.md`, committed on a
work branch (`docs/odd-stack-<name>`) for you to review like code, a
one-screen synthesis (where it lives, the query surface, the fields it
declares, what is verified), and the offer to switch to it. The switch
checks the file against the contract first and ends in the connection
proof — the file's first real verification.

## Edit

The file is source: edit it in a branch and review it like code, or
dictate the change:

```text
/odd-config for stack seq: the traces endpoint is /api/traces, it takes a service query parameter
```

The instruction becomes a diff to the section it touches, shown to you
before it is committed. An instruction never marks a command verified
on its own — a run does. To check a file by hand, run the switch's
check from your repository's root:

```text
python3 <the observability-cli-guides skill's directory>/scripts/check_stack_reference.py --declaration .odd/observability-stacks/seq.md
```

It lists the headings the file lacks, or prints the declaration the
switch stores; a file that fails it is never switched to.

## What a run teaches the file

An observe or verify run against the custom stack corrects the file's
query commands when one fails as written, returns another shape, or
needs a flag the file did not carry, and dates the notes it could
verify. The correction lands as a commit of its own on the run's
branch, named in the report's run record and in the closing synthesis
("the stack file changed", with the reason) — review it like any other
commit. What a run cannot change — how the configuration is displayed,
what the switch persists — it tells you instead, for you to apply with
`for stack <name>: ...`.

## Link a guide another repository carries

One guide can serve a whole team: the file in your repository then
only points at it —

```text
/odd-config create a stack seq linked to https://github.com/example-org/obs-guides stacks/seq.md
```

— and carries no body of its own. The switch fetches the guide,
checks it, and reads the copy; the file in your repository never
changes. A change — your instruction, a run's learning — goes to the
linked repository as a pull request when you can push there (opened
only with your go), or is shown to you to apply there yourself when
you cannot.

## Try it

This repository carries a throwaway [Seq](https://datalust.co/seq) and
a custom stack file for it, written from Seq's documentation and
verified with `seqcli`:

```text
docker compose -f docker-compose/seq/docker-compose.yml up -d
dotnet tool install --global seqcli
/odd-config switch to seq
```

The connection proof shows `"status":"healthy"` from
`seqcli node health --json`, and a `/odd-observe` against the sample
data Seq ships (`seqcli sample ingest`, stopped after a minute)
exercises the file's logs and traces commands.
`docker compose -f docker-compose/seq/docker-compose.yml down -v`
removes the instance and its data.
