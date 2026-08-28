# Datadog — configuration display

## Display

The Pup CLI's own session is the context: which site and org the
queries will hit.

- `pup auth list` — every stored session with its site, org, and
  expiry; the one the mission will use is the org/site pair the run
  targets (`--org`/`DD_ORG`, `--site`/`DD_SITE`).
- The credential **by name only**: which of `DD_ACCESS_TOKEN`, an
  OAuth2 session from `pup auth login`, or `DD_API_KEY` +
  `DD_APP_KEY` is set — never the value of any of them, never a
  partial or masked value. See the `datadog.md` reference in the
  `observability-cli-guides` skill for the priority order between the
  three and for the site list.

`stack_config.datadog` is expected **empty** — the CLI session already
names the site and org. Present-and-empty (`{}`) or missing both
display as "nothing persisted — the Pup session is the source".

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

## Connection proof

`pup auth status` — the cheapest call that
verifies the active credential, per the backend's
`observability-cli-guides` reference. But **the exit code is not the
signal**: pup exits 0 authenticated or not (verified on pup 1.14.0 —
`pup auth status` prints `{"authenticated": false, "org": null, ...}`
and exits 0; `pup auth test` exits 0 while reporting
`API Key: not set`). Unlike the other backends' probes (`aws sts
get-caller-identity` exits 253, `dtctl auth whoami` exits 1), a shell
exit-code check on pup proves nothing. The proof is the **output**:
connected means the status JSON carries `"authenticated": true` —
that boolean is the sole authority. `pup auth test`'s `not set` lines
corroborate a missing API-key pair, but an OAuth or bearer session
leaves those keys unset while authenticated — never rule a failed
proof on `not set` alone. `"authenticated": false` is the failed
proof: stop and guide `pup auth login` or the API/app key setup;
never authenticate on the user's behalf.

Site mismatch is silent here: a read against the wrong region returns
empty rather than failing, so show the site even when the probe passes.

## Change-request phrasing

- "change backend to datadog"
