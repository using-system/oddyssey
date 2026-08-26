# Splunk — what to persist

## What stack_config holds

**Nothing.** `stack_config.splunk` is expected to stay empty, and an
empty entry is the correct final state of a switch to `splunk`.

The reason differs from the other context-bearing CLIs. The `splunk`
binary ships with the instance it belongs to
(`$SPLUNK_HOME/bin/splunk`), and the target is either the instance the
binary lives on or the `-uri https://<host>:8089` a command carries.
There is no shareable, persistent context to mirror and no whoami
surface to read one from: the target is supplied **per mission**, so
storing it here would pin a value the next mission may legitimately
override.

## Where each value comes from

From the mission and the invocation, not from a stored context:

- the instance — the `-uri https://<host>:8089` the commands carry, or
  the local `$SPLUNK_HOME` whose `bin/splunk` is being used;
- the user — the `splunk login` session or the `-auth <user>:<...>` the
  mission supplies, referred to by **username only**;
- the app or index scope — when a mission pins one, and only for that
  mission.

The `splunk` Detect command references `$SPLUNK_HOME`, which is usually
unset — run it in a shell without `set -u`, as the CLI preflight
requires.

Note also that Splunk Enterprise / Cloud Platform (SPL, the `splunk`
CLI) and Splunk Observability Cloud (SignalFlow, APM) are separate
products with separate credentials. Nothing about that distinction is
stored here either; the `splunk.md` reference in the
`observability-cli-guides` skill owns it.

## What to ask the user

**Nothing to persist.** Do not ask for the instance host, the username,
the password, or any authentication value with the intent of storing it
— the credential lives in the CLI's login session or in the mission's
own inputs.

Asking which instance a run should target is a **mission** question, and
`check-backend-configuration` displays whatever the mission supplies.
Keep it there.

Leave `stack_config.splunk` alone.
