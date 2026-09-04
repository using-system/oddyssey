# Custom stack files

`.odd/observability-stacks/<name>.md` is a stack the package does not
ship — a backend the observed repository's team queries on its own —
written as one file with the same sections as a built-in stack
reference, so the stack-agnostic skills consume it exactly like a
built-in one. Like a benchmark, it is **living source**, not a run
record (`SKILL.md`'s exception): updated in place through reviewed
diffs, git history being its memory. The rest of the contract (where
the memory lives, no secrets, the work branch and the lone commit, the
reply) applies as written there.

## Where custom stacks live

One file per stack, `.odd/observability-stacks/<name>.md`, in the
observed repository — the name is the stack's identity: it is the
`stack` value `odd_config_set` stores, the file's stem, and the word
the user says to switch to it.

## The file

- **The frontmatter** declares what the server must know and never
  reads from the file — the `observability-cli-guides` skill's
  `references/CONTRACT.md` fixes its shape (`stack`, the file's stem;
  `stack_config_fields`, the fields the switch may persist — an empty
  list when the stack's query surface carries its own targeting). A
  `verified` note may sit next to them: the date and what was
  exercised, per the contract's live-verification rule; anything else
  the frontmatter carries belongs to the file alone.
- **The body** carries the contract's mandatory sections under its
  exact headings, in any order, plus any section of the file's own.
  The query surface is whatever the backend answers to — a CLI, plain
  `curl` against an HTTP API, anything else — a CLI is one option,
  never a requirement; every command links to the page it comes from.
- **No secrets, no real endpoints, amplified**: a file filled from a
  live instance is exactly where an endpoint, a tenant or a token would
  leak. A real endpoint or identifier is a `stack_config` field the
  file names (`stack_config.base_url`) and never a value in the file; a
  credential is the environment variable **name** the command reads.
  On a host that runs the package's lifecycle hooks, a hook flags what
  slipped through, after the write.

## Recall

By name: a stack the user names that maps onto no row of
`builtin-stacks.md` is looked up at `.odd/observability-stacks/<name>.md`
in the observed repository — present, it is the stack's reference file,
read by section like a built-in one (the contract says who reads which
section); absent, the name is unknown, an error naming both the
built-in list and this location, never a guess. Listing the directory
is how a prompt offers the custom stacks the repository carries.

## Rules

- **Checked before it is trusted.** A switch to a custom stack runs
  `python3 <the observability-cli-guides skill's directory>/scripts/check_stack_reference.py --declaration .odd/observability-stacks/<name>.md`
  first: a file that breaks the contract does not get persisted — the
  fix is an edit to the file, through this reference — and neither
  does one the check could not run on. What the check prints is the
  `odd_config_set` payload the switch passes verbatim, never rebuilt by
  hand.
- **Reviewed diffs, never silent overwrites.** A change to a stored
  file — a user's instruction, a run's learning — is presented as a
  diff against the stored version and reviewed like any other committed
  change. The persistence never rewrites a stored file without that
  diff being visible.
- **Commit discipline** (the memory contract): the work branch is
  `docs/odd-stack-<name>`; the commit carries the file alone, subject
  `docs(odd): stack <name>` for a new file, `docs(odd): stack <name> -
  <what changed>` for an update; the reply states the stored path.
- **Never a built-in.** A file whose name is a `STACKS` value is
  refused at the check (the script reads `builtin-stacks.md`, and the
  server refuses the name again): a learning about a stack the package
  ships is a package issue, never a file in the observed repository.

## What the persistence does not own

- Any backend knowledge — it persists whatever content the caller
  decided. Whether the commands are right belongs to whoever wrote
  them and to the runs that exercise them.
- Deleting a custom stack. A file for a backend the team no longer
  queries is stale source, removed by a human's PR like any other dead
  source file — and only after `odd_config_set {"custom": {"<name>":
  null}}` has removed its declaration from the configuration (refused
  while it is the configured stack).

## Lifecycle notes

- **Not inventoried by `/odd-status`**: a custom stack file is not loop
  state.
- **Visible to the verify-vs-re-measure boundary** (the memory
  contract): a commit that changes a custom stack file counts as
  changed code, like a benchmark's.

## Show

A custom stack is shown after it is persisted — created or updated —
one screen, from the stored file and the configuration, never from the
conversation's memory of the mission. A switch to one ends in
`backend-configuration`'s preflight handoff instead, like any switch.

### What to render

- **Stored path** — `.odd/observability-stacks/<name>.md`, with its
  carrying commit, or `not committed` with the reason.
- **Query surface** — the binary or the transport the `## CLI binary`
  section names, one line.
- **Declared fields** — the `stack_config_fields` of the frontmatter,
  and for each whether the configuration holds a value (the field name
  and "set" or "not set" — never the value).
- **Verification state** — the `verified` note, or "unverified" when
  the frontmatter carries none.
- **For an update**: a short headline of what changed — the diff lives
  in the commit.

### What the synthesis reads

The stored file's frontmatter and `## CLI binary` section, and
`odd_config_get` for which declared fields hold a value — never the
file's other sections, never a value, never a backend query.
