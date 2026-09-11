# Custom stacks

`.odd/observability-stacks/<name>/` is a stack the package does not
ship — a backend the observed repository's team queries on its own —
written as a directory: `guide.md`, with the same sections as a
built-in stack reference, and `scripts/`, the query scripts the guide
names, so the stack-agnostic skills consume it exactly like a built-in
one. Like a benchmark, it is **living source**, not a run record
(`SKILL.md`'s exception): updated in place through reviewed diffs, git
history being its memory. The rest of the contract (where the memory
lives, no secrets, the work branch and the lone commit, the reply)
applies as written there.

## Where custom stacks live

One directory per stack, `.odd/observability-stacks/<name>/`, in the
observed repository — the name is the stack's identity: it is the
`stack` value `odd_config_set` stores, the directory's name, and the
word the user says to switch to it. The single-file form an earlier
contract used (`<name>.md`) is not read and nothing converts it: a
stack written that way is recreated through `/odd-instrument-stack`.

## The directory

- **`guide.md`** is the reference, under that fixed name:
  - **its frontmatter** declares what the server must know and never
    reads from the file — the `observability-cli-guides` skill's
    `references/CONTRACT.md` fixes its shape (`stack`, the directory's
    name; `stack_config_fields`, the fields the switch may persist —
    an empty list when the stack's query surface carries its own
    targeting). A `verified` note may sit next to them: the date and
    what was exercised, per the contract's live-verification rule;
    anything else the frontmatter carries belongs to the guide alone;
  - **its body** carries the contract's mandatory sections under its
    exact headings, in any order, plus any section of the guide's own
    — or **nothing**, when the frontmatter links the guide (the
    contract's `source_url`, or `source_repo` with `source_path`): one
    guide then serves several repositories, the local directory is
    the pointer, and the fetched copy is what every consumer reads.
- **`scripts/`** holds the query scripts `## Query by signal` names,
  as the contract's shipped-script rule states them — one per shape of
  the work, a shared module for the transport, `--json`, the backend
  commands printed last — and nothing else. The query surface is
  whatever the backend answers to — a CLI, plain `curl` against an
  HTTP API, anything else — a CLI is one option, never a requirement;
  every command links to the page it comes from. A linked stack has no
  scripts of its own: they come with the link when the link is a
  repository's directory, and not at all when it is a URL.
- **No secrets, no real endpoints, amplified**: a guide filled from a
  live instance is exactly where an endpoint, a tenant or a token would
  leak. A real endpoint or identifier is a `stack_config` field the
  guide names (`stack_config.base_url`) and never a value in the guide
  or a script (a `localhost` default is an example, not a real
  endpoint); a credential is the environment variable **name** the
  command reads. On a host that runs the package's lifecycle hooks, a
  hook flags what slipped through, after the write.

## Recall

By name: a stack the user names that maps onto no row of
`builtin-stacks.md` is looked up at `.odd/observability-stacks/<name>/`
in the observed repository — present, its `guide.md` is the stack's
reference, read by section like a built-in one (the contract says who
reads which section), and its `scripts/` are what the guide's
invocations run; absent, the name is unknown, an error naming both the
built-in list and this location, never a guess. Listing the directory
is how a prompt offers the custom stacks the repository carries.

## Rules

- **Checked before it is trusted.** A switch to a custom stack runs
  `python3 <the observability-cli-guides skill's directory>/scripts/check_stack_reference.py --declaration .odd/observability-stacks/<name>`
  first: a stack that breaks the contract — a heading missing, a script
  the guide names absent or not compiling — does not get persisted, and
  neither does one the check could not run on; the fix is a change to
  the stack, through `/odd-instrument-stack`. What the check prints is
  the `odd_config_set` payload the switch passes verbatim, never
  rebuilt by hand.
- **Written by one prompt.** `/odd-instrument-stack` and the agent it
  dispatches are the only writers of a custom stack — a creation, a
  completion, a link, a fix from an observation report. Every
  invocation the guide carries is run against the backend before it is
  written as verified (the contract's live-verification rule): a
  backend the machine cannot reach stops a creation, and an
  invocation that could not be run is marked unverified with the date,
  never upgraded without a measurement.
- **Reviewed diffs, never silent overwrites.** A change to a stored
  stack — a user's instruction, a fix from a report — is presented as a
  diff against the stored version and reviewed like any other committed
  change. The persistence never rewrites a stored stack without that
  diff being visible.
- **Commit discipline** (the memory contract): the work branch is
  `docs/odd-stack-<name>`, created when the repository sits on its
  default branch — on any other branch the commit lands where the
  repository is, as the contract says for every kind; the commit
  carries the directory alone (`git add -- .odd/observability-stacks/<name>`;
  a `__pycache__` the check left is ignored, never added), subject
  `docs(odd): stack <name>` for a new stack, `docs(odd): stack <name>
  - <what changed>` for an update; the reply states the stored path.
- **A mission never edits a stack.** An observe or verify run that
  meets friction with the stack as shipped — a script that failed as
  written, an output shape the guide did not state, a flag it lacked,
  a section it could not follow, a query it had to compose by hand —
  records it in its report's `## 8. Stack friction` section (the
  `observe-run-report` reference), one bullet per point, and touches
  nothing under the directory: authoring is the stack expert's
  responsibility, and `/odd-instrument-stack from report <path>` turns
  that section into the fix, verified live and committed on the
  stack's own branch, reviewed like any other change. A friction with
  the preflight's or the switch's sections is stated the same way, for
  the same prompt.
- **A linked guide is amended where it lives.** When the stack links
  its guide, no change — a user's instruction, a friction a report
  recorded — is ever written into the local directory: a body next to
  a link forks the guide, and the check refuses it. The change goes to
  the linked guide instead: when the link is a git repository the user
  can push to (probe it — `gh repo view <repo> --json viewerPermission`
  for a GitHub remote, a dry-run push otherwise; never assumed), clone
  the repository into a scratch directory of your own — never the
  check's fetch clone, which the check deletes and re-clones on every
  run — apply the diff there on a work branch named as above, run the
  check on the amended copy as a plain path, commit it with the same
  subject, push the branch, and **propose a pull request** on that
  repository — opened only with the user's go, like any outward action;
  where no tool opens one for that remote, push the branch and say so —
  reporting the branch and the pull request in the reply; otherwise (a
  URL, a repository without write access) **display the proposed
  change** in the reply — the section or the script, the diff, the
  reason, the date — for the user to apply on the guide themselves,
  saying plainly that nothing was written anywhere.
- **Never a built-in.** A directory whose name is a `STACKS` value is
  refused at the check (the script reads `builtin-stacks.md`, and the
  server refuses the name again): a learning about a stack the package
  ships is a package issue, never a stack in the observed repository.

## What the persistence does not own

- Any backend knowledge — it persists whatever content the caller
  decided. Whether the commands and the scripts are right belongs to
  the stack expert who verified them and to the runs that exercise
  them.
- Deleting a custom stack. A directory for a backend the team no
  longer queries is stale source, removed by a human's PR like any
  other dead source — and only after `odd_config_set {"custom":
  {"<name>": null}}` has removed its declaration from the configuration
  (refused while it is the configured stack).

## Lifecycle notes

- **Not inventoried by `/odd-status`**: a custom stack is not loop
  state.
- **Visible to the verify-vs-re-measure boundary** (the memory
  contract): a commit that changes a custom stack counts as changed
  code, like a benchmark's.

## Show

A custom stack is shown after it is persisted — created, completed or
fixed — one screen, from the stored directory and the configuration,
never from the conversation's memory of the mission. A switch to one
ends in `backend-configuration`'s preflight handoff instead, like any
switch.

### What to render

- **Stored path** — `.odd/observability-stacks/<name>/`, with its
  carrying commit, or `not committed` with the reason; for a linked
  guide, the link too, and the amendment's branch and commit on the
  linked repository when one was made (or "displayed, nothing
  written").
- **Query surface** — the binary or the transport the `## CLI binary`
  section names, one line.
- **Scripts** — the files under `scripts/`, one line, each with the
  shape of the work it ships (discover, logs, traces, ...), and
  `none (linked by URL)` for a guide linked that way.
- **Declared fields** — the `stack_config_fields` of the frontmatter,
  and for each whether the configuration holds a value (the field name
  and "set" or "not set" — never the value).
- **Verification state** — the `verified` note, or "unverified" when
  the frontmatter carries none, and the count of invocations the guide
  marks unverified.
- **For an update**: a short headline of what changed — the diff lives
  in the commit; for a fix from a report, the report's path and how
  many of its friction entries the fix closed.

### What the synthesis reads

The stored guide's frontmatter and `## CLI binary` section, the
listing of `scripts/`, and `odd_config_get` for which declared fields
hold a value — never a value, never a backend query.
