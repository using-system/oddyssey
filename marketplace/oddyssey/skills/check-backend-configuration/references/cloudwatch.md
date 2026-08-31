# AWS CloudWatch / X-Ray — configuration display

## Display

Two sources, labelled per line — the CLI's effective credentials and
the persisted targeting values.

**If `stack_config.cloudwatch.profile` is persisted, run every command
below (display and connection proof alike) with `--profile <profile>`**
— a bare call answers for whatever profile happens to resolve without a
flag, which on an SSO setup with no `default` is routinely none at all,
reporting a degradation on an account that is actually configured and
working.

From the `aws` CLI:

- `aws sts get-caller-identity` — the account id and the caller ARN
  (which identity the queries run as).
- `aws configure list` — the effective profile, region, and where each
  came from (env, config file, IAM role). Show the source column: a
  region coming from an env var is the usual explanation for queries
  hitting the wrong one.

From `stack_config.cloudwatch` (per `odd_config_get`):

- `region` — the region the mission queries, when pinned separately
  from the CLI's effective one.
- `profile` — the named `aws` CLI profile the mission runs under, when
  no `default` profile resolves on its own (the SSO norm).
- `log_group` — the CloudWatch Logs group the mission reads for
  application logs.
- `metrics_log_group` — the CloudWatch Logs group metrics arrive
  through as Embedded Metric Format, when the account exports them that
  way rather than writing directly to the CloudWatch metrics API. May
  equal `log_group`, may not — display both, never assume one covers
  the other.
- `xray` — the X-Ray context values the mission needs (group or
  sampling target), when persisted.

Every field the user did not persist is listed as "not persisted — the
mission will ask", and a present-but-empty `stack_config.cloudwatch`
(`{}`) means exactly that for all of them: a valid state, not an error.
Call out a persisted `region` that differs from the CLI's effective
one — the query targets the persisted value.

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

## Connection proof

`aws sts get-caller-identity --profile <profile>` when
`stack_config.cloudwatch.profile` is persisted (see Display above),
plain `aws sts get-caller-identity` otherwise. It needs no permissions
and returns the account and ARN, so a success is proof the credentials
resolve and work.

On failure, check the single most likely real-world cause **first**: no
`default` profile resolves, even though a named one is fully configured
and working. `aws configure list-profiles` enumerates what exists
locally; retry the identity check with `--profile <name>` (or `export
AWS_PROFILE=<name>`) before concluding nothing is configured — an
error naming `NoCredentials` and suggesting `aws login` reads like "not
set up at all" but is routinely just "no default among the profiles
that do exist," even when there's only the one. Only after that comes
up empty is it a genuine stop-and-guide (profile creation, SSO login,
env vars) — never run the login for the user, never echo an access key.

## Change-request phrasing

- "persist log group <name> for cloudwatch"
- "clear the log group for cloudwatch"
- "use profile <name> for cloudwatch"
- "persist metrics log group <name> for cloudwatch"
- "change backend to cloudwatch"
