# The reference contract

Every stack file in this directory — one per backend, `builtin-stacks.md`
and this file excepted — carries the sections below, under these exact
headings. The consumers find a section by its heading and read nothing
else: the preflight reads three (`## CLI binary`, `## Setup`,
`## Configuration display`), the switch two (`## CLI binary`,
`## What to persist`) — the four the agents never open — and the
agents the rest. A section under another name is a section nobody
reads. This skill's `scripts/check_stack_reference.py` enforces the
list from the block below — in CI on the built-in references, and at
switch time on a custom stack file; the block is the list.

```text
## CLI binary
## Setup
## Query by signal
## Planning notes
## Configuration display
### Display
### Connection proof
### Change-request phrasing
## What to persist
### What stack_config holds
### Where each value comes from
### What to ask the user
```

Order is free — a file may put the configuration sections before the
query surface, as `local.md` does — and a file may add sections of its
own between them (a remote-targeting section, a resource-discovery
section, an output-reading section): an optional section is read by the
agents like any other, never by the preflight or the switch.

## What each section answers, and who reads it

- **`## CLI binary`** — which binary the stack is queried with, how to
  detect it and how to install it. Read by the preflight and the switch;
  never by the agents (the preflight handoff carries the answer).
- **`## Setup`** — how the CLI authenticates and targets an instance,
  never doing it for the user. Read by the preflight only.
- **`## Query by signal`** — the discovery-then-query commands per
  signal the backend carries (metrics, traces, logs, profiles — a signal
  the backend cannot serve says so), the output shapes and their traps,
  and whether the CLI is safe to run concurrently from one shell
  (verified, or marked not verified). Read by the agents only; it may
  route to another file's section, as `local.md` routes to `grafana.md`.
- **`## Planning notes`** — the backend's coverage gaps, quirks and
  verification dates a mission plans around. Read by the agents only.
- **`## Configuration display`** — read by the preflight only:
  - **`### Display`**: the commands that show the effective
    configuration, which fields to show, which to never echo;
  - **`### Connection proof`**: the one cheapest call whose success means
    "connected", and what its failure means;
  - **`### Change-request phrasing`**: the phrasings a user may use to ask
    for a switch to this stack.
- **`## What to persist`** — read by the switch only:
  - **`### What stack_config holds`**: the field list the switch persists
    for this stack (never a credential);
  - **`### Where each value comes from`**: the command or console path
    that yields each field;
  - **`### What to ask the user`**: what the switch asks when a field
    cannot be derived.

## The rules every section obeys

- **Verified live, non-negotiable** (AGENTS.md): a changed CLI command,
  flag, prerequisite or `stack_config` field is exercised against a real
  account carrying real data before it lands; a note the file could not
  verify says so, with the date, and is never upgraded without a
  measurement.
- **One backend per file**: a reference talks about its own backend
  only, never a comparison with another one; routing to the local stack
  is not a comparison.
- **No secrets, no real identifiers**: placeholders only, and the
  `### Display` section names what must never be echoed.
- **Linked, not remembered**: every command traces to the backend's
  documentation, linked from the section that uses it — the checker
  refuses a `## Query by signal` that links nothing (a section routing
  to another file links that file).

## A custom stack

A custom stack (a backend the package does not ship, kept in the
observed repository as a **directory**, `.odd/observability-stacks/<name>/`
— the `odd-memory` skill's `observability-stack` reference owns its
lifecycle) follows the same contract, so the stack-agnostic skills
need no special case for it. The directory holds two things:

```text
.odd/observability-stacks/<name>/
  guide.md          # the reference: frontmatter + the sections above
  scripts/          # the query scripts guide.md names, one per shape of the work
```

`guide.md` is the fixed name; it differs from a built-in reference in
one place: it opens with a frontmatter that declares what the server
must know and never reads from the file —

```yaml
---
stack: <name>              # kebab-case, the directory's own name, never a built-in value
stack_config_fields: []    # the stack_config fields the switch may persist - [base_url], or [] when none
---
```

**The scripts follow what the package did for its own stacks**: this
skill's `scripts/grafana-*.py` and their shared `grafana_gcx.py` are
the model. Standard library only; generic through their inputs
(service names, a window, a selector) — never a value of one
instance; one shared module for the CLI or the HTTP transport, which
absorbs the surface's traps once; one script per shape of the work —
discovery, then one per signal the backend serves, plus a context or
a landing proof where the backend needs one; `--json` on each; each
ending its output with the backend commands it ran, one per line, the
way an observation report records a shipped query — the binary by its
name, the way the guide's `## CLI binary` section names it, whatever
path the module resolved it at. `scripts/` holds `.py` files and
nothing else (a `__pycache__` the check leaves behind is ignored, not
shipped). `## Query by signal` names each script with its **whole flag surface** and a
copy-pasteable invocation run from the observed repository's root
(`python3 .odd/observability-stacks/<name>/scripts/<name>-logs.py ...`),
and states the output shapes, so no run reads a script's source; the
residual traps for a call still composed by hand stay as bullets — a
list, never an essay.

**Verified live at construction**: every invocation the guide carries
was run against the backend, answering from the machine the stack was
built on, before it was written as verified — the `verified` note and
the dated marks in `## Query by signal` are the record; an invocation
that could not be run is marked unverified with the date. No test
suite lands in the observed repository and none runs in this package's
CI for a custom stack (the package cannot test a script it does not
ship); the checker verifies the shape.

The switch runs
`python3 <this skill's directory>/scripts/check_stack_reference.py --declaration .odd/observability-stacks/<name>`:
the guide's headings are checked as for a built-in, the name is refused
when `builtin-stacks.md` lists it, every script `## Query by signal`
names as `scripts/<file>.py` must exist under `scripts/` and compile
(and so must every other `.py` there), and the declaration is printed
as the `odd_config_set` payload that switches to the stack — the tool's
`config` argument, passed verbatim. Any other frontmatter key (a
`verified` note, for instance) belongs to the guide and is never
forwarded. A guide file on its own — a copy an agent fetched somewhere
— is checked the same way as a plain path.

A custom stack may **link** its guide instead of carrying it, so one
guide serves several repositories: `guide.md` then carries the
frontmatter only, naming the guide — `source_url: <URL the guide is
fetched from as-is>`, which brings the guide alone (no scripts, and
the guide must name none); or `source_repo: <git repository the user
can clone>` with `source_path: <the stack's directory in it>` and an
optional `source_ref: <branch or tag>`, which brings the directory
whole, scripts included (a `source_path` naming a file brings that
guide alone) — and the body stays empty (a body next to a link is
refused: it would fork the guide silently). The check then fetches the
stack into `--fetch-dir <dir>` as `<dir>/<name>/` (`guide.md`, and
`scripts/` when the link carries them), checks that copy's headings
and scripts, and prints the same payload; the copy is what the skills
read, never committed. The linked guide may itself be a full custom
stack guide of the other repository, frontmatter included. A guide
reachable some other way is fetched by the agent into that directory
and checked as a plain path.
