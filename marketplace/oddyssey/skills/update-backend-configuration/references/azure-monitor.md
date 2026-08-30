# Azure Monitor — what to persist

## What stack_config holds

`az` is a **general-purpose** CLI: its context says who you are and
which subscription is active, and nothing at all about where the
telemetry lives. A Log Analytics query needs a workspace GUID that no
`az` context carries. So `stack_config.azure-monitor` holds the
targeting information the missions would otherwise ask for on every
single run:

- `subscription` — the subscription the missions query, by name or id.
- `resource_group` — the resource group holding the workspace. The
  Application Insights component may well sit in another one; this field
  pins the workspace's.
- `workspace` — the Log Analytics workspace's **customer ID** GUID: the
  value `az monitor log-analytics query` takes as `--workspace`. Not the
  workspace resource name, which looks plausible in the same slot and
  fails.
- `app_insights_app` — the Application Insights component's **appId**
  GUID: the value `az monitor app-insights query` takes as `--app` with
  no `-g` beside it. Not the resource name, which needs a resource group
  to mean anything, and not the instrumentation key.

The workspace and the component are two different things and the runs
need both. A workspace holds logs and platform metrics; the
`requests`/`dependencies` tables that carry distributed tracing exist
only once an Application Insights component is provisioned and grafted
onto that workspace. Persisting a workspace and no component configures
a run that can read logs and cannot see a single trace — which is why
`app_insights_app` is asked for on every azure-monitor pass rather than
waited for.

All four are identifiers and names. None of them is a secret: the
credential behind `az` stays in its own auth store, established by
`az login`, and is never copied here.

## Where each value comes from

- `subscription` — `az account show` reports the active subscription's
  name, id, and tenant. If the missions target that one, take it from
  there; persist it anyway, because "active" is machine state that
  changes under you and the stored value is what pins the target.
- `resource_group` — list the workspaces the identity can see and read
  the group each sits in. The exact listing command comes from the
  `azure-monitor.md` reference in the `observability-cli-guides` skill,
  or from `az monitor log-analytics workspace --help` — never from
  memory.
- `workspace` — `az monitor log-analytics workspace show -g
  <resource_group> -n <name> --query customerId -o tsv` is the command
  that turns a workspace name into the GUID to store. Deriving it is
  strictly better than asking: users know their workspace by name and
  rarely by GUID.
- `app_insights_app` — `az monitor app-insights component show --app
  <name> -g <resource_group> --query appId -o tsv` turns a component
  name into the GUID to store, exactly as the workspace command turns a
  workspace name into its customer ID. When the user does not know which
  component to name, list them first —
  `az monitor app-insights component show -g <resource_group> --query
  "[].{name:name, appId:appId}" -o table` — and note there is no
  `component list` subcommand; the discovery block in the
  `observability-cli-guides` reference has the full command set.
  **An empty listing is not an answer.** A component often sits in a
  different resource group from the workspace it writes to, and a
  group-scoped listing that finds nothing returns an empty table with
  exit 0 — indistinguishable, at a glance, from a subscription that has
  no Application Insights at all. Always widen to the subscription-wide
  form (`component show --query "[].{name:name, rg:resourceGroup,
  appId:appId}" -o table`, which reports each component's own group)
  before concluding there is none. Concluding "no Application Insights"
  from a narrow listing persists the degradation this field exists to
  prevent.

## What to ask the user

Ask for **every value that is not derivable** from `az account show` and
the list commands above, one question rather than four:

> Which subscription, resource group, Log Analytics workspace, and
> Application Insights resource should the runs query? (I can resolve
> both GUIDs from their names, and list the candidates if you are
> unsure.)

The Application Insights part of that question is asked on **every**
azure-monitor pass, not only when the user brings it up first. It is
the one value a user is least likely to volunteer and the one whose
absence costs the most — see above.

If `az` is not yet logged in, do not turn this into an auth flow: state
what will be asked once the CLI answers, persist what the user does
supply, and let `check-backend-configuration` guide the login.

**"There is no Application Insights here" is an answer, not a blank** —
once the user says so outright, or the subscription-wide listing has
come back empty too. Some Azure Monitor deployments genuinely collect
infrastructure logs and platform metrics and nothing else. Take that
answer, persist nothing for
`app_insights_app`, and say plainly what it costs: the runs will read
logs and metrics and will report distributed tracing as a telemetry gap.
Do not persist a placeholder to fill the slot, and do not offer to
create the resource — provisioning Azure infrastructure is not this
skill's job.

A value the user cannot supply yet is left unpersisted — that field
simply reads "not persisted — the mission will ask". Every field except
`app_insights_app`, whose unset state is the named degradation stated
above and never a neutral blank. Never invent a GUID, never guess a
resource group from a name that looks similar, and never persist a
partial GUID.
