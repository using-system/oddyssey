---
name: package-layout
description: Where this package is installed and what each part of it is - every skill, its reference files, its scripts, and the sibling directories the install carries. Use when a mission block needs the skills' directory, when a contract must name a reference or a script by path, or when anything is about to look for the package on disk. The answer comes from the script's own location, so it is exact wherever a host installed the package, and nothing has to be searched for or written down in advance.
---

# Where the package is

A host installs this package wherever it likes. Nothing downstream can
know that path in advance, and everything downstream needs it: a mission
block's `Skills:` line, a contract pointing at a reference file, an
agent about to run a skill's script.

Working it out is not a task for an agent. One that tries globs the
repository, opens whatever it meets on the way, and spends turns on it
before any work begins — measured, in one observation preflight: 34 file
reads and 13 globs against 16 shell commands, including an unrelated
command file it found while looking.

## Ask the installation where it is

```bash
python3 <this skill's directory>/scripts/layout.py              # the whole map
python3 <this skill's directory>/scripts/layout.py --skill <name>   # one skill
python3 <this skill's directory>/scripts/layout.py --json           # parseable
```

That is the whole surface — `--skill` and `--json`, nothing required —
so `--help` has nothing to add and the file has nothing to read.

It prints the skills' root and the sibling directories the install
carries, then, per skill, its `SKILL.md`, its `references/<name>.md`
and its `scripts/<name>`. `--skill <name>` narrows it to one, which is
what a mission block needs; an unknown name exits 1 and lists what is
installed.

The script sits inside the installation, so its own location is the
answer: no path is hardcoded, no directory is searched, and it costs
about fifty milliseconds. It describes an installation and never judges
one — a skill without references or scripts simply shows none.

## What to do with it

**Carry the path, never the search.** A caller that dispatches an agent
puts the skills' root in the mission block; a contract that names a
reference gives the path this script printed. An agent that receives one
opens the file; an agent that receives none runs this script rather than
looking around.

**Never write an install path into a committed file.** The paths this
prints are a machine's, and a report or a spec that quotes one is wrong
on every other machine — and, under a home directory, names the user.
