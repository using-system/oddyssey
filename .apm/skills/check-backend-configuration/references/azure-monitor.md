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
- `resource_group` — the resource group holding the workspace.
- `workspace` — the Log Analytics **customer ID** GUID, the value
  `az monitor log-analytics query` takes as `--workspace`; not the
  workspace resource name.
- `app_insights_app` — the Application Insights app, when the mission
  queries App Insights rather than the workspace.

Show each stored value next to the field it came from. Every field the
user did not persist is listed as "not persisted — the mission will
ask": a present-but-empty `stack_config.azure-monitor` (`{}`) means all
four are unset, which is a valid state, not an error. Say it plainly
when the persisted `subscription` differs from the one `az account
show` reports — the query targets the persisted one.

Add any `invalid_ignored` dotted names as degradations: stored value
invalid, default in use.

## Connection proof

`az account show` succeeding. It doubles as the context display and the
cheapest probe — unauthenticated, it fails with a "Please run 'az
login'" message. Never run `az login` for the user: guide it.

## Change-request phrasing

- "persist workspace <guid> for azure-monitor"
- "change backend to azure-monitor"
