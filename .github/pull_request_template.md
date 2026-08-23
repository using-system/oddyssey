<!-- PR title = the squash commit = the release note.
     Conventional Commits required - the rules live in CONTRIBUTING.md#pull-requests. -->

## What


## Why


## How to test


## Checklist

- [ ] PR title follows Conventional Commits (it becomes the squash commit and drives the version — see CONTRIBUTING)
- [ ] No `!` / breaking marker (or it was explicitly discussed first)
- [ ] `ruff check` and `format --check` pass at the CI-pinned version (if `src/` or `tests/` changed)
- [ ] Unit tests pass; integration tests pass if the stack behavior changed
- [ ] No hand edits to generated files (`marketplace/`, `.claude-plugin/`, `.agents/plugins/`)
