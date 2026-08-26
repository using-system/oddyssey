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
     and re-push the tag).

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

5. **Hand back**: name the tag pushed, link the release run
   (`gh run list --workflow release.yml --limit 1`), and remind that
   the PyPI publish waits for the pypi environment approval in the
   Actions UI.
