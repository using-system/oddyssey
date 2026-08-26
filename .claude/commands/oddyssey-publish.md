---
description: Cut a release - inspect the last pushed tag, pick the bump (patch, minor, or major), then tag and push; the tag push starts the whole release pipeline
---

Cut an oddyssey release. Pushing the version tag IS the release order:
the release workflow then bumps the files for exactly that version,
opens the release PR, waits for its CI, merges it, re-points the tag at
the merge commit, creates the GitHub release, and publishes to PyPI
behind the pypi environment approval.

- Arguments: $ARGUMENTS
- Expected fields (optional, free-form): the bump to apply (`patch`,
  `minor`, `major`) or an exact version (`1.8.0`). When present, skip
  the question in step 3 - the confirmation in step 4 still applies.

Steps:

1. **Preflight** - all of these must hold; stop naming the failing one
   otherwise:
   - `git fetch origin --tags --force` first, so tags and main are
     current;
   - the working tree is clean and the current branch is `main`, in
     sync with `origin/main` (not ahead, not behind);
   - read the latest version tag:
     `git tag -l 'v*' --sort=-v:refname | head -1` (no tag at all =
     first release, treat the base as v0.0.0 and say so);
   - check the latest tag's release run
     (`gh run list --workflow release.yml --limit 1`): if it FAILED,
     do not offer a new version - guide the recovery instead (fix
     main, then "Re-run all jobs" on that run - never a partial
     re-run, which would reuse a stale prepare artifact - or delete
     and re-push the tag). If it is WAITING (pending pypi approval),
     do not offer a new version either - jump straight to step 6 and
     resume that run's approval.

2. **Show what would ship**: the last tag, then
   `git log --oneline <last-tag>..origin/main`. Derive the
   recommendation from the conventional commit types: any `feat` -
   minor; else patch. Major is NEVER derived or preselected - a
   breaking release is always the user's explicit call. When a
   breaking marker (`!`) appears in the log, surface it as evidence
   that major may be warranted and let the user choose it themselves.

3. **Ask which bump to release** (unless the arguments already said):
   compute the three candidate versions from the last tag and offer
   patch / minor / major with the recommendation first, each option
   showing its resulting `vX.Y.Z`. An exact version given as argument
   must be strict `X.Y.Z` AND greater than the last tag - reject
   anything else (the workflow only gates the shape; monotonicity is
   this command's job).

4. **Confirm before firing**: show verbatim the two commands about to
   run -
   `git tag vX.Y.Z` and `git push origin vX.Y.Z` -
   and state plainly that the push starts the whole release pipeline
   (release PR, CI, merge, GitHub release, then PyPI pending the
   environment approval). Only on explicit confirmation, run both
   commands.

5. **Watch the run to the approval gate**: name the tag pushed and the
   release run, then poll `gh run view <run-id> --json status,conclusion`
   (every ~20 s, in the background when possible) until the status is
   no longer `queued`/`in_progress`:
   - `completed` + `failure` - report which job failed with its log
     pointer and the step-1 recovery guidance; stop;
   - `waiting` - the run reached the pypi environment gate: go to
     step 6.

6. **Offer the approval decision** - read the pending deployment
   first:
   `gh api /repos/<owner>/<repo>/actions/runs/<run-id>/pending_deployments`
   (it names the environment id and whether the current user can
   approve). Then ask the user - approve, reject, or defer - and act:
   - **approve**:
     `gh api -X POST .../actions/runs/<run-id>/pending_deployments --input <json>`
     with `{"environment_ids": [<id>], "state": "approved", "comment": "<short reason>"}`,
     then keep watching the run to completion and verify the outcome:
     the GitHub release exists WITH its notes (never header-only), and
     PyPI serves the version (`curl -s https://pypi.org/pypi/oddyssey-mcp/json | jq -r .info.version`);
   - **reject**: same call with `"state": "rejected"` - the run ends
     without publishing; the GitHub release and tag remain, say so and
     name the cleanup options (delete the release/tag, or re-run and
     approve later via a fresh dispatch on the tag ref);
   - **defer**: stop watching; the approval stays pending in the
     Actions UI ("Review deployments"), and re-running
     `/oddyssey-publish` resumes it (step 1 routes a WAITING run
     straight back here).
