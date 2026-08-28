<!-- PR title = the squash commit = the release note.
     Conventional Commits required - the rules live in CONTRIBUTING.md#pull-requests. -->

## What


## Why


## How to test


## Checklist

- [ ] References an existing issue (`Closes #N` above — open the issue first when none exists)
- [ ] PR title follows Conventional Commits (it becomes the squash commit and drives the version — see CONTRIBUTING)
- [ ] No `!` / breaking marker (or it was explicitly discussed first)
- [ ] `ruff check` and `format --check` pass at the CI-pinned version (if `src/` or `tests/` changed)
- [ ] Unit and integration tests pass (CI runs both on any `src/`, `tests/`, or `integration-tests/` change)
- [ ] No hand edits to generated files (`marketplace/`, `.claude-plugin/`, `.agents/plugins/`)
- [ ] Docs kept in sync per AGENTS.md: prompts guide, dependency map, and reports guide updated in the same change when their sources changed
- [ ] No secrets in the diff or in committed `.odd/` reports (tokens, credentials, real endpoints — by name only)
