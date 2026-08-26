# Splunk — configuration display

## Display

The `splunk` CLI has **no whoami surface**, so the context is the
target the mission provides — display it explicitly rather than
implying one:

- The instance — the `-uri https://<host>:8089` the commands will
  carry, or, when the CLI runs on the instance itself, the local
  `$SPLUNK_HOME` whose `bin/splunk` is being used.
- The user the commands authenticate as (`splunk login` session or the
  `-auth <user>:<pass>` the mission supplies) — the **username only**,
  never the password, and never a full `-auth` string echoed back.
- The app/index scope when the mission pins one.

`stack_config.splunk` is expected **empty** — the target is per-mission
and the CLI keeps no shareable context. Present-and-empty (`{}`) or
missing both display as "nothing persisted — the mission supplies the
target".

Add any `invalid_ignored` dotted names as degradations: stored value
invalid, default in use.

## Connection proof

A trivial authenticated search, per the backend's
`observability-cli-guides` reference: `splunk search '<trivial SPL>'
-maxout 1`, adding `-uri` for a remote instance. A successful response
= connected. Failure = stop and guide the login or the
`-uri`/credential inputs; never authenticate on the user's behalf.

## Change-request phrasing

- "change backend to splunk"
