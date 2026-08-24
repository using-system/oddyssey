# CLAUDE.md

## Marketplace is generated — never edit it by hand

`marketplace/` is a build artifact: the release workflow regenerates it
from `.apm/` via `scripts/build-marketplace.sh`. Author every change in
`.apm/` (agents, skills, prompts) only, and leave `marketplace/` alone.
