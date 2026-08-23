<!-- PR title = the squash commit = the release note. Conventional Commits required:
     type(scope): lowercase imperative description
     feat -> minor release, fix/docs/ci/chore -> patch.
     NEVER add a `!` or BREAKING CHANGE marker without prior discussion. -->

## What


## Why


## How to test


## Checklist

- [ ] PR title follows Conventional Commits (it becomes the squash commit and drives the version)
- [ ] No `!` / breaking marker (or it was explicitly discussed first)
- [ ] `uvx ruff@0.16.4 check` and `format --check` pass (if `src/` or `tests/` changed)
- [ ] Unit tests pass; integration tests pass if the stack behavior changed
- [ ] No hand edits to generated files (`marketplace/`, `.claude-plugin/`, `.agents/plugins/`)
