# Azure Monitor — configuration display

## Display

Two sources, and every line says which one it came from — the CLI
identity and the persisted targeting values are different facts and a
mismatch between them is exactly what this display exists to catch.

From `az account show` (the CLI's own context):

- the active subscription (name and id) and the tenant.

From `stack_config.azure-monitor` (persisted by the user through
`odd_config_set`, per `odd_config_get`):

- `subscription` — the subscription the mission queries, when it is
  pinned separately from the CLI's active one.
- `resource_group` — the resource group holding the workspace; the
  Application Insights component may sit in another one.
- `workspace` — the Log Analytics **customer ID** GUID, the value
  `az monitor log-analytics query` takes as `--workspace`; not the
  workspace resource name.
- `app_insights_app` — the Application Insights component's **appId**
  GUID, the value `az monitor app-insights query` takes as `--app`; not
  the component's resource name.

Show each stored value next to the field it came from. Every field the
user did not persist is listed as "not persisted — the mission will
ask": a present-but-empty `stack_config.azure-monitor` (`{}`) means all
four are unset, which is a valid state, not an error. Say it plainly
when the persisted `subscription` differs from the one `az account
show` reports — the query targets the persisted one.

`app_insights_app` is the one exception to that neutral wording. A
workspace carries logs and platform metrics; distributed tracing lives
in the `requests`/`dependencies` tables, which exist only inside an
Application Insights component. So when `app_insights_app` is unset,
the line is a **named degradation**, not a shrug:

> no Application Insights configured — `requests`/`dependencies` and the
> Profiler are unavailable, and the run will see Log Analytics tables
> only. Distributed tracing will be reported as a telemetry gap.

The mission carries that sentence into the report's telemetry gaps. Say
it whether the user declined the resource or was never asked: the
consequence for the run is identical, and stating it is what stops an
observation from quietly degrading into a logs-only run that reads like
a complete one.

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

## Connection proof

This section defines the probe the skill's step 3 runs, and it has
**two parts**, because `az` answering says nothing about whether the
persisted target exists. A successful identity proof alone is not a
connected verdict when `app_insights_app` is persisted: both parts must
pass. The second is skipped — not failed — when nothing is persisted to
check.

**Identity** — `az account show` succeeding. It doubles as the context
display: unauthenticated, it fails with a "Please run 'az login'"
message. Never run `az login` for the user: guide it.

**Targeting** — when `app_insights_app` is persisted, prove the GUID
resolves before a mission spends a run on it:

```bash
az monitor app-insights query --app <app_insights_app> \
  --analytics-query "print 1" --offset 5m -o none
```

Exit 0 is the proof (about a second against a live component). This
queries the data plane rather than reading the resource through ARM,
which is deliberate: it proves the access a mission actually needs, and
an identity with query rights but no ARM read still passes. The appId
resolves on the data plane and carries no subscription, so a
persisted/active subscription mismatch does not affect this proof —
**do not add `--subscription`** to reconcile it (verified: the probe
returns exit 0 even under a subscription that does not exist).

Two things this command will not tolerate, both verified on az 2.77.0:
**never add `-g` beside the GUID** — the pair fails with exit 3 even
when both values are correct — and never substitute the component's
resource name. A name would need a `-g` this probe does not pass, and
proving a name proves nothing about the GUID that is actually stored.
The `--app` table in the `observability-cli-guides` reference has the
full matrix.

**Read the error line before diagnosing — the exit code alone is not
enough.** az reserves exit **3** for one thing, a resource that does not
exist (`ResourceNotFoundError`), and funnels almost everything else into
exit **1**: authorization failures, expired credentials, network and
proxy errors, throttling and service errors alike
(`azure/cli/core/util.py`, az 2.77.0 — `exit_code = 1` is the default
and `3` is set only for `ResourceNotFoundError`). So:

- **Exit 0** — connected, the persisted appId resolves and is queryable.
- **Exit 3** — the appId does not resolve. This is the wrong-value case:
  stop, report the persisted GUID as unresolvable, and route to
  `update-backend-configuration` to correct it. Catching it here is far
  cheaper than in an observation that returns empty trace queries and
  looks merely quiet.
- **Exit 1** — read the message, and mind that az may wrap it in an
  "unexpected error … Here is the traceback" banner: the diagnosis is
  the `ERROR:` line, never the Python stack under it. `The Application
  Insight is not found. Please check the app id again.` means the
  persisted value is not an appId GUID — typically the component's
  resource name, which this probe cannot resolve without a `-g` it does
  not pass. That is a wrong value: route once, exactly as exit 3. An
  authorization/`Forbidden` message instead means the identity is
  authenticated but lacks **query rights** on this component — a
  permissions problem, **not** a wrong value: re-persisting the same
  correct GUID will not fix it, so say that plainly and name the missing
  access rather than routing. A re-authentication message (`AADSTS…`, or
  a "run `az login`") is an **identity** failure surfacing late: `az
  account show` reads the local profile and never touches the network,
  so it returns 0 on a stale token and only this probe reveals it. Hand
  it to the identity guidance above — do not retry it, and do not route
  it to `update-backend-configuration`, which cannot fix a login.
  Anything else (connection, proxy, throttling, service error) is
  reported verbatim and retried; never rewrite it as a targeting
  failure.
- **Exit 2** — az could not parse the command. That is a defect in the
  command as written, not a configuration problem and never a wrong
  stored value: fix the invocation against the reference.

Exit 1 is a bucket, not a diagnosis: mistaking a 403 for a bad GUID
sends the user to re-persist a value that was right all along, and
mistaking a stored name for a transient error retries it forever.

A failed targeting proof is **not** a "CLI not configured" error and is
never reported as one: the binary is installed, `az` is authenticated,
and the backend answered. What is wrong is the stored value or the
access to it — say it in those terms. Route to
`update-backend-configuration` **once** for a corrected value; if the
proof fails again on the value that came back, stop and report rather
than bouncing between the two skills.

`app_insights_app` unset is **not** a failed proof: it is the
degradation stated in the display above, and the mission proceeds
logs-only having said so.

## Change-request phrasing

- "persist workspace <guid> for azure-monitor"
- "persist app insights <name-or-guid> for azure-monitor"
- "clear the workspace for azure-monitor"
- "change backend to azure-monitor"
