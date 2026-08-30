## [1.8.3] - 2026-08-30

### 🚀 Features

- *(skill)* Show-report skills close the missions with a synthesis (#165)

### 🐛 Bug Fixes

- *(skill)* Guard the default branch before committing a report (#161)
- *(agent)* Drive the scenario to completion inside the turn (#164)

### 📚 Documentation

- *(odd)* Close finding N2 by evidence - opt-in attribution verified 18/18, tracked decision superseded (#156)
- *(agents)* Clean up the apm validation's working-tree side effects (#163)
## [1.8.2] - 2026-08-29

### 🚀 Features

- *(mcp)* Document and pin the opt-in instance identity - OTEL_RESOURCE_ATTRIBUTES separates co-resident servers (#153)

### 🐛 Bug Fixes

- *(mcp)* Telemetry polish and a clean loop - probe-failure counter, image-inspect span, quiet boot-polls, decisions ledger in action (#151)

### 📚 Documentation

- *(skill)* Field fixes - reset-forbidden and long scenarios, gcx minimum version and --json shape, Pyroscope time range (#152)
## [1.8.1] - 2026-08-29

### 🚀 Features

- *(mcp)* Odd_stack_status returns the container identity - image, timestamps, and redacted user env (#146)

### 🐛 Bug Fixes

- *(ci)* Backtick bare at-words at changelog generation - manual CHANGELOG fixes do not survive git-cliff regeneration (#144)

### 📚 Documentation

- *(agents)* Tests follow the MCP server - unit coverage moves with behavior, integration coverage with the wire surface (#147)
## [1.8.0] - 2026-08-28

### 🚀 Features

- *(prompts)* /odd-status wontfix ledger - record finding decisions via skills, stop showing declined findings as open (#141)

### 🐛 Bug Fixes

- *(skill)* Re-measure report mode - a no-fix protocol replay keeps a machine-readable chain (#133)
- *(skill)* Regenerate the isolated gcx context whole after a port change - in-place edits break the keychain credential binding (#139)
- *(skill)* Datadog connection proof parses pup output - the exit code is 0 authenticated or not (#140)

### 📚 Documentation

- *(changelog)* Backtick `@import` so it stops rendering as a user mention (#130)
- *(agents)* Issue titles follow the conventional commits form (#132)
- *(guide)* Reports guide - frontmatter fields, allowed values, and body structure of both report kinds (#135)
- *(contributing)* Harden the contributor path - AGENTS.md conventions and rules, security guidance, strict PR-issue requirement (#138)
## [1.7.3] - 2026-08-28

### 🐛 Bug Fixes

- *(mcp)* Stack env survives recreations and stack_config gains null deletion (#127)

### 📚 Documentation

- *(agents)* AGENTS.md as the single instruction file - CLAUDE.md becomes an `@import` bridge (#125)
- *(guide)* Split the dependency map into per-prompt diagrams for readability (#126)
- *(readme)* State the minimum apm-cli version and why the pin matters (#128)
## [1.7.2] - 2026-08-26

### 🐛 Bug Fixes

- *(claude)* /oddyssey-publish watches the run and drives the pypi approval (#107)
- *(prompts)* Odd-observe answers service-less discovery questions directly (#111)
## [1.7.1] - 2026-08-26

### 🐛 Bug Fixes

- *(ci)* Mint the release App token with client-id (#100)
- *(ci)* Release notes from an explicit tag range - the trigger tag empties git-cliff's unreleased set (#104)

### 📚 Documentation

- *(guide)* Prompt usage examples and the component dependency map (#102)
- *(readme)* Drop the duplicate dependencies.md link from How to (#105)
## [1.7.0] - 2026-08-26

### 🚀 Features

- *(mcp)* Carry the container environment forward through odd_config_set's auto-reset (#82)
- *(mcp)* Bump otel-lgtm to 0.31.0 and catalog its environment surface in setup-local-stack (#84)
- *(skill)* Verification reports named verify-<run_name> with a verifies frontmatter link (#92)
- *(apm)* /odd-verify also accepts an instrumentation report as the baseline to verify (#93)
- *(apm)* /odd-status - the state of the ODD loop from the .odd/ history (#95)
- *(prompts)* /odd-config - display the backend configuration and guide backend changes (#96)

### 🐛 Bug Fixes

- *(skill)* Rename report frontmatter environment to stack and record the detected deployment environment (#97)
- *(ci)* Tag-driven release - the PR the workflow opens is the PR it merges (#98)
## [1.6.1] - 2026-08-24

### 🐛 Bug Fixes

- *(mcp)* Local is a first-class stack value - grafana means remote Grafana (#68)
## [1.6.0] - 2026-08-24

### 🚀 Features

- *(mcp)* Stack env passthrough and delta-metric ingestion (#55)
- *(mcp)* Persistent global configuration - stack backend and local ports (#63)
- *(apm)* Backend preflight - check-backend-configuration skill and configured-stack resolution (#65)

### 🐛 Bug Fixes

- *(method)* Run-scoped metrics, pinned identities, and validated checks (#56)

### 📚 Documentation

- *(skill)* Run-scenario contract for expensive or non-deterministic scenarios (#57)
- *(skill)* Otel-guides - three measured pitfalls from real adoption (#58)

### ⚙️ Miscellaneous Tasks

- *(release)* Name runs after the chosen mode (#54)
## [1.5.0] - 2026-08-23

### 🚀 Features

- *(mcp)* Make odd_stack_reset machine-wide wipe visible (#49)

### 🐛 Bug Fixes

- *(mcp)* Probe all four signal backends for stack readiness (#51)

### 📚 Documentation

- *(skill)* Align setup-local-stack with the verified gcx surface (#52)
## [1.4.1] - 2026-08-23

### ⚙️ Miscellaneous Tasks

- *(community)* Community health files and manual release proposing (#45)
## [1.4.0] - 2026-08-23

### 🚀 Features

- *(apm)* In-repo instrumentation memory and committed odd reports (#32)
## [1.3.0] - 2026-08-23

### 🚀 Features

- *(marketplace)* Native claude, copilot, kimi and codex marketplace distribution (#30)

### 📚 Documentation

- *(readme)* Update command and one-telemetry-two-consumers principle (#28)
## [1.2.0] - 2026-08-22

### 🚀 Features

- *(mcp)* Opentelemetry instrumentation of the oddyssey mcp server (#26)

### 📚 Documentation

- *(readme)* Document the claude install command and the other targets (#24)
## [1.1.0] - 2026-08-22

### 🚀 Features

- *(apm)* In-repo observation memory and /odd-verify verification pass (#22)
## [1.0.0] - 2026-08-22

### 🚀 Features

- *(apm)* [**breaking**] Restructure primitives under .apm, entry prompts, full-target ci (#19)
## [0.1.1] - 2026-08-22

### 🐛 Bug Fixes

- *(mcp)* Match the no-such-container error case-insensitively (#13)
## [0.1.0] - 2026-08-22

### 🚀 Features

- Bootstrap oddyssey as an apm package for observability-driven development (#1)
- Grafana proxy routing, observe-local-run agent, simplified readme (#2)
- [**breaking**] Reposition as an odd toolbox with otel instrumentation planning (#3)
- *(mcp)* Drive docker directly without a compose file (#5)
- *(agents)* Harden both agents into true experts with supporting skills (#7)
- *(mcp)* Add odd_stack_reset tool (#8)
- *(agents)* [**breaking**] Generalize observe-run to any observability backend (#9)

### 📚 Documentation

- Add the oddyssey banner to the readme (#6)

### ⚙️ Miscellaneous Tasks

- *(mcp-server)* Add lint, unit-test, and mcp-client integration jobs (#4)
- *(release)* Auto version bump, github release, and pypi publish (#10)
- *(release)* Git-history-driven release flow (git-cliff) with approved release pr (#11)
