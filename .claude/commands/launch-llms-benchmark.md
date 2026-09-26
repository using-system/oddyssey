---
description: Benchmark one LLM on the llms-benchmark demo stack - drive it through a coding-agent CLI (opencode, claude or copilot) on the stored scenario, grade the observation report it produced, and propose its row of the results table
argument-hint: "<opencode | claude | copilot> <vendor/model> [effort, default medium]"
---

Run the whole llms-benchmark protocol for one model on one CLI, end to
end, and come back with a pull request adding or replacing that row in
`.llms-benchmark/README.md`.

The question this benchmark answers: **how much of what a model reports,
after observing a running stack it has never seen, actually holds up?**
The demo stack under `.llms-benchmark/src/` is deliberately defective,
and what it gets wrong is written down nowhere in this repository — not
in a comment, not in a README, not in an issue. There is no answer key to
compare against, and that is on purpose: the model is graded on evidence,
the same way you would grade a colleague's incident report.

- Arguments: $ARGUMENTS
- Expected fields, in this order: the **CLI** the mission runs in —
  `opencode`, `claude` or `copilot`; the **model** to benchmark, as its
  canonical `vendor/name` id, the OpenRouter form
  (`anthropic/claude-sonnet-5`, `openai/gpt-5-mini`,
  `google/gemini-3.5-flash-lite`, ...); optionally, the **effort** the
  CLI runs the model at — `low`, `medium`, `high`, or any other level
  the CLI's effort flag accepts — **`medium` when omitted**, the level
  every row was measured at before this argument existed. Those are the
  only three inputs. Ask for the CLI or the model when missing and stop
  until you have both; never ask for the effort. Model, effort and CLI
  identify the row: the same model on two CLIs, or at two efforts, is
  two rows.
- The model id is written the same way whatever the CLI, so the two
  rows of one model line up. Each CLI is handed its own form of it:
  `opencode` takes it as `openrouter/<model>`; `claude` takes Anthropic
  models only, under Anthropic's id — `anthropic/claude-haiku-4.5` is
  `claude-haiku-4-5`, `anthropic/claude-sonnet-5` is `claude-sonnet-5`
  (the vendor prefix dropped, the dots of the version turned into
  dashes; `claude --help` on `--model` names the accepted forms);
  `copilot` takes the bare name its model picker lists —
  `openai/gpt-5.6-luna` is `gpt-5.6-luna` (the vendor prefix dropped,
  nothing else changed). A model the CLI cannot run, or cannot run at
  the requested effort, is a preflight failure, not a row. Below,
  `<effort>` is that argument, passed verbatim to the CLI's flag.

**Never ask for an API key, and never handle one.** Every credential this
protocol needs — the OpenRouter provider in opencode, the Claude Code
login, the demo agent's own key — is a prerequisite the person running
it sets up once, and the preflight checks them rather than requesting
them. No key is ever passed as an argument, written to a file, echoed
back, or allowed near a commit, a PR body, an issue, or a report.

Steps:

1. **Preflight** — all of these must hold; stop naming the failing one
   otherwise:
   - `git fetch origin` first, then: the working tree is clean, the
     current branch is `main`, and it is in sync with `origin/main`; a
     `bench/*` branch a previous run left behind is deleted here (it
     never ships, and it may carry that run's report);
   - `docker info` answers (the demo stack and the observability stack
     are both containers);
   - the local oddyssey stack is up (`odd_stack_status`; `odd_stack_up`
     if it is not) and `odd_config_get` says the configured stack is
     `local` — a run against another backend is not comparable with the
     rows already in the table;
   - `command -v k6` — the scenario is a k6 benchmark;
   - `.llms-benchmark/benchmark/llmbench-store-load/` exists (the stored
     scenario every row of the table was produced with);
   - **the CLI can run the model, and reads the package at the revision
     being measured** — configuring a provider or installing the package
     at user scope is the user's to do, once, and spending a run to
     discover it is missing is worse than refusing to start:
     - `opencode`: `opencode models openrouter` lists the model id you
       were given - or, when the listing lags OpenRouter's catalog (it
       did not carry `z-ai/glm-5.3-flashx` on 2026-09-19 while the
       model ran), a smoke run answers with a `text` event:
       `opencode run --model openrouter/<model> --variant <effort> --format json "reply with the single word ok" < /dev/null`
       (the package is installed in step 3) - **and the model has a
       variant at the requested effort**: `opencode run` accepts any
       `--variant` name, an unknown one included, records it on every
       message and sends no effort at all (verified on 2026-09-25 with
       `--variant bogus`). Read the model's `variants` from
       `opencode models openrouter --verbose`; when `<effort>` is not
       among them, launch without `--variant` and write `default` in the
       Effort column - the provider's default effort is what the model
       ran at (the `z-ai/glm-5.3*` models and
       `deepseek/deepseek-v4.1-flash` offer `low`, `high` and `max` only,
       so every row of theirs measured at "medium" ran at `default`);
     - `claude`: `claude --version` answers; the package is installed at
       **user scope** for Claude Code — `~/.claude/commands/odd-observe.md`,
       `~/.claude/agents/observe-run.md`, `~/.claude/skills/<the nine
       skills>` — and each body is identical to its `.apm/` source at
       `HEAD`: compare below the frontmatter against
       `.apm/prompts/<name>.prompt.md`, `.apm/agents/<name>.agent.md`
       and `.apm/skills/<name>/` — the suffixes matter: a diff against a
       path that does not exist compares two empty streams and reports
       them identical; the oddyssey MCP server is in the user's Claude
       configuration (`~/.claude.json`, `mcpServers` carries `oddyssey` —
       the name only, never its contents); and a smoke run answers with a
       result naming the model:
       `claude -p "Reply with the single word ok" --model <anthropic id> --effort <effort> --output-format json < /dev/null`
       must print a `type: result` JSON whose `modelUsage` carries the
       model's canonical id. Since Claude Code 2.1.270 a second key,
       `claude-haiku-4-5`, sits beside it on every run — a background
       call of about a thousand tokens the CLI makes on its own
       (0.001 USD) — so the check is that the benchmarked model's key is
       there and carries the spend, not that it is alone; step 7 records
       the haiku share beside the total. Run it from a scratch directory,
       not the repository — it leaves a session transcript under the
       directory's project;
     - `copilot`: `copilot --version` answers; the user is logged in
       (`~/.copilot/config.json` carries a non-empty `loggedInUsers` —
       the host and login, nothing else lives there); and a smoke run
       answers with a usage file naming the model:
       `copilot -p "Reply with the single word ok" --model <name> --effort <effort> --allow-all-tools --usage-output-file <scratch>/usage.json < /dev/null`
       must leave a `usage.json` whose `modelMetrics` has one key, the
       model's name. Run it from a scratch directory too — it leaves a
       session under `~/.copilot/session-state/`. Nothing is installed
       at user scope for this CLI: the package goes into the repository
       in step 3, and the MCP server rides on the launch line;
   - **`docker-compose/llms-benchmark/.env` exists and carries a
     non-empty `OPENAI_API_KEY`** — the demo agent's own model key, which
     `docker compose` reads on its own from that file. Check its
     presence, never its value, and never print it. The file is
     gitignored; `.env.example` next to it says what goes in.

2. **Create the work branch**: `bench/<cli>-<model-slug>-<effort>-<YYYYMMDD-HHMM>`,
   where `<model-slug>` is the model id with `/` and `.` replaced by
   `-`. Everything the run installs, configures, and produces happens on
   this branch, and none of it is what ships.

3. **Install or update the CLI, and the oddyssey package for it.**
   Record the CLI's version: it goes in the pull request, never in the
   table.

   For `claude`:
   - `claude update` (the native installer updates itself), then record
     `claude --version`.
   - the package is **not** installed into the repository for this CLI:
     the claude target deploys `.claude/settings.json` and `.claude/hooks/`,
     and a deployed hook loads into the running Claude Code session
     (AGENTS.md). The run reads the user-scope install the preflight
     verified, which is what `apm install --global --target claude` put
     there; nothing in the working tree changes before the run, so the
     `git status --porcelain` you record here is empty.

   For `opencode`:
   - opencode: `brew upgrade opencode` when Homebrew has it, else
     `opencode upgrade`, else the official install script. Record the
     resulting `opencode --version` — **and smoke the binary before
     trusting it**: `opencode run --model openrouter/<a cheap model>
     --format json "reply with the single word ok" < /dev/null` must
     print a `text` event. On 2026-09-14 Homebrew's `1.18.30_1` rebuild
     failed every run with `Unexpected server error` on stdout
     (`TypeError: undefined is not an object (evaluating 'a.name')` in
     `SystemPrompt.environment`, in any directory) while the official
     install script's binary of the same version ran; when the brew
     binary fails the smoke, install the official one
     (`curl -fsSL https://opencode.ai/install | bash`, with Homebrew off
     the `PATH` so the script's "already installed" check does not exit
     early — it lands in `~/.opencode/bin/`) and launch that path
     explicitly. Record which binary ran in the pull request.
   - the package, for the opencode target, **into the repository**
     (opencode's user scope takes no MCP server, so `--global` fails
     there):
     `uvx --from 'apm-cli==0.31.0' apm install --target opencode`
     from the repository root. Record `git status --porcelain` **before**
     this command: it deploys files into the working tree — `.opencode/`,
     `.agents/skills/`, `opencode.json`, and an edit to `.gitignore` —
     and step 9 has to put the tree back exactly as it was.
   - **a user-level copy of the package is a second install the run
     reads.** opencode also discovers `~/.claude/skills/`, and when the
     package is installed there most runs resolve the scripts through
     that path rather than the repository's. Diff it against
     `.apm/skills/` (`diff -rq`, ignoring caches) before launching: an
     older copy there measures another version than the row claims.
     **The tracked marketplace build is a third**: one run of 2026-09-14
     resolved every script through `marketplace/oddyssey/skills/`, the
     artifact the release workflow regenerates from `.apm/`. Diff it the
     same way; a release that lagged `.apm/` would measure the release,
     not `HEAD`.

   For `copilot`:
   - `copilot update`, then record `copilot --version`.
   - the package, for the copilot target, **into the repository**:
     `uvx --from 'apm-cli==0.31.0' apm install --target copilot`
     from the repository root. Record `git status --porcelain` **before**
     it: it deploys `.github/prompts/`, `.github/agents/`,
     `.github/hooks/`, `.github/mcp.json`, `.agents/skills/` and an edit
     to `.gitignore`, and step 9 has to put the tree back. The deployed
     hooks are Copilot's, not the running session's; the MCP file is
     what the launch line hands the CLI.
   - **a second install the run reads**: Copilot also loads
     `~/.copilot/skills/` and the skills of every installed plugin
     (`~/.copilot/installed-plugins/<marketplace>/<plugin>/skills/`).
     List them before launching: none of the package's nine skills may
     be there, and a run that lists a skill twice resolves one of them.

4. **Select the model.** Nothing to configure: the provider is already
   set up (preflight), and the model and effort are passed on the command
   line in step 6, never persisted into a config file — `opencode`:
   `--model openrouter/<model> --variant <effort>`; `claude`:
   `--model <anthropic id> --effort <effort>`; `copilot`:
   `--model <name> --effort <effort>`. The three flags name the same
   effort level; that is what makes two rows of one model at one effort
   comparable across CLIs.

5. **Clean what the next run must not read — then recreate the demo
   stack, never reuse a running one.** Before every run, whatever the
   previous one's end (a stall killed, an `ERROR` line, a restart leave
   everything below in place), in this order — the discipline the
   `test-plugin-harnessing` kit applies before each of its samples:

   - **no observation report of the three services, anywhere the run can
     read** — not tracked under `.odd/observe-run-reports/`, not
     untracked there, not on a `docs/odd-*-report-*` branch, not on the
     work branch. One report there and the bench is void: the run
     recalls it as its baseline and grades itself against a previous
     model's findings — the answer key step 9 exists to keep out of its
     hands. Prove the absence rather than assume it:
     `python3 .apm/skills/odd-memory/scripts/odd_recall.py --repo . --service llmbench-api --service llmbench-mcp --service llmbench-agent --stack local`
     must answer `no stored report matches` (services and stack only:
     an environment on the line would skip a report recorded at
     another one, and the file would still be there to read).
   - **the leftovers, before the store is emptied**: any `llmbench*`
     container beyond the three (a run can start its own copy of the
     stack under another project name — step 9 tells what one cost, and
     one left running exports into the store the reset is about to
     empty), every CLI's scratch directory and the `k6-summary-*.json`
     files (step 9's list, cleared unconditionally — another session's
     directory is the same hazard as a previous run's); and **let the
     previous run's process end, then wait a few seconds**: a launch
     that reads the CLI's log while the previous run still writes it
     takes that run's id — the trap step 6's watcher describes.
   - **the oddyssey stack's data: `odd_stack_reset`.** The store is
     shared machine-wide; the previous model's driven run is still inside
     the window this run observes (its own `odd-bench/…/<slug>` identity
     on the rows, more exemplars to open), and its profiles carry no
     instance identity at all. Two rows are comparable only when each
     model observes its own run's traffic and nothing else. The reset
     recreates the container with the persisted env; the stack stays the
     user's and stays up.
   - **the demo stack, recreated** — after the reset, so its first
     exports land in the empty store:

     ```
     docker compose -f docker-compose/llms-benchmark/docker-compose.yml down -v
     docker compose -f docker-compose/llms-benchmark/docker-compose.yml up -d --build
     ```

     `down -v` matters: it drops the catalog volume. Without it a previous
     run's orders and its service instance ids sit inside the window this
     run observes, and two rows stop being comparable.

   Then wait for the three containers to be healthy and prove it with
   one request to each of the three services. Only the api declares a
   healthcheck in the compose file: a wait for three `healthy`
   containers never ends (one run lost four minutes to it). Wait for
   the api to be `healthy` and for the
   other two to answer a request — `GET /health` on the api and the
   agent, a bare `POST /mcp` on the MCP server, which has no `/health`
   and answers 400 to say it is up — and retry the probes until all three
   answer: `Up` is printed before the process listens.

6. **Run the mission — twice.** Every model on every CLI is run twice,
   the second run only after step 9's teardown and step 5's cleaning
   and recreation have been done again in full (a second run that reads
   the first's report, scratch or traffic measures nothing), and each
   run is read (step 7) and graded (step 8) on its own. The row in the
   table is the **better of the two**: the run with more confirmed
   findings; on a tie, the cheaper; on a tie again, the shorter. The
   other run is not discarded: the pull request carries both runs'
   figures and says which one the row is. Two attempts are also the
   ceiling for a run that never produces a turn or declines to drive
   (step 8): a decline counts as one of the two.

   **A second run that is already worse than the first is stopped, not
   finished.** Watch it against the first run's figures: once it has
   been running longer than the first run's whole duration and its
   report is not written yet, or its drive has not started by the time
   the first run had finished, kill it by its PID — it can no longer
   beat the first on duration, its cost is already spent for nothing,
   and the twenty-to-forty minutes it still needs are better given to
   the next model. The row is the first run; the pull request records
   the second's launch time, the phase it was stopped in and its spend
   to that point. Decided on 2026-09-20 by the maintainer after the
   second run of one model passed the first's 29-minute total with its
   report still being generated, at 49 minutes.

   For each run: record the UTC timestamp **before** launching —
   step 7 needs it to identify the session. Then one headless run, from
   the repository root, on the work branch.

   `opencode`:

   ```
   caffeinate -i opencode run --model openrouter/<model> --variant <effort> \
     --format json --auto --title "llms-benchmark <model>" \
     "<the mission prompt below>" < /dev/null
   ```

   `claude` — generate the session id yourself and write it down: this
   CLI takes no title, and step 7 identifies the session by that id:

   ```
   SID=$(uuidgen | tr 'A-Z' 'a-z')
   caffeinate -i env -u CLAUDECODE -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_CODE_SESSION_ID \
     -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_PID \
     CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 \
     claude -p "<the mission prompt below>" --model <anthropic id> --effort <effort> \
     --permission-mode bypassPermissions --output-format json \
     --session-id "$SID" < /dev/null > <scratch>/run.json 2> <scratch>/run.err
   ```

   `copilot` — generate the session id yourself here too:

   ```
   SID=$(uuidgen | tr 'A-Z' 'a-z')
   caffeinate -i env COPILOT_TASK_WAIT_TIMEOUT_SECONDS=7200 \
     copilot -p "<the mission prompt below>" --model <name> --effort <effort> \
     --allow-all --no-ask-user --additional-mcp-config @.github/mcp.json \
     --session-id "$SID" --output-format json --usage-output-file <scratch>/usage.json \
     < /dev/null > <scratch>/run.jsonl 2> <scratch>/run.err
   ```

   `COPILOT_TASK_WAIT_TIMEOUT_SECONDS=7200` lifts prompt mode's 600 s
   wait on background tasks: a root that dispatches `observe-run` with
   `mode: background` and ends its turn has its subagent cancelled
   600 s later, report unwritten (`session.warning`
   `background_task_wait_timeout`, `subagent.completed` with
   `cancelled: true`) - the first `openai/gpt-6-luna` run of
   2026-09-24 lost its whole observation to it, ten minutes in. That
   run is void, not a row.
   `--allow-all` is this CLI's headless auto mode (tools, paths and
   URLs); `--no-ask-user` removes the tool a run would otherwise use to
   ask a question nobody answers; `--additional-mcp-config @.github/mcp.json`
   loads the MCP file step 3 deployed — on its own the CLI reads only
   `~/.copilot/mcp-config.json`, and the user's file stays untouched;
   `--session-id` is how step 7 finds the session; `--output-format json`
   streams the session's events to stdout, `model.call_start` /
   `model.call_finished` pairs and a final `result` among them, so
   stdout goes to a file; `--usage-output-file` writes the whole
   session's usage at exit, subagents included. Memory is off in prompt
   mode by default — never pass `--enable-memory`: a memory would carry
   one run's findings into the next. The CLI does not expand
   `/odd-observe`; the text reached the model as written, and the run of
   `openai/gpt-5.6-luna` invoked the package's skills through Copilot's
   `skill` tool and dispatched the observation to `observe-run` through
   its `task` tool — nothing was rewritten.

   Each part of the claude line is load-bearing. `env -u ...` strips the
   variables a Claude Code session exports into its shells: this command
   is usually run from inside one, and a nested launch that inherits them
   is treated as part of the parent (`env` takes its `-u` flags before
   any assignment — an assignment placed first turns the next `-u` into
   the command to run, and the launch dies at once with exit 127).
   `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` lifts print mode's ceiling on
   background tasks: a root that dispatches the observation agent in the
   background and ends its own turn is otherwise terminated 600 s later
   with the agent still running, and no report is written — one run of
   #534 lost its whole observation to that, after driving the scenario.
   `--permission-mode bypassPermissions`
   is the headless counterpart of opencode's `--auto`: under `-p` anything
   that would prompt is denied outright, and a denied `Bash` is a run that
   never drives. `--output-format json` prints the whole run's result — a
   single `type: result` object with the cost and token totals step 7
   reads — on stdout **at exit**, so stdout goes to a file, not to the
   terminal. The prompt, quotes included, reached `/odd-observe` as the
   command it names on the run of #534; nothing had to be rewritten.
   Launched from inside a Claude Code session in auto mode, the line is
   written into a script with the file-writing tool and the script is
   launched: a shell heredoc carrying `--permission-mode
   bypassPermissions` is refused by the session's classifier (2026-09-16).

   `caffeinate -i` keeps the machine from sleeping under the run. A
   suspend does not stop the work but it does add itself to the wall
   clock, and duration is one of the three axes the rank turns on — a run
   that spanned a sleep is measured wrong and must be re-run.

   **`< /dev/null` is not optional.** Run in the background with an open
   stdin, `opencode run` stops just after `init` — no child process, no
   socket, no output — and looks exactly like a slow run for as long as
   you let it.

   (`opencode serve` plus `run --attach` was considered and rejected: a
   server to start, a port to choose and a teardown to remember, where
   the only real problem was stdin. A server surviving a failed run is
   the kind of leftover state that makes two rows incomparable.)

   The mission prompt is one `/odd-observe` invocation that carries all
   three of its inputs itself — the services, the scenario and the
   stack — rather than naming some of them in prose around it:

   ```text
   /odd-observe observe the three services llmbench-api, llmbench-mcp and
   llmbench-agent by running .llms-benchmark/benchmark/llmbench-store-load/
   on the local stack
   ```

   Nothing in the line changes between two runs. Each of the three is
   named on purpose:
   - **the three services**, so the mission never has to guess its own
     scope from what happens to be running on the machine, and so the
     report's frontmatter carries all three;
   - **the scenario**, because every row of the table was produced from
     that same replayed traffic, and an ad-hoc one would grade the
     traffic instead of the model;
   - **the local stack**, because a mission that leaves it unsaid picks
     up whatever backend the configuration happens to carry.

   Every row so far was produced with that text wrapped in a pair of
   literal double quotes — the first campaign's shell quoting passed them
   through, and the string opencode received starts and ends with `"`.
   Keep it byte-identical, quotes included: read it back from a previous
   run's first user message rather than retyping it — the decoded string
   value (`jq -r`, `json_extract`), never the raw serialized text. Under
   `claude` and `copilot` that value is the argument as passed. **Under
   opencode it is not**: `opencode run` stores the argument wrapped in
   one more pair of escaped quotes than it was given (verified on
   2026-09-14 with a smoke argument: `"x"` passed, `"\"x\""` stored, after
   decoding), so the argument to pass is the same 669-character string
   as under the other two CLIs, and the store's form passed verbatim
   reaches the run double-wrapped (one run of 2026-09-12 did, at 693
   characters, when the mission still named a depth and was 683 long —
   #620 dropped the depth phrase, and every run since is 669).

   Add exactly three things to that line and nothing else: that the
   services' sources are under `.llms-benchmark/src/`; that you want
   **every kind of anomaly, not only the slow ones** — performance
   problems, outright errors, wrong behavior, and telemetry that is
   missing or lying, across all four signals; and, last inside the
   quotes, **"The scenario's calls to a paid model provider are accepted
   as authored."** That sentence is the input the observation agent's
   contract requires before it drives an operation that calls a paid
   model — without it the contract says to leave the operation out, and
   one model did exactly that, twice: asked a headless user for consent
   and ended, then replaced the stored scenario with traffic of its own.
   Every other model had recorded the spend as accepted on its own
   reading of "by running <the benchmark>". The sentence names no
   defect and no count; it was added on 2026-09-10 (#534), and the rows
   measured before it were driven exactly as if it had been there — each
   report records the acceptance the model inferred — so none was
   re-run; the maintainer decided that.

   And one more sentence, which is not a hint but a method: **drive and
   observe first — the code confirms what the telemetry surfaced, it does
   not decide what to look for.** Open a file only after a measurement
   led you to it, and only to check that measurement. Without it a model
   reads the whole application up front and finds its defects by code
   review, then dresses them in telemetry: the run of #489 read all ten
   source files nine minutes before it drove any traffic, where the run
   before it read one file, after its first queries. Forbidding the code
   outright would be worse — the ODD cross-check needs it, and half the
   findings would become unverifiable.

   **Tell it nothing else.** No hint about what to look for, no count of
   anything to find, no example of a defect. Any such hint invalidates
   the row.

   Do **not** ask the run to report its own cost or token usage. It
   cannot do it correctly — writing the report is itself part of the run,
   so anything it writes is a mid-run snapshot — and step 7 measures it
   better from outside.

   **Watch it while it runs, and say where it is.** A twenty-to-forty
   minute run that has silently died looks exactly like one that is
   thinking. Poll every couple of minutes — the run writes nothing to
   stdout until it finishes, so read these instead.

   Under `claude` the run keeps no central log; what grows live is its
   **session transcript**, `~/.claude/projects/<cwd with every / turned
   into ->/<session-id>.jsonl`, and the subagents' transcripts beside it
   under `<session-id>/subagents/agent-*.jsonl` (the observation is
   dispatched to one, as under opencode). Each `assistant` line carries
   the message's `tool_use` blocks — `Bash` with its `input.command`,
   `Read` with its `input.file_path` — and its `usage`; the line count
   across those files is the liveness signal, and a file that stops
   growing for several minutes with the process alive is the stall.
   The `k6` process, the container count and the run's scratch
   directory read the same way as below — this CLI's runs wrote their
   scratch under `/tmp/llmbench-*` directly, a third location.

   Under `copilot` what grows live is
   `~/.copilot/session-state/<session-id>/events.jsonl`: each
   `tool.execution_start` event carries `toolName` and `arguments`
   (`command` for `bash`, `path` for `view`), `subagent.started` /
   `subagent.completed` name the agent dispatched, and the line count is
   the liveness signal. The run of `openai/gpt-5.6-luna` wrote its
   scratch under `$TMPDIR/oddyssey/<slug>-local/` and recreated the
   three containers itself before driving, per the run-identity
   contract — the container count dips to one for a few seconds and
   comes back to three; anything else is a second stack.

   Under `opencode`:

   - `~/.local/share/opencode/log/opencode.log`, filtered to **this
     run's id** (the `run=<id>` on its `message=init` line; another
     opencode session of the user's writes to the same file, so never
     read the tail unfiltered). Pick the `init` line whose timestamp is
     after your launch, never the last one in the file: a watcher armed
     a few seconds early took the previous run's id and reported that
     model's activity for a whole poll. Its last line is the current
     activity, and its `pattern="..."` entries name the commands being
     run — but some runs alias the script paths in shell variables
     (`python3 $S counter ...`), so the patterns undercount what ran.
   - **`level=ERROR` in the run's log lines, on every poll.** This is the
     check that matters and it is cheap. A provider can fail a stream and
     leave the connection open: the process stays alive, its child stays
     alive, the socket stays ESTABLISHED, stderr stays empty, and nothing
     moves for as long as you let it. One run sat like that for nine
     minutes after two `stream error` lines and a 503, while every
     liveness check said it was working. Treat a stream opened with no
     completion and no new log line for several minutes as a stall, and
     say so instead of reassuring — but check the session store before
     killing anything: the log writes nothing during a stream, and two
     models of this campaign streamed nothing for six to eight minutes
     per turn and then completed, three times each, with no error line.
     The signal that separates the two is the `part` table — count the
     rows of the run's session tree and read their latest
     `time_updated`; a stream that is alive keeps adding parts, a stalled
     one does not. Give a silent turn a bounded wait (ten minutes was
     enough today) before ruling, and say which case it turned out to be.
   - the process itself: alive, and — past the first minute — with
     children. **Alive with no child and no new log line is the stdin
     hang**, not a slow model. Note the process you launched is a shell
     wrapper; opencode is its child, and it is the child's state that
     means anything.
   - **the `k6` process and the run's own scratch directory**, for the
     drive. Do not look for a `k6 run` bash pattern in the log: a run may
     drive through a helper script it writes, and then that pattern never
     appears at all — it stayed at zero for the whole of #489's run. The
     scratch directory (under the system temp dir, named after the run)
     fills with the run's query outputs, and its `k6-summary.json` appears
     when the drive ends. That directory is not always under
     `$TMPDIR/opencode/`: one run put it under `$TMPDIR/oddyssey/`, next
     to the gcx context file, and the k6 summary of a synchronous replay
     lands in `$TMPDIR` itself. The drive's own boundaries are what step 7
     needs; where to read them is settled there.
   - the session in the store (step 7's identification): its `cost` and
     token counters climb while the run works.

   Report progress to the user as it crosses the phases rather than at
   the end: preflight done, the k6 drive started and finished, the
   telemetry queries under way, the report written. Name what you are
   waiting on, and if a phase stalls with no new log line for several
   minutes, say so instead of waiting silently.

   **A turn that fails the same way three times will not pass.** opencode
   retries a failed stream without limit. On 2026-09-14 one model's
   report-writing turn — a single long generation — hit `Upstream idle
   timeout exceeded` (504) after about 3m50s of streaming four times in
   a row, and three more times on the identical re-run; a `z-ai` upstream
   that will not carry that generation is not going to on the fifth try.
   Kill by the PID after the third identical failure of one turn and
   record it as the provider not streaming; the row keeps its previous
   measurement, marked provisional.

   Never `pkill` by a pattern that could match another opencode process:
   the user may be running their own session at the same time. Kill by
   the PID you launched, or not at all.

7. **Read the run's cost from outside the run — and make sure it is the
   right session.** Where it lives depends on the CLI.

   **Under `claude`** the whole run's totals are the `type: result`
   object the launch line captured in `run.json`:
   - **Cost** = `total_cost_usd`, the sum of every `modelUsage` key's
     `costUSD` — since Claude Code 2.1.270 that includes the
     `claude-haiku-4-5` background call the smoke check describes, about
     0.001 USD; the table takes the total and the pull request states the
     haiku share. Its `costBasis` is `list`: the API list price, whatever
     plan the account is on — a subscription changes the bill, not this
     figure, and this figure is what the table wants.
   - the token counters are the benchmarked model's key,
     `modelUsage[<model>]`: `inputTokens`,
     `outputTokens` (thinking included; `thinkingTokens` states the
     share), `cacheReadInputTokens`, `cacheCreationInputTokens` — for the
     **whole tree**, subagents included (`subagent_stats.spawned` says
     how many there were). **Input** for the table = `inputTokens +
     cacheReadInputTokens + cacheCreationInputTokens`; **Output** =
     `outputTokens`; **Cache** = `cacheReadInputTokens +
     cacheCreationInputTokens` — the same three sums as under opencode.
   - **never the result's top-level `usage`, `num_turns` or
     `duration_ms`**: they cover the root session's last turn(s) only.
     On the run of #534 they read 26 input tokens, 3 turns and 18 s for
     a 10-minute run whose model usage was 4.15 million tokens.
   - identify the session by the id you generated: `session_id` in the
     result must equal it, and the transcript is
     `~/.claude/projects/<project>/<that id>.jsonl`. Anything else, stop
     and say so.
   - **the observation must have run on the benchmarked model.** The
     root session may dispatch `observe-run` through the Agent tool with
     a `model` of its own choosing — on 2026-09-20 a `claude-sonnet-5`
     root passed `model: 'opus'` on one run of two, and the subagent's
     89 requests, 90 % of the spend and the whole report were opus-5's.
     Read `modelUsage`'s keys: the benchmarked model's key, the
     `claude-haiku-4-5` background key, and nothing else carrying spend.
     A run whose report was written by another model measured that
     model: it is no row for this one, whatever it found — record it as
     void in the pull request with its cost, and the other run is the
     row (or re-run when it was the only one).
   - reconstruct the cost from the transcripts, root and
     `subagents/*.jsonl` together, at Anthropic's published list prices
     for the model: an `assistant` line is written once per content
     block and repeats the request's `usage` with `output_tokens`
     growing, so group the lines by `requestId` and take each counter's
     largest value. **Cache writes carry two prices**: `usage.cache_creation`
     splits `cache_creation_input_tokens` into `ephemeral_5m_input_tokens`
     and `ephemeral_1h_input_tokens`, and the one-hour tier costs more
     (for `claude-haiku-4-5`: 1.25 and 2.00 USD per million; input 1.00,
     output 5.00, cache read 0.10 USD per million). Summed per tier, the
     reconstruction
     matched `total_cost_usd` to the last digit on the run of #534; a
     flat write rate lands short and looks like a mismatch.
   - **turns** = the distinct `requestId` values across the tree;
     **median turn latency** = the median, over those requests, of the
     assistant line's timestamp minus the preceding line's timestamp in
     the same transcript (the transcript has no created/completed pair,
     so this is the wait for the model's first block).
   - **signals** and **file reads** come from the `tool_use` inputs
     across the tree — `Bash` commands and the helper scripts they run
     (the run of #534 put all fourteen query invocations in one
     `query-all-signals.sh`), `Read`/`Grep` file paths — dated against
     the drive.

   **Under `copilot`** the whole run's totals are the `usage.json` the
   launch line asked for:
   - `modelMetrics[<model>].usage` carries `inputTokens` (the whole
     prompt, cached share included), `outputTokens` (reasoning included;
     `reasoningTokens` states the share), `cacheReadTokens` and
     `cacheWriteTokens`, for the whole session — `agentMetrics` splits
     the same figures between `main` and each subagent, and
     `requests.count` is the number of model requests. **Input** =
     `inputTokens`; **Output** = `outputTokens`; **Cache** =
     `cacheReadTokens + cacheWriteTokens`; `tokenDetails.input` is the
     uncached share (`inputTokens` minus the two cache counters).
   - **Cost is not in the file**: Copilot bills premium requests and AI
     credits (`totalPremiumRequestCost`, `totalNanoAiu`), not dollars.
     Reconstruct it at the model vendor's published list price —
     uncached and cache-write tokens at the input rate, cache-read at
     the cached-input rate, output at the output rate (for
     `gpt-5.6-luna`: 0.20, 0.02 and 1.20 USD per million) — and record
     the premium requests and the AIU in the pull request beside it.
   - identify the session by the id you generated: the final `result`
     line of `run.jsonl` carries `sessionId`, and `session.start` in
     `events.jsonl` carries `selectedModel` and `reasoningEffort` —
     all three must match the launch. Anything else, stop and say so.
   - **turns** = `requests.count` summed over `modelMetrics`; **median
     turn latency** = the median of the `model.call_finished` minus
     `model.call_start` timestamps in `run.jsonl`, paired in order (the
     events carry no id).
   - **signals** and **file reads** come from the `tool.execution_start`
     events of `events.jsonl` — `bash` commands and the helper scripts
     they run, `view` paths — dated against the drive.

   **Under `opencode`** the store is
   `~/.local/share/opencode/opencode.db` (SQLite, WAL). Copy the `.db`,
   `-wal` and `-shm` files to a scratch directory and query the copy: a
   read-only connection to the live file can miss committed WAL frames.

   **Identifying the session is where this goes wrong.** The title alone
   is not enough — a previous run of the same model carries the same
   title. Select the root session on **all** of:
   - `title = 'llms-benchmark <model>'`, and
   - `time_created >= <the timestamp recorded in step 6>` — **read it
     back from the file you wrote it to, never retype it from memory**;
     a remembered value off by fifteen seconds makes this selector
     return zero rows and look like a protocol failure, and
   - `json_extract(model,'$.id')` equal to the model benchmarked, and
   - `directory` equal to the repository root, and
   - `parent_id IS NULL`.

   If that returns anything other than exactly one row, stop and say so
   rather than guess.

   **Then sum the whole tree, not the root.** opencode dispatches the
   observation to a subagent, which gets its own session; on the first
   run the subagent carried 80% of the spend. Walk `parent_id`
   recursively — descendants may nest deeper than one level — and sum
   every level:

   ```sql
   WITH RECURSIVE tree(id) AS (
     SELECT id FROM session WHERE id = '<root>'
     UNION ALL SELECT s.id FROM session s JOIN tree t ON s.parent_id = t.id)
   SELECT SUM(s.tokens_input), SUM(s.tokens_output), SUM(s.tokens_reasoning),
          SUM(s.tokens_cache_read), SUM(s.tokens_cache_write), SUM(s.cost)
   FROM session s JOIN tree ON tree.id = s.id;
   ```

   **What the counters mean**, because they are not what the names
   suggest. They are disjoint, and under prompt caching `tokens_input`
   holds only the prompt tokens that were neither written to nor read
   from cache — 208 on the first run, for 10.6 million prompt tokens
   processed. So:
   - **Input** for the table = `tokens_input + tokens_cache_read +
     tokens_cache_write`, the whole prompt. This is the only form that
     compares between two models: caching behavior differs per provider,
     and the raw field alone puts the same work at 208 for one and
     hundreds of thousands for another.
   - **Output** = `tokens_output + tokens_reasoning`; reasoning is billed
     as output.
   - **Cache** = `tokens_cache_read + tokens_cache_write`, the cached
     share of Input.
   - **Cost** = `SUM(cost)`, the provider's own figure. Sanity-check it
     against the model's published prices
     (`https://openrouter.ai/api/v1/models`, the `pricing` object): the
     four counters at those four rates reconstruct the recorded cost
     exactly. **Read the whole `pricing` object, not the four headline
     rates**: some models carry an `overrides` block that raises every
     rate above a prompt size, and a flat reconstruction then lands short
     and looks like a mismatch. Apply the tier per message, on that
     message's own prompt — and treat the stated `min_prompt_tokens` as
     indicative, not exact: on the run of #495 the reconstruction matched
     to the cent at 200,000 where the field said 272,000. An `overrides`
     entry can also be keyed by time rather than by size — `utc_days`
     with `utc_start` / `utc_end` in hours-and-minutes — doubling every
     rate inside a weekday window; pick the tier the run's UTC launch
     time falls in (one model of this campaign doubles its rates on
     weekdays between 01:00–04:00 and 06:00–10:00 UTC, and a run at
     19:35 UTC reconciled at the base rates). The tier billed can also
     differ from the window published: on 2026-09-16 two runs of that
     model thirteen minutes apart, both after the window's 10:00 UTC
     end, reconciled one exactly at the doubled tier and the other
     exactly at the base tier — the table takes the recorded figure and
     the pull request names the tier it reconciled at. If it still
     does not reconcile, say so instead of publishing the number.

   Also read off, under either CLI:
   - the **three phase durations**, not just the total: preflight
     (your launch timestamp → the drive's start), drive, and observation
     (drive end → your end timestamp). The total alone hides which of
     the three a model spends itself in. The drive's boundaries are the
     `window:` field of the report's own frontmatter: the contract
     requires it, so it is on every report, and it says what the run
     itself considered the drive — which is what the other rows were
     measured on. Cross-check it before trusting it, from the run's
     `k6-summary.json`: `http_reqs.count` divided by `http_reqs.rate` is
     k6's own duration, and the file's mtime is the drive's end, so the
     two together reconstruct the window without the run's help. They
     agreed to the second on the run of #505.

     Do not expect a file to hand you the window. The packaged
     `replay_benchmark.py` writes `replay-record.json` **only under
     `--detach`**; run synchronously it prints the window to stdout and
     leaves nothing behind — one run of #505 took each path, and only the
     detached one left a record. Earlier runs that composed their own
     wrapper each invented a name (`drive-window.txt`, `timestamps.env`,
     `run-timestamps.txt`) and one wrote none at all.
   - the **turns** — assistant messages across the whole session tree,
     same recursion as the cost — and the **median** per-turn latency
     from each message's `time.created` / `time.completed`. Use the
     median and never the mean: one message whose completion timestamp is
     written late is enough to make the mean meaningless (a 1078 s turn
     inside a 1240 s run, on the first run). The two together separate
     the two ways of being slow — many short turns is a model groping,
     few long ones is a model slow to answer.
   - the **oddyssey version** (`odd_config_get`'s `version`) — the
     release whose `.apm/` tree the run read. When the server the CLI
     launched carries a later patch whose `.apm/` is identical
     (`git diff <that tag> HEAD -- .apm` empty), the row keeps the
     release's version and the pull request states what the server
     answered (2026-09-16: the install generated `oddyssey-mcp==1.12.1`
     under a `.apm/` identical to `v1.12.0`'s);
   - how many of the four signals the run actually queried — count
     `gcx metrics` / `traces` / `logs` / `profiles` invocations in
     `~/.local/share/opencode/log/opencode.log` for this run's id, and
     corroborate with the run's scratch files, since a run that queries
     through helper scripts logs fewer invocations than it makes. The
     package's `grafana-*.py` scripts are what the runs call now, and the
     log's `pattern=` is truncated and alias-blind: count in the session
     store instead — the `part` rows of the tree whose `tool` is `bash`
     carry the full command — and add the helper scripts' contents. A
     query that produced nothing does not count: one run wrote
     `gcx query traces ...` (not a gcx command) and curled ports the
     stack does not publish, and every output file was empty — that is
     `0/4`, whatever the draft says it queried.

8. **Grade the report — this is your job, not the model's.**

   **A run that never produced a turn produces no row either.** The
   provider can accept the request and then stream nothing: the process
   stays alive, the log shows one `message=process` and no bash command,
   and the only other line is a `stream error` minutes later. One run of
   this campaign sat that way for 30 minutes, was re-launched with the
   identical mission against a freshly recreated stack, and repeated it.
   Two attempts is the rule, the same as for a run that declines to drive;
   after that "the provider did not stream" is the result, recorded with
   its timestamps in the pull request and with no row in the table.

   **First, check the run actually drove the scenario.** The report's
   frontmatter window must fall *after* your launch timestamp, and its
   mode must be a driven one. A run that reads `mode: post-hoc`, or whose
   window starts before it did, graded somebody else's traffic — one did
   exactly that, declaring a post-hoc analysis because it believed it
   could not start a stack that was already running and answering. That
   run produces **no row**: re-run it with the identical mission (changing
   the mission would invalidate every other row), and if it declines
   again, "did not drive the scenario" is its result. Two more shapes of
   declining, both seen on one model through `claude`: a run that stops
   to **ask the user's consent** for the scenario's paid model calls —
   under `-p` nobody answers, and the run ends with a question instead
   of a drive; and a run that **writes traffic of its own** in place of
   the stored scenario to avoid those calls (a curl loop over the free
   routes, no k6, no assistant scenario). The second grades the traffic,
   not the model, exactly what the stored scenario exists to prevent; it
   is a decline, whatever report it goes on to write, and it can be
   stopped by its PID as soon as its drive script shows what it is. Both
   shapes came from the paid-operation rule of the observation agent's
   contract, and the remedy is the acceptance sentence step 6 now puts in
   the mission — not a system prompt: `--append-system-prompt` reaches the
   root session only, never the subagent that reads the rule, and a run
   launched with it declined all the same. Two further shapes, both from
   one model through `claude` on 2026-09-14, neither about the paid
   calls: a run that greps the compose file, reads the `OPENAI_API_KEY`
   line, declares the key missing without opening the `.env` beside it
   (the containers were up and answering) and asks the headless user to
   set it; and a run that invokes the scenario skill through the
   `Skill` tool as if it were a command, waits for a file nothing
   writes, and goes on to observe an empty store — no `k6` process ever
   appears. Both are declines; after the second, "did not drive the
   scenario" is the model's result.

   **An account limit ends a run mid-flight, and the preflight cannot
   see it coming.** One `claude` run of 2026-09-14 drove the scenario,
   observed for six minutes, then exited with `is_error: true` and the
   result text "You've hit your monthly spend limit" — its smoke had
   passed minutes earlier. That is no row: the previous row stays,
   marked provisional, and the limit is the user's to lift; ask before
   re-launching, never spend a run to find out.

   **A run that drove but never persisted its report still gets a row.**
   One run drove the scenario, wrote a draft and a findings summary in
   its scratch directory, told the user the report "has been persisted to
   the `.odd/` memory", and wrote nothing there — `git log` on the work
   branch had no commit and the reports directory no new file. Grade the
   draft and the run's final answer as the report: the grade is of what
   the model claimed, and it claimed those. Say in the pull request that
   no report reached `.odd/`, and copy the draft out of the scratch
   directory before step 9 clears it.

   Then read the observation report the run stored under
   `.odd/observe-run-reports/` — **found by the branch, never by a grep
   for the services**: runs name the file after their own slug
   (`…-2fcc17e4.md`, `…-run-1789389106.md`, `…-obs-store-load-….md`),
   so `git diff --name-only main..HEAD -- .odd/observe-run-reports` plus
   the untracked files there is what lists it; a watcher that greps for
   `llmbench` reported "no report" on three finished runs of 2026-09-14 —
   and take every finding it reports, one at a time — the anomalies and
   the telemetry gaps alike; an absent signal that really is absent is a
   finding like any other. For each one, rule **confirmed** or **not
   confirmed** on its own evidence:
   - does the telemetry the finding cites actually say what the finding
     claims? Re-run the query yourself against the local stack.
   - does the code actually do what the finding says it does? Open the
     file and the line.

   **What counts as one reported item**, decided before you start
   grading, because models organise their reports differently and the
   denominator must not measure that:
   - **both sections count** — the anomalies and the telemetry gaps.
     Absent database spans were an anomaly for two runs and a gap for a
     third; counting the anomalies alone cost that third run a third of
     its score until the method was fixed.
   - **an entry that restates one already counted does not count twice**,
     wherever it sits. Gap sections routinely cross-reference their own
     findings — one run's five gaps were all restatements and added
     nothing.
   - **a row that bundles defects with different root causes and
     different fixes counts once per defect.** One run put a fan-out and
     the prompt inflation it causes on one line where another split them
     across two; one line is not one finding.

   **Aggregate a profile the way the report did.** A CPU percentage
   quoted off a flamegraph is almost always **self** time, and a grader
   who sums or maxes each frame's *total* gets a different number for the
   same profile — on the run of #505 the same frame read 88.4% as self
   time and 79.0% as the largest total, which is the difference between
   ruling a finding exact and ruling it wrong. Reproduce the report's
   figure under both readings before calling it unsupported.

   **k6's OTLP counters encode a Rate through a `condition` label.**
   `http_req_failed_total{condition="zero"}` counts the requests whose
   failed value was 0 and `checks_total{condition="nonzero"}` the checks
   that passed; summed across the label they equal the request and
   check totals, and read that way two reports of 2026-09-14 called the
   counter a lie ("4,223 failed despite zero failures"). Query
   `--by condition` before ruling on either.

   **The assistant scenario makes eight or nine arrivals.** One every
   15 s from t0, and whether the one at t0+120 s lands depends on the
   run: some runs of 2026-09-14 had nine `POST /ask` traces, all
   carrying the run's User-Agent, and `agent_questions_total` = 9;
   others had eight. Count the run's own traces by its User-Agent before
   ruling — a ninth that carries the UA is an arrival, not
   "pre-window contamination" (one report stopped its search one
   interval short and called the correct counter misleading) — and
   count the `chat` spans against the traces found, never against
   eight: one report ruled 17 usage records against "15 chat spans"
   that were 17.

   **Three `service_instance_id` values are one per service**, the api's,
   the mcp's and the agent's — not several instances of one service. And
   **a just-recreated stack has no request telemetry until the first
   request**: nothing but the compose healthcheck has reached it, and
   that leaves none, so a preflight probe that finds the api and the mcp
   "absent" minutes after `up` has found no traffic, not an export gap.

   **A large response is not on stdout.** `gcx traces get` on a wide trace
   answers with a `gcx.spill_reference` object naming a file it wrote
   instead of the trace; a grader that parses stdout gets a key error and
   can rule a true finding unsupported on nothing but that. Read the
   `spilled_to` path when the type says so. Reports also cite traces by an
   eight-character prefix, which `gcx traces get` does not accept: resolve
   the prefix against a `gcx traces query` listing first.

   **A missing child span needs a structural query.** A TraceQL
   conjunction inside one pair of braces — `{ name = "POST /orders" &&
   span.db.system.name = "sqlite" }` — matches a single span carrying
   both, so it returns zero whether or not the request has a database
   child. Three reports cited exactly that query as their evidence for
   an untraced write path; it happened to be right, but the query proved
   nothing. Rule such a finding on the structural form, `{ name = "POST
   /orders" } >> { span.db.system.name = "sqlite" }`, against a sibling
   route known to carry the child.

   **Re-read a raw attribute before ruling on a run's parser.** Two
   findings of this campaign came from a run's own attribute reader: one
   declared `gen_ai.response.finish_reasons` empty on every chat span
   because its reader handled string, int and double values and rendered
   the array as `""`; another counted an `order created` log line twice
   because its `grep -c` also matched the query echo the script appends
   to its own extract. Both looked like store facts and neither was.

   A finding is confirmed when both checks hold. It is not confirmed when
   the evidence does not support it, when the cited query returns
   something else, when the code does not do that, or when the finding is
   a restatement of another one already counted. A finding whose numbers
   are exact but which the report itself labels uncertain still counts:
   grading honesty down would only teach models to hide it.

   The row's grade is `confirmed / reported`. Record, for your own PR
   body, one line per finding with the ruling and why - for both runs,
   each under its own heading, the one the row is taken from named
   first (step 6's rule: more confirmed, then cheaper, then shorter).

9. **Tear down, put the tree back, then leave the branch behind.**
   - `docker compose -f docker-compose/llms-benchmark/docker-compose.yml down -v`,
     **then remove any remaining container whose name starts with
     `llmbench`**. `down -v` only knows its own compose project, and a run
     can start its own copy of the stack under another project name: one
     did, and its three containers ran for **ten hours** afterwards,
     exporting under the same service names. They exhausted the machine's
     memory and killed a later run outright, and because profiles carry no
     instance identity their idle CPU merged into four subsequent runs'
     profiles. Count the `llmbench` containers while the run works too —
     more than three means a second stack is up.
     Leave the oddyssey stack up — it is the user's, and it was probably
     up before the run; its data is the next run's business, step 5
     resets it before launching.
   - **delete the run's scratch directory under the system temp dir**
     (`$TMPDIR/opencode/`, and `/tmp/llmbench-*`, `/tmp/oddyssey-scratch/`,
     `/tmp/oddyssey-scratchpad/`, `/private/tmp/odd-scratch/`,
     `/tmp/odd-observe-scratch/` or `$TMPDIR/oddyssey/scratch/` for a
     `claude` run, `$TMPDIR/oddyssey/`,
     `/tmp/oddyssey/` or `/tmp/oddyssey-observe/` for a `copilot` run —
     one run of that CLI wrote under each — and **`.odd/scratch/` inside
     the repository**, where one `copilot` run of 2026-09-14 put its
     replay record, exemplars and report draft: untracked, unignored, and
     one `ls` away from the next run; the k6 summary lands beside them
     as `$TMPDIR/k6-summary-<slug>.json`, and one `claude` run left a
     `/tmp/llmbench-slug.txt`),
     every run's, not only this one's. Runs name
     that directory themselves and the names collide: one run of #505
     picked a name an earlier session had already used and inherited 248
     files — another model's query outputs, its trace dumps and its
     analysis scripts. That run happened never to read them, which was
     luck, not design: a single `ls` of its own scratch would have handed
     it a worked answer key, which is exactly what step 9 refuses to let
     the observation report carry into the repository. The directory is
     the same hazard with none of the protection, so clear it, and clear
     it after the run rather than during — the run writes its own k6
     summary there. Clear the run directories under `$TMPDIR/oddyssey/`
     too (every directory there; the gcx context files stay), and the
     `k6-summary-*.json` files a synchronous replay leaves in `$TMPDIR`
     itself: one run wrote its whole scratch under `$TMPDIR/oddyssey/`,
     beside a directory an earlier session had left there four days
     before — with that session's `report.md` inside it.
   - delete the untracked files step 3's install created and revert its
     edits to tracked files, against the `git status --porcelain` you
     recorded — leave anything that existed before untouched, the
     gitignored `.env` included. Delete what the install added, never the
     directory that holds it: the install writes `.agents/skills/`, but
     `.agents/` also holds the tracked `plugins/` build artifact, and
     removing the parent takes it with it. `git status --porcelain` must
     come back empty afterwards — that is the check, not the deletion;
   - **a killed run leaves an untracked skeleton** in
     `.odd/observe-run-reports/` — `odd_report.py new` wrote it, with
     `<fill>` in every section — that `git checkout main` keeps and the
     next run's `odd_recall.py` reads. Delete it, then prove the absence
     with the recall command of step 5 before anything else launches;
   - the run may have committed its observation report to the work
     branch. It does not ship: it names the defects it found, which is
     exactly what must not enter this repository, since the next model to
     be benchmarked can read it. Keep its content in your own context for
     step 10 and let the branch take the file with it;
   - `git checkout main`, then delete the work branch (`git branch -D`) —
     it never gets pushed.

10. **Open the results PR from a clean base.**
    - **Open the run's issue first.** Every PR in this repository
      references an existing issue, and a benchmark run is no exception:
      create one naming the model and the protocol revision, then the PR
      that closes it. This is a step, not a fallback.
    - From `main`, freshly pulled, create
      `docs/llms-benchmark-<cli>-<model-slug>-<effort>` and make **one** change:
      the row in the results tables of `.llms-benchmark/README.md`.
      `## Results` holds the two tables below. **A row is identified by
      model, effort and CLI together.** The triple is not in the table
      yet → append the row; already there → replace that row in place.
      The same model driven through two CLIs, or at two efforts, is two
      rows (`google/gemini-3.7-flash` under `opencode` and under another
      CLI both appear); the oddyssey version is not part of the key — a
      new run of the same model, effort and CLI overwrites the row,
      whatever version the old one carried. The table carries no
      history: one row per model, effort and CLI, always the latest
      run.

    **Two tables, not one.** Twenty-two columns scroll the model name off
    the screen and the rows stop being readable, and GitHub keeps no CSS
    to pin a column. So:

    - a **headline table** of thirteen columns — rank, model, effort, CLI,
      provider, oddyssey
      version, `confirmed / reported`, the findings by kind under a
      single `Telemetry / Perf / Behavior` header written `X / X / X`,
      total duration, cost, accuracy (confirmed over reported, as a
      percentage), cost per confirmed finding and seconds per
      confirmed finding (the total duration divided by the confirmed
      findings). It fits
      without scrolling and answers the question on its own. The effort
      column is the `<effort>` argument as passed to the CLI's flag
      (`medium` by default), right after the model it qualifies. The CLI
      column names the coding-agent CLI the mission ran in — the `<cli>`
      argument, `opencode`, `claude` or `copilot`, with no version: the version
      belongs in the pull request, where the row's exact figures already
      live. The provider column follows it and names who served the model:
      `OpenRouter` for opencode, `Anthropic` for claude, `Copilot`
      for copilot. The oddyssey version sits right after it because it says
      which protocol a row was taken under, which a reader needs before
      any number to its right means anything;
    - a **detail table** inside a `<details>` block — model, effort, CLI,
      provider,
      oddyssey version, the three phase durations, turns, median turn
      latency, input / output / cache tokens, and signals. Round the
      token counts (`30.0M`, `79k`): the
      exact figures live in each run's pull request, and full precision
      here only costs width.

    **The rank is decided with the user, not computed.** It weighs three
    axes together — findings, cost and duration — and none of them alone
    survives as a rule: ranking on findings would put a 67-minute run
    first, on duration would reward whichever model gives up soonest, on
    cost would reward the one that barely looks. Propose a placement in
    the PR and argue it on the three axes; adding or updating a model
    **re-sorts the whole table**, it never just inserts a line. A row
    measured under an earlier revision of the protocol is marked as such
    and its placement is provisional until it is re-run.

    Cost per confirmed finding is the column that answers the question in
    the README's title: cost and duration alone reward whichever model
    gives up soonest. The breakdown by kind exists because a run can
    score perfectly and still have looked at one kind of problem only —
    the first run's `7/7` was performance and nothing else.

    The PR body carries the per-finding rulings from step 8 for both
    runs, so the ratio is auditable and the choice between the two is
    too, and it names the CLI, its version and the effort flag
    used, with the effort level. It also notes three things the table has no column for: how
    many source files the run read **before** the drive, whether it drove
    any traffic of its own outside the stored scenario, and whether its
    report carries a replayable verification protocol.

    **Count the file reads inside the run's own scripts, not only in the
    log.** The log records a helper script's invocation, never the reads
    inside it, so a run that greps the sources from a `batch*.sh` looks
    like a run that never opened them: one run of this campaign read three
    source files that way and its log named none. Grep the run's scratch
    directory for the source paths as well, and date each read against the
    drive. Judge the traffic question the same way: a `curl` before the
    drive may be a health probe rather than traffic, and one after it may
    be fetching documentation — read the command before counting it.

    **It carries no API key and no list of the stack's defects** —
    the rulings read as "the report's finding N held up / did not hold
    up, because <evidence>", never as a catalogue of what the application
    gets wrong.

    Hand the PR back to the user. Do not merge it.

    **Never write a dollar sign followed by a digit in this file.** The
    command's text is expanded with its arguments before the model reads
    it, and a dollar sign followed by 1, 2 or 0 is a positional
    substitution: a price written as a dollar sign, `1.25` and `/M`
    reached one run as the first argument's text with `.25/M` appended.
    Write prices as `1.25 USD per million`.

11. **Amend this command when the run taught it something.** An install
    step that needed another flag, a configuration key that moved, a
    token field that turned out to live elsewhere, a preflight that
    should have caught something — fix it here, in the same PR as the
    results row. A protocol that drifts silently makes two rows
    incomparable; a protocol that records its own corrections stays
    honest. A change that alters what a run measures invalidates the
    rows taken before it: say so, and re-run them.
