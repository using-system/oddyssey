# Datadog — what to persist

## What stack_config holds

**Nothing.** `stack_config.datadog` is expected to stay empty, and an
empty entry is the correct final state of a switch to `datadog`.

The Pup CLI carries its own session, and that session is what names the
**site** (`datadoghq.com`, `datadoghq.eu`, `us3`, `us5`, `ap1`, …) and
the **org** the queries hit. Persisting a site or org here would
duplicate the session and diverge from it the moment the user logs in
elsewhere — while the CLI's own session is still what the query
actually uses.

## Where each value comes from

From the Pup session, read at use time:

- `pup auth list` — every stored session with its site, org, and
  expiry; the org/site pair a run targets is the one selected via
  `--org`/`DD_ORG` and `--site`/`DD_SITE`.

The credential is whichever of the documented mechanisms is in play — an
OAuth2 session from `pup auth login`, or the environment-variable
credentials the CLI reads. Refer to it **by name only** (which variable
is set, which login was used); never read, echo, mask, or persist a
value. The `datadog.md` reference in the `observability-cli-guides`
skill owns the priority order between them.

## What to ask the user

**Nothing about targeting.** Do not ask for the site, the org, the API
key, or the application key — the first two belong to the session and
the last two are secrets that never enter this configuration.

One thing is worth saying out loud after the switch, because it fails
quietly: a session pointed at the wrong site returns **empty results
rather than an error**. So confirm with the user that the session's site
is the region their data lives in, and let
`check-backend-configuration` display it. That is a confirmation, not a
value to store.

Leave `stack_config.datadog` alone.
