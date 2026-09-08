---
description: Benchmark one LLM on the llms-benchmark demo stack - drive it through opencode on the stored scenario, grade the observation report it produced, and propose its row of the results table
---

Run the whole llms-benchmark protocol for one model, end to end, and
come back with a pull request adding or replacing that model's row in
`.llms-benchmark/README.md`.

The question this benchmark answers: **how much of what a model reports,
after observing a running stack it has never seen, actually holds up?**
The demo stack under `.llms-benchmark/src/` is deliberately defective,
and what it gets wrong is written down nowhere in this repository — not
in a comment, not in a README, not in an issue. There is no answer key to
compare against, and that is on purpose: the model is graded on evidence,
the same way you would grade a colleague's incident report.

- Arguments: $ARGUMENTS
- Expected field: the **model** to benchmark, as its OpenRouter id
  (`anthropic/claude-sonnet-5`, `openai/gpt-5-mini`,
  `google/gemini-3.5-flash-lite`, ...). That is the only input. Ask for
  it if it is missing and stop until you have it.

**Never ask for an API key, and never handle one.** Both credentials this
protocol needs are prerequisites the person running it sets up once, and
the preflight checks them rather than requesting them. No key is ever
passed as an argument, written to a file, echoed back, or allowed near a
commit, a PR body, an issue, or a report.

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
     scenario every row of the table was produced with);
   - **opencode already has OpenRouter configured**: `opencode models
     openrouter` lists the model id you were given. If it does not, stop
     and say so — configuring the provider is the user's to do, once, and
     spending a run to discover it is missing is worse than refusing to
     start;
   - **`docker-compose/llms-benchmark/.env` exists and carries a
     non-empty `OPENAI_API_KEY`** — the demo agent's own model key, which
     `docker compose` reads on its own from that file. Check its
     presence, never its value, and never print it. The file is
     gitignored; `.env.example` next to it says what goes in.

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
     this command: it deploys files into the working tree — `.opencode/`,
     `.agents/skills/`, `opencode.json`, and an edit to `.gitignore` —
     and step 9 has to put the tree back exactly as it was.

4. **Select the model.** Nothing to configure: the provider is already
   set up (preflight), and the model and effort are passed on the command
   line in step 6 (`--model openrouter/<model>`, `--variant medium`),
   never persisted into a config file.

5. **Recreate the demo stack — never reuse a running one.**

   ```
   docker compose -f docker-compose/llms-benchmark/docker-compose.yml down -v
   docker compose -f docker-compose/llms-benchmark/docker-compose.yml up -d --build
   ```

   `down -v` matters: it drops the catalog volume. Without it a previous
   run's orders and its service instance ids sit inside the window this
   run observes, and two rows stop being comparable. Wait for the three
   containers to be healthy and prove it with one request to each of the
   three services.

6. **Run the mission.** Record the UTC timestamp **before** launching —
   step 7 needs it to identify the session. Then one headless opencode
   run, from the repository root, on the work branch:

   ```
   caffeinate -i opencode run --model openrouter/<model> --variant medium \
     --format json --auto --title "llms-benchmark <model>" \
     "<the mission prompt below>" < /dev/null
   ```

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
   four of its inputs itself — the services, the scenario, the depth and
   the stack — rather than naming some of them in prose around it:

   ```text
   /odd-observe observe the three services llmbench-api, llmbench-mcp and
   llmbench-agent by running .llms-benchmark/benchmark/llmbench-store-load/
   at full depth on the local stack
   ```

   Each of the four is named on purpose:
   - **the three services**, so the mission never has to guess its own
     scope from what happens to be running on the machine, and so the
     report's frontmatter carries all three;
   - **the scenario**, because every row of the table was produced from
     that same replayed traffic, and an ad-hoc one would grade the
     traffic instead of the model;
   - **full depth**, because `quick` queries metrics and traces only: a
     run under it can reach performance anomalies and nothing else,
     whatever the model is worth;
   - **the local stack**, because a mission that leaves it unsaid picks
     up whatever backend the configuration happens to carry.

   Add exactly two things to that line and nothing else: that the
   services' sources are under `.llms-benchmark/src/`, and that you want
   **every kind of anomaly, not only the slow ones** — performance
   problems, outright errors, wrong behavior, and telemetry that is
   missing or lying, across all four signals.

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
   stdout until it finishes, so read these instead:

   - `~/.local/share/opencode/log/opencode.log`, filtered to **this
     run's id** (the `run=<id>` on its `message=init` line; another
     opencode session of the user's writes to the same file, so never
     read the tail unfiltered). Its last line is the current activity,
     and its `pattern="..."` entries name the commands being run.
   - **`level=ERROR` in the run's log lines, on every poll.** This is the
     check that matters and it is cheap. A provider can fail a stream and
     leave the connection open: the process stays alive, its child stays
     alive, the socket stays ESTABLISHED, stderr stays empty, and nothing
     moves for as long as you let it. One run sat like that for nine
     minutes after two `stream error` lines and a 503, while every
     liveness check said it was working. Treat a stream opened with no
     completion and no new log line for several minutes as a stall, and
     say so instead of reassuring.
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
     when the drive ends. The drive's own boundaries are what step 7
     needs; where to read them is settled there.
   - the session in the store (step 7's identification): its `cost` and
     token counters climb while the run works.

   Report progress to the user as it crosses the phases rather than at
   the end: preflight done, the k6 drive started and finished, the
   telemetry queries under way, the report written. Name what you are
   waiting on, and if a phase stalls with no new log line for several
   minutes, say so instead of waiting silently.

   Never `pkill` by a pattern that could match another opencode process:
   the user may be running their own session at the same time. Kill by
   the PID you launched, or not at all.

7. **Read the run's cost from the opencode session store — and make sure
   it is the right session.** The store is
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
     to the cent at 200,000 where the field said 272,000. If it still
     does not reconcile, say so instead of publishing the number.

   Also read off:
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
   - the **oddyssey version** (`odd_config_get`'s `version`);
   - how many of the four signals the run actually queried — count
     `gcx metrics` / `traces` / `logs` / `profiles` invocations in
     `~/.local/share/opencode/log/opencode.log` for this run's id, and
     corroborate with the run's scratch files, since a run that queries
     through helper scripts logs fewer invocations than it makes.

8. **Grade the report — this is your job, not the model's.**

   **First, check the run actually drove the scenario.** The report's
   frontmatter window must fall *after* your launch timestamp, and its
   mode must be a driven one. A run that reads `mode: post-hoc`, or whose
   window starts before it did, graded somebody else's traffic — one did
   exactly that, declaring a post-hoc analysis because it believed it
   could not start a stack that was already running and answering. That
   run produces **no row**: re-run it with the identical mission (changing
   the mission would invalidate every other row), and if it declines
   again, "did not drive the scenario" is its result.

   Then read the observation report the run stored under
   `.odd/observe-run-reports/`
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

   A finding is confirmed when both checks hold. It is not confirmed when
   the evidence does not support it, when the cited query returns
   something else, when the code does not do that, or when the finding is
   a restatement of another one already counted. A finding whose numbers
   are exact but which the report itself labels uncertain still counts:
   grading honesty down would only teach models to hide it.

   The row's grade is `confirmed / reported`. Record, for your own PR
   body, one line per finding with the ruling and why.

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
     up before the run.
   - **delete the run's scratch directory under the system temp dir**
     (`$TMPDIR/opencode/`), every run's, not only this one's. Runs name
     that directory themselves and the names collide: one run of #505
     picked a name an earlier session had already used and inherited 248
     files — another model's query outputs, its trace dumps and its
     analysis scripts. That run happened never to read them, which was
     luck, not design: a single `ls` of its own scratch would have handed
     it a worked answer key, which is exactly what step 9 refuses to let
     the observation report carry into the repository. The directory is
     the same hazard with none of the protection, so clear it, and clear
     it after the run rather than during — the run writes its own k6
     summary there.
   - delete the untracked files step 3's install created and revert its
     edits to tracked files, against the `git status --porcelain` you
     recorded — leave anything that existed before untouched, the
     gitignored `.env` included. Delete what the install added, never the
     directory that holds it: the install writes `.agents/skills/`, but
     `.agents/` also holds the tracked `plugins/` build artifact, and
     removing the parent takes it with it. `git status --porcelain` must
     come back empty afterwards — that is the check, not the deletion;
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
      `docs/llms-benchmark-<model-slug>` and make **one** change: the
      model's row in the results table of `.llms-benchmark/README.md`.
      The model is not in the table yet → append the row; already there →
      replace that row in place. The table carries no history: one row
      per model, always the latest run.

    **Two tables, not one.** Seventeen columns scroll the model name off
    the screen and the rows stop being readable, and GitHub keeps no CSS
    to pin a column. So:

    - a **headline table** of eight columns — rank, model, oddyssey
      version, `confirmed / reported`, the findings by kind under a
      single `Telemetry / Perf / Behavior` header written `X / X / X`,
      total duration, cost, and cost per confirmed finding. It fits
      without scrolling and answers the question on its own. The version
      sits third because it says which protocol a row was taken under,
      which a reader needs before any number to its right means anything;
    - a **detail table** inside a `<details>` block — the three phase
      durations, turns, median turn latency, input / output / cache
      tokens, and signals. Round the token counts (`30.0M`, `79k`): the
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

    The PR body carries the per-finding rulings from step 8, so the ratio
    is auditable, and it names the opencode version and the model variant
    used. It also notes three things the table has no column for: how
    many source files the run read **before** the drive, whether it drove
    any traffic of its own outside the stored scenario, and whether its
    report carries a replayable verification protocol. **It carries no API key and no list of the stack's defects** —
    the rulings read as "the report's finding N held up / did not hold
    up, because <evidence>", never as a catalogue of what the application
    gets wrong.

    Hand the PR back to the user. Do not merge it.

11. **Amend this command when the run taught it something.** An install
    step that needed another flag, a configuration key that moved, a
    token field that turned out to live elsewhere, a preflight that
    should have caught something — fix it here, in the same PR as the
    results row. A protocol that drifts silently makes two rows
    incomparable; a protocol that records its own corrections stays
    honest. A change that alters what a run measures invalidates the
    rows taken before it: say so, and re-run them.
