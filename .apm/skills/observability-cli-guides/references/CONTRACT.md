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
  documentation, linked from the section that uses it.

## A custom stack file

A custom stack file (a backend the package does not ship, kept in the
observed repository as `.odd/observability-stacks/<name>.md` — the
`odd-memory` skill's `observability-stack` reference owns its
lifecycle) follows the same contract, so the stack-agnostic skills need
no special case for it. It differs from a built-in reference in one
place: it opens with a frontmatter that declares what the server must
know and never reads from the file —

```yaml
---
stack: <name>              # kebab-case, the file's own stem, never a built-in value
stack_config_fields: []    # the stack_config fields the switch may persist; [] when none
---
```

The switch runs
`python3 <this skill's directory>/scripts/check_stack_reference.py --declaration <file>`:
the headings are checked as for a built-in, the name is refused when
`builtin-stacks.md` lists it, and the declaration is printed
as the `odd_config_set` payload that switches to the stack — the
tool's `config` argument, passed verbatim. Any other frontmatter key
(a `verified` note, for instance) belongs to the file and is never
forwarded.
