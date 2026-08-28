# AGENTS.md

## Marketplace is generated — never edit it by hand

`marketplace/` is a build artifact: the release workflow regenerates it
from `.apm/` via `scripts/build-marketplace.sh`. Author every change in
`.apm/` (agents, skills, prompts) only, and leave `marketplace/` alone.

## Keep the prompts guide in sync

`docs/guide/prompts.md` catalogs the packaged prompts with example
invocations. Update it in the same change whenever a prompt is added or
removed, or a prompt's behavior/arguments change — examples and
field-mapping annotations must keep matching the `.apm/prompts/`
contracts. Update the `README.md` too: the primitives table, the How to
steps, and the Miscellaneous prompts subsection all reference prompts.

## Keep the dependency map in sync

`docs/guide/dependencies.md` maps who invokes what across prompts,
agents, skills, and MCP tools. Update it in the same change whenever a
prompt, agent, skill, or MCP tool is added or removed, or a dependency
between them changes — every edge must match an actual invocation in
the `.apm/` sources (no aspirational edges). Update the `README.md`
too: its primitives table lists every component, and its MCP tools
table the server's tool surface.

## Title and label every issue

GitHub issue titles follow the Conventional Commits form
`type(scope): summary`, exactly like commit messages and PR titles —
e.g. `feat(prompts): ...`, `fix(mcp): ...`, `docs(skill): ...`. Pick
the type and scope from the existing issue titles.

When creating a GitHub issue, always set: a type label (`bug`,
`enhancement`, `documentation`), a `priority: low|medium|high` label,
and — when the issue concerns a specific observability stack — that
stack's label (`datadog`, `local`, ...; create the label if it does
not exist yet).

When closing an issue as not planned, add the `wontfix` label and
close with a comment stating the rationale — the decision must be
readable from the issue itself.
