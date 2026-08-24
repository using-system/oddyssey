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
- *(release)* 1.6.0 (#66)
## [1.5.0] - 2026-08-23

### 🚀 Features

- *(mcp)* Make odd_stack_reset machine-wide wipe visible (#49)

### 🐛 Bug Fixes

- *(mcp)* Probe all four signal backends for stack readiness (#51)

### 📚 Documentation

- *(skill)* Align setup-local-stack with the verified gcx surface (#52)

### ⚙️ Miscellaneous Tasks

- *(release)* 1.5.0 (#53)
## [1.4.1] - 2026-08-23

### ⚙️ Miscellaneous Tasks

- *(community)* Community health files and manual release proposing (#45)
- *(release)* 1.4.1 (#47)
## [1.4.0] - 2026-08-23

### 🚀 Features

- *(apm)* In-repo instrumentation memory and committed odd reports (#32)

### ⚙️ Miscellaneous Tasks

- *(release)* 1.4.0 (#33)
## [1.3.0] - 2026-08-23

### 🚀 Features

- *(marketplace)* Native claude, copilot, kimi and codex marketplace distribution (#30)

### 📚 Documentation

- *(readme)* Update command and one-telemetry-two-consumers principle (#28)

### ⚙️ Miscellaneous Tasks

- *(release)* 1.3.0 (#31)
## [1.2.0] - 2026-08-22

### 🚀 Features

- *(mcp)* Opentelemetry instrumentation of the oddyssey mcp server (#26)

### 📚 Documentation

- *(readme)* Document the claude install command and the other targets (#24)

### ⚙️ Miscellaneous Tasks

- *(release)* 1.2.0 (#27)
## [1.1.0] - 2026-08-22

### 🚀 Features

- *(apm)* In-repo observation memory and /odd-verify verification pass (#22)

### ⚙️ Miscellaneous Tasks

- *(release)* 1.1.0 (#23)
## [1.0.0] - 2026-08-22

### 🚀 Features

- *(apm)* [**breaking**] Restructure primitives under .apm, entry prompts, full-target ci (#19)

### ⚙️ Miscellaneous Tasks

- *(release)* 1.0.0 (#21)
## [0.1.1] - 2026-08-22

### 🐛 Bug Fixes

- *(mcp)* Match the no-such-container error case-insensitively (#13)

### ⚙️ Miscellaneous Tasks

- *(release)* 0.1.1 (#14)
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
- *(release)* 0.1.0 (#12)
