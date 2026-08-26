# AWS CloudWatch / X-Ray — what to persist

## What stack_config holds

Same rationale as Azure Monitor: `aws` is a **general-purpose** CLI. A
profile says which credentials and which region — it never says which
log group holds the service's logs or which X-Ray group the missions
read. So `stack_config.cloudwatch` holds the targeting information:

- `region` — the region the missions query, pinned separately from
  whatever the CLI's effective region happens to be.
- `log_group` — the CloudWatch Logs group the missions read. When the
  services follow a convention rather than one fixed group, store the
  **naming pattern** instead (`/aws/ecs/<service>`,
  `/aws/lambda/<function>`) — a pattern the mission can expand beats a
  single group that only covers one service.
- `xray` — the X-Ray group or context the missions use, when X-Ray is
  part of the picture. Omit it entirely when it is not.

Region names, group names, and patterns — all identifiers, none of them
a secret. Access keys, session tokens, and SSO sessions stay where the
`aws` CLI keeps them and are never copied into the configuration.

## Where each value comes from

- `region` — `aws configure list` prints the effective profile, region,
  and the **source** of each (env var, config file, IAM role). Take the
  region from there when it is the one the missions want; the source
  column is also what explains a surprising value.
- `log_group` — `aws logs describe-log-groups --query
  'logGroups[].logGroupName'` lists what the identity can actually see;
  pick the group (or read the convention off the list) with the user.
- `xray` — `aws xray get-groups` names the configured groups. Skip
  unless the user says traces come from X-Ray.

`aws sts get-caller-identity` is the identity check, not a source of
targeting values — it belongs to the connection proof in
`check-backend-configuration`.

## What to ask the user

Ask for whatever `aws configure list` and the list commands above do not
settle, in one question:

> Which region and which log group (or log-group naming pattern) should
> the runs read? Is X-Ray part of it, and if so which group?

Persist only what the user confirms. An unpersisted field reads "not
persisted, the mission will ask", which is a valid state — never guess a
log group from a service name, and never persist a region simply because
it is the one the CLI defaults to today when the user has not said it is
the right one.
