# AWS CloudWatch / X-Ray — configuration display

## Display

Two sources, labelled per line — the CLI's effective credentials and
the persisted targeting values.

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
- `log_group` — the CloudWatch Logs group the mission reads.
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

`aws sts get-caller-identity`. It needs no permissions and returns the
account and ARN, so a success is proof the credentials resolve and
work. Failure = stop and guide (profile, SSO login, env vars) — never
run the login for the user, never echo an access key.

## Change-request phrasing

- "persist log group <name> for cloudwatch"
- "change backend to cloudwatch"
