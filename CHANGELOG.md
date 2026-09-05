## [1.11.1] - 2026-09-05

### 🚀 Features

- *(skill)* Get-status renders a one-screen synthesis by default, the full tables behind --full, and applies the caller's rulings before rendering (#365)
- *(skill)* Odd-memory - the finding ledger is written by a script the skill carries, every rule of the decisions reference checked before the row lands (#367)
- *(skill)* Get-status - the runtime / non-runtime classification of tree entries recorded once in .odd/entry-classifications.md, read by the script before the built-in list, instead of retyped as flags (#368)
- *(skill)* Odd-memory - a recall script the skill carries lists the stored reports a mission considers, so a recall reads one frontmatter instead of every one (#370)
- *(skill)* Odd-memory - a repository frontmatter field records which repository a report observed, so a central .odd/ store can tell services of several repositories apart (#373)
- *(skill)* Get-status resolves a report's revision and tree_anchor in the repository the report names, and rules the boundary unknown when that clone is not reachable (#374)

### 📚 Documentation

- *(readme)* Multi-repo strategies - a dedicated observability repository drives the loop when the system spans several repositories (#357)
- *(odd)* Classify this repository's top-level tree entries once, so the status settles a report's code boundary without flags (#372)

### ⚡ Performance

- *(agent)* The mission block carries the skills' directory, and an agent never searches the filesystem for a skill (#369)

### ⚙️ Miscellaneous Tasks

- *(apm)* Bump apm-cli to 0.29.0 in the install commands, the CI workflows and the marketplace build (#377)
- *(mcp)* Bump the local stack image to grafana/otel-lgtm 0.32.1 - Grafana 13.2.0, Loki 3.7.7, Pyroscope 2.3.0, OBI 0.12.2 (#379)
## [1.11.0] - 2026-09-04

### 🚀 Features

- *(hooks)* Refuse git commit on the default branch with a PreToolUse hook (#310)
- *(hooks)* Flag real identifiers and home paths in a file written under .odd/ with a PostToolUse hook (#312)
- *(skill)* Odd-memory - one contract for the .odd/ memory, each create and show skill keeps only its specifics (#315)
- *(skill)* Fold the create and show skills into odd-memory references - one memory skill, one reference per kind (#316)
- *(skill)* Backend-configuration - one skill for the check and the switch of the configured backend (#318)
- *(mcp)* Odd_config_set accepts a custom observability stack declared by the caller (#322)
- *(skill)* A custom observability stack as the fifth memory kind, checked against the reference contract at switch time (#325)
- *(prompts)* /odd-config creates or completes a custom stack file from the user's sources, their instructions, or web research (#326)
- *(agent)* Observe-run proposes a reviewed diff to a custom stack file after a run that exercised its commands (#327)
- *(skill)* A custom stack file may link an external guide - fetched and checked at switch time, amended where it lives (#328)
- *(mcp)* Remove the splunk built-in stack (#330)
- *(agent)* Observe-run - a check that passes on zero is validated on the zero branch, and the marker says which shapes were exercised (#332)
- *(skill)* Get-status - verify the memory invariant, every stored report carries the contract's frontmatter and every decision names an existing report (#335)
- *(agent)* Collector health checks name the component id as configured, and a grep that matches nothing on the whole history closes nothing (#339)

### 🐛 Bug Fixes

- *(agent)* Otel-instrumentation-expert - a verification check never projects a credential field (#308)
- *(skill)* Record-finding-decision - never commit the ledger on the default branch (#309)
- *(skill)* Run-scenario - a header-borne run identity for a target the run cannot launch, with run-unique trace ids (#331)
- *(odd)* Two stored reports quote a home-directory path from a Docker log - replaced by a placeholder, a recorded exception to the append-only rule (#336)
- *(skill)* Cloudwatch - the edge-diff recipe probes the resource fields first, the percentile sources are named, and three X-Ray and Logs Insights traps documented (#337)

### 🚜 Refactor

- *(skill)* Run-scenario - a light SKILL.md carrying the shared method, the run identity, the benchmark replay and the long-scenario carve-outs as references read by block (#334)

### 📚 Documentation

- *(guide)* Prompts - pair each example invocation with its field mapping (#289)
- *(agents)* Record the choices that deviate from the issue's spec as comments on that issue (#297)
- *(skill)* Observability-cli-guides - write the reference contract every stack file must carry, and check it in ci-apm (#313)
- *(guide)* Custom backends - create, edit, amend and link a custom stack, with a README section listing every backend (#329)
- *(skill)* Azure-monitor - ingest latency and the bounded poll, reserved KQL aliases, --offset over an explicit window, customMetrics temporality detected before trusted (#338)

### ⚡ Performance

- *(skill)* Get-status - deterministic status script, the model reasons on a fact sheet instead of parsing every report and running git turn by turn (#292)
- *(skill)* Get-status - render the status deterministically, the model adds judgment only (#294)
- *(skill)* Create-observe-run-report - return the synthesis block, never the report body (#298)
- *(agent)* Observe-run - bound the setup reads by section, never the agent file (#299)
- *(agent)* Observe-run - discoveries and exemplar fetches as shell-level concurrency in one call (#300)
## [1.10.3] - 2026-09-03

### 🚀 Features

- *(agent)* Observe-run - one flush wait per mission and parallel signal discovery (#267)
- *(skill)* Trim the preflight and baseline reads of an observe mission (#268)
- *(prompts)* Quick mode for /odd-observe and /odd-verify - a bounded mission under five minutes (#269)
- *(skill)* Run-scenario - a port already served by a foreign process is never killed, the run moves to a free one (#275)
- *(agent)* Route instrumentation protocol queries and timestamps (#276)

### 🐛 Bug Fixes

- *(agent)* Presence rulings prove which process emitted the signal, and profiles get a per-run identity (#272)

### 📚 Documentation

- *(readme)* Move the primitives table into the dependency map (#253)
- *(guide)* Simplify the README prompt sections and the guides - user docs are not specs (#271)
- *(skill)* Grafana reference - profile selectors, labels scope, query envelope and frame naming (#273)
- *(skill)* Grafana reference - count log lines over a finished window from raw lines, not edge-straddling samples (#274)
- *(prompts)* Name both preflight stop outcomes - not installed, and not configured (#277)
## [1.10.2] - 2026-09-02

### 🚀 Features

- *(agent)* Validate a k6 benchmark with inspect and one smoke iteration before persisting (#237)
- *(skill)* Auto-install k6 from the prompts' preflight when it is missing (#239)

### 🐛 Bug Fixes

- *(prompts)* Run a stored k6 benchmark through /odd-observe and run-scenario (#236)
- *(skill)* Count .odd/benchmarks/ changes as changed code for the verify-vs-re-measure boundary (#238)
- *(agent)* Cross-check every threshold against the service floors the investigation found (#240)
- *(prompts)* Ask before any drive replay on a remote stack, whatever the report kind (#241)

### 🚜 Refactor

- *(skill)* Centralize per-stack knowledge in observability-cli-guides (#244)

### 📚 Documentation

- *(skill)* Name gcx's Unix-seconds convention and the traces get envelope in the grafana reference (#242)
- *(readme)* Embed the trailer video in place of the banner image (#246)
## [1.10.1] - 2026-09-02

### 🚀 Features

- *(mcp)* Publish pyroscope ingest port 4040 as a fourth named local port (#233)

### 🐛 Bug Fixes

- *(skill)* Distinguish expired SSO token from NoCredentials in cloudwatch guides (#230)
- *(skill)* Flag cumulative-temporality trap in cloudwatch statistics roll-ups (#231)

### 📚 Documentation

- *(skill)* Add cloudwatch CLI pagination, dimensions, percentile, and X-Ray filter edge cases (#232)
## [1.10.0] - 2026-08-31

### 🚀 Features

- *(apm)* Add /odd-instrument-bench for k6 benchmark authoring (#211)

### 🐛 Bug Fixes

- *(agent)* Forbid observe-run and otel-instrumentation-expert self-delegation (#204)
- *(mcp)* Validate stack_config keys against a per-stack field whitelist (#206)
- *(aws)* Add cloudwatch profile/metrics_log_group fields, document CLI gaps (#208)

### 🚜 Refactor

- *(prompts)* Rename /odd-instrument to /odd-instrument-otel (#210)

### 📚 Documentation

- *(agents)* Document the community label for discoverability issues (#200)
- *(agents)* Broaden the no-secrets rule to real identifiers and account names (#202)
- *(skill)* Document azure-monitor CLI first-use noise and customDimensions encoding (#203)
- *(skill)* Document the gcx sum() series-limit trap and logs labels time flags (#205)
- *(guide)* Add backends guide - CLI, connect, required resource, switch prompt (#209)
## [1.9.0] - 2026-08-30

### 🚀 Features

- *(skill)* Sanctioned session-scoped gcx targeting for remote grafana missions (#175)
- *(tests)* Integration coverage for the configuration surface (#176)
- *(skill)* Squash-proof tree_anchor in the report contracts (#178)
- *(claude)* /oddyssey-publish labels the released issues with their version (#182)

### 🐛 Bug Fixes

- *(skill)* Grafana reference matches the real gcx CLI - output contract, flag surface, loki over otlp (#174)
- *(skill)* Check-backend-configuration detects a missing cli binary first (#177)
- *(skill)* Require and verify application insights on the azure-monitor stack (#180)
- *(apm)* Add discoverability metadata to pyproject and plugin manifest (#186)

### 💼 Other

- *(deps)* Bump mcp from 2.0.0 to 2.1.1 in /src/mcp-server (#185)
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
