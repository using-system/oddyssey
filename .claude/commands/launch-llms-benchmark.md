---
description: Benchmark one LLM on the llms-benchmark demo stack - drive it through opencode on the stored scenario, grade the observation report it produced, and propose its row of the results table
---

Run the whole llms-benchmark protocol for one model, end to end, and
come back with a pull request adding or replacing that model's row in
`.llms-benchmark/README.md`.

The question this benchmark answers: **how much of what a model reports,
after observing a running stack it has never seen, actually holds up?**
The demo stack under `.llms-benchmark/src/` is deliberately defective, and
what it gets wrong is written down nowhere in this repository — not in a
comment, not in a README, not in an issue. There is no answer key to
compare against, and that is on purpose: the model is graded on evidence,
the same way you would grade a colleague's incident report.

- Arguments: $ARGUMENTS
- Expected fields (free-form): the **model** to benchmark, as its
  OpenRouter id (`anthropic/claude-sonnet-5`, `openai/gpt-5-mini`,
  `google/gemini-3.5-flash-lite`, ...) — required; and the **OpenRouter
  API key** — required. Ask for whichever is missing and stop until you
  have it.

**The key is a runtime value and nothing else.** Never write it to a
file, never put it in a command you echo back, never let it reach a
commit, a PR body, an issue, a log excerpt, or the observation report.
It lives in the environment of the processes that need it, for the
duration of the run.

Steps:

1. **Preflight** — all of these must hold; stop naming the failing one
   otherwise:
   - `git fetch origin` first, then: the working tree is clean, the
     current branch is `main`, and it is in sync with `origin/main`;
   - `docker info` answers (the demo stack and the observability stack
     are both containers);
   - the local oddyssey stack is up (`odd_stack_status`; `odd_stack_up`
     if it is not) and `odd_config_get` says the configured stack is
     `local` — a run against another backend is not comparable with the
     rows already in the table;
   - `command -v k6` — the scenario is a k6 benchmark;
   - `.llms-benchmark/benchmark/llmbench-store-load/` exists (the stored
     scenario every row of the table was produced with).

2. **Create the work branch**: `bench/<model-slug>-<YYYYMMDD-HHMM>`,
   where `<model-slug>` is the model id with `/` and `.` replaced by
   `-`. Everything the run installs, configures, and produces happens on
   this branch, and none of it is what ships.

3. **Install or update opencode, and the oddyssey package for it.**
   - opencode: `brew upgrade opencode` when Homebrew has it, else
     `opencode upgrade`, else the official install script. Record the
     resulting `opencode --version`.
   - the package, for the opencode target, **into the repository**
     (opencode's user scope takes no MCP server, so `--global` fails
     there):
     `uvx --from 'apm-cli==0.29.1' apm install --target opencode`
     from the repository root. Record `git status --porcelain` **before**
     this command: it deploys files into the working tree, and step 9
     has to put the tree back exactly as it was.

4. **Configure opencode for OpenRouter, at medium reasoning effort.**
   Export `OPENROUTER_API_KEY` in the environment of the run — that is
   the whole configuration, and it keeps the key out of every file
   opencode writes. The model and the effort are passed on the command
   line in step 6 (`--model openrouter/<model>`, `--variant medium`),
   never persisted into a config file. Verify the provider resolves
   before spending a run on it: `opencode models openrouter` must list
   the model id you were given; stop and say so if it does not.

5. **Start the demo stack and let it settle.**
   `docker compose -f docker-compose/llms-benchmark/docker-compose.yml up -d --build`
   with `OPENAI_API_KEY` set to the same OpenRouter key (the demo agent
   calls the provider too, on its own default model — that is part of
   the stack under observation, not part of what is being graded).
   Wait for the three containers to be healthy and prove it with one
   request to each of the three services.

6. **Run the mission.** One headless opencode run, from the repository
   root, on the work branch:

   ```
   OPENROUTER_API_KEY=<the key> opencode run \
     --model openrouter/<model> --variant medium \
     --format json --auto --title "llms-benchmark <model>" \
     "<the mission prompt below>"
   ```

   The mission prompt asks for exactly two things:

   - **`/odd-observe run .llms-benchmark/benchmark/llmbench-store-load/ in quick mode on the local stack`**
     — the stored scenario, driven, in quick mode, on the **local**
     oddyssey stack. Both halves are named on purpose: the scenario,
     because every row of the table was produced from that same
     replayed traffic and an ad-hoc one would grade the traffic instead
     of the model; and the stack, because a mission that leaves it
     unsaid can pick up whatever backend the configuration happens to
     carry, and a row observed against another backend is not
     comparable with the rest of the table.
   - **the run's own cost, written into the report it produces**: wall
     clock duration, input tokens, output tokens, and cache tokens.

   Tell it plainly that the services under observation are
   `llmbench-api`, `llmbench-mcp` and `llmbench-agent`, and that their
   sources are under `.llms-benchmark/src/`. Tell it nothing else — no
   hint about what to look for, no count of anything to find. Any such
   hint invalidates the row.

   Capture the session id from the run, and take the token counts from
   `opencode export <session-id>` as the authoritative figures: the
   model's self-report goes in the report, the session export goes in
   the table. When they disagree, the export wins and the PR says so.

7. **Grade the report — this is your job, not the model's.** Read the
   observation report the run stored under `.odd/observe-run-reports/`
   and take every finding it reports, one at a time. For each one, rule
   **confirmed** or **not confirmed** on its own evidence:
   - does the telemetry the finding cites actually say what the finding
     claims? Re-run the query yourself against the local stack.
   - does the code actually do what the finding says it does? Open the
     file and the line.

   A finding is confirmed when both hold. It is not confirmed when the
   evidence does not support it, when the cited query returns something
   else, when the code does not do that, or when the finding is a
   restatement of another one already counted. Telemetry gaps count as
   findings like any other — an absent signal that really is absent is a
   confirmed finding.

   The row's grade is `confirmed / reported`. Record, for your own PR
   body, one line per finding with the ruling and why.

   Also read off: the **oddyssey version** the run used
   (`odd_config_get`'s `version`, or the installed `oddyssey-mcp`), and
   the **run duration**.

8. **Tear down.**
   `docker compose -f docker-compose/llms-benchmark/docker-compose.yml down -v`.
   Leave the oddyssey stack up — it is the user's, and it was probably
   up before the run.

9. **Put the tree back, then leave the branch behind.** The run
   installed a package into the working tree and produced an
   observation report; **none of it ships**:
   - delete the untracked files step 3's install created and revert its
     edits to tracked files, against the `git status --porcelain` you
     recorded — leave anything that existed before untouched;
   - delete the observation report the run stored. It names the defects
     it found, which is exactly what must not enter this repository:
     the next model to be benchmarked can read it. Keep its content in
     your own context for step 10 and let the file go;
   - `git checkout main`, then delete the work branch
     (`git branch -D`) — it never gets pushed.

10. **Open the results PR from a clean base.** From `main`, freshly
    pulled, create `docs/llms-benchmark-<model-slug>` and make **one**
    change: the model's row in the results table of
    `.llms-benchmark/README.md`.
    - the model is not in the table yet → append the row;
    - the model is already there → replace that row in place. The table
      carries no history: one row per model, always the latest run.

    Columns: run duration, input tokens, output tokens, cache tokens,
    `confirmed / reported`, and the oddyssey version.

    The PR references its issue (`Closes #N`) like every PR in this
    repository — open one first if none covers this run. Its body
    carries the per-finding rulings from step 7, so the ratio in the
    table is auditable, and it names the opencode version and the model
    variant used. **It carries no API key and no list of the stack's
    defects** — the rulings are stated as "the report's finding N held
    up / did not hold up, because <evidence>", never as a catalogue of
    what the application gets wrong.

    Hand the PR back to the user. Do not merge it.

11. **Amend this command when the run taught it something.** An install
    step that needed another flag, a configuration key that moved, a
    token field that turned out to live elsewhere, a preflight that
    should have caught something — fix it here, in the same PR as the
    results row. A protocol that drifts silently makes two rows
    incomparable; a protocol that records its own corrections stays
    honest.
