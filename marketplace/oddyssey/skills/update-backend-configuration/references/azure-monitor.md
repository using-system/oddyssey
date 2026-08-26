# Azure Monitor — what to persist

## What stack_config holds

`az` is a **general-purpose** CLI: its context says who you are and
which subscription is active, and nothing at all about where the
telemetry lives. A Log Analytics query needs a workspace GUID that no
`az` context carries. So `stack_config.azure-monitor` holds the
targeting information the missions would otherwise ask for on every
single run:

- `subscription` — the subscription the missions query, by name or id.
- `resource_group` — the resource group holding the workspace.
- `workspace` — the Log Analytics workspace's **customer ID** GUID: the
  value `az monitor log-analytics query` takes as `--workspace`. Not the
  workspace resource name, which looks plausible in the same slot and
  fails.
- `app_insights_app` — optional, and only when the missions query
  Application Insights rather than the workspace.

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
- `app_insights_app` — only when the user says App Insights is the
  target; take the command that names the app from the same
  `observability-cli-guides` reference, or from
  `az monitor app-insights --help`.

## What to ask the user

Ask for **every value that is not derivable** from `az account show` and
the list commands above, one question rather than four:

> Which subscription, resource group, and Log Analytics workspace should
> the runs query? (I can resolve the workspace GUID from its name.)

If `az` is not yet logged in, do not turn this into an auth flow: state
what will be asked once the CLI answers, persist what the user does
supply, and let `check-backend-configuration` guide the login.

A value the user cannot supply yet is left unpersisted — that field
simply reads "not persisted, the mission will ask". Never invent a GUID,
never guess a resource group from a name that looks similar, and never
persist a partial GUID.
