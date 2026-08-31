# AWS CloudWatch / X-Ray — what to persist

## What stack_config holds

Same rationale as Azure Monitor: `aws` is a **general-purpose** CLI. A
profile says which credentials and which region — it never says which
log group holds the service's logs, which log group its metrics arrive
through, or which X-Ray group the missions read. So `stack_config.cloudwatch`
holds the targeting information:

- `region` — the region the missions query, pinned separately from
  whatever the CLI's effective region happens to be.
- `profile` — the named `aws` CLI profile the missions run every command
  under (`--profile <name>` / `AWS_PROFILE`). SSO setups routinely have
  **no `default` profile at all** — without this, `aws sts
  get-caller-identity` fails with `NoCredentials` even though the CLI is
  genuinely configured and working under its named profile. Skip the
  field only when a `default` profile truly resolves on its own.
- `log_group` — the CloudWatch Logs group the missions read for
  **application logs**. When the services follow a convention rather
  than one fixed group, store the **naming pattern** instead
  (`/aws/ecs/<service>`, `/aws/lambda/<function>`) — a pattern the
  mission can expand beats a single group that only covers one service.
- `metrics_log_group` — the CloudWatch Logs group **metrics arrive
  through**, when the account exports metrics as Embedded Metric Format
  (EMF) log records (an OTel Collector's `awsemf`-style exporter is the
  common source) rather than writing directly to the CloudWatch metrics
  API. Good practice keeps this separate from `log_group` even though
  the two **may hold the same value** for a team that doesn't split
  them — persist whatever the account actually does, don't assume one
  group serves both. Omit entirely when metrics don't arrive via a log
  group (i.e. nothing to extract, `list-metrics` is already the whole
  story).
- `xray` — the X-Ray group or context the missions use, when X-Ray is
  part of the picture. Omit it entirely when it is not.

Region names, profile names, group names, and patterns — all
identifiers, none of them a secret. Access keys, session tokens, and SSO
sessions stay where the `aws` CLI keeps them and are never copied into
the configuration.

## Where each value comes from

- `region` — `aws configure list` prints the effective profile, region,
  and the **source** of each (env var, config file, IAM role). Take the
  region from there when it is the one the missions want; the source
  column is also what explains a surprising value.
- `profile` — `aws configure list-profiles` enumerates every named
  profile the identity has locally; `aws configure list` (or `--profile
  <name>` beside `aws sts get-caller-identity`) shows which one, if any,
  currently resolves without an explicit flag. Persist it whenever more
  than one profile exists or `aws configure list` shows nothing set for
  a bare (no-flag) call — never assume a `default` profile exists.
- `log_group` — `aws logs describe-log-groups --query
  'logGroups[].logGroupName'` lists what the identity can actually see;
  pick the group (or read the convention off the list) with the user.
- `metrics_log_group` — same listing command as `log_group`; ask the
  user which group (if any) the account's metrics exporter writes EMF
  records to, distinctly from the application-logs group. A raw EMF
  record has an `_aws.CloudWatchMetrics` key at the top level — grep a
  sample event for it to confirm a candidate group is actually the
  metrics source, don't guess from the name alone.
- `xray` — the `cloudwatch.md` reference in the
  `observability-cli-guides` skill owns the X-Ray command surface; take
  the group-listing command from there, or from `aws xray help`, rather
  than from memory. Skip the field entirely unless the user says traces
  come from X-Ray.

`aws sts get-caller-identity` is the identity check, not a source of
targeting values — it belongs to the connection proof in
`check-backend-configuration`.

## What to ask the user

Ask for whatever `aws configure list` and the list commands above do not
settle, in one question:

> Which region and profile should the runs use? Which log group (or
> log-group naming pattern) holds application logs — and is there a
> separate one metrics arrive through as Embedded Metric Format? Is
> X-Ray part of it, and if so which group?

Persist only what the user confirms. An unpersisted field reads "not
persisted, the mission will ask", which is a valid state — never guess a
log group from a service name, never assume `log_group` and
`metrics_log_group` are the same value without checking, and never
persist a region (or a profile) simply because it is what the CLI
defaults to today when the user has not said it is the right one.
