#!/usr/bin/env bash
# Merge main's CURRENT head into the checked-out PR head, so the PR gate tests
# what would land now (CI-STALE-MERGE-REF, 27 Oct 2026).
#
# GitHub's own merge commit (refs/pull/N/merge: `github.sha` and the default
# checkout on a pull_request event) is built when the PR head is pushed and is
# not rebuilt when main moves. Run 40354117904 (#1876) tested
# "Merge 149c4b3d into 1aaeed54" while main was seven merges on, at 15bf09c1.
#
# A conflict fails here: merge origin/main into the branch, resolve, push,
# re-label. Writes `main=<sha>` (the main it merged) to $GITHUB_OUTPUT.
#
# Run from a checkout of the PR head with history (a merge needs the base).
set -euo pipefail
git fetch --no-tags --quiet origin +refs/heads/main:refs/remotes/origin/main
main=$(git rev-parse refs/remotes/origin/main)
head=$(git rev-parse HEAD)
# The runner has no git identity; the merge commit is local and never pushed.
if ! git -c user.name=sorento-ci -c user.email=ci@example.invalid merge --no-edit origin/main; then
  echo "::error title=PR head does not merge into main::$head conflicts with main $main: merge origin/main into the branch, resolve, push, then re-label"
  git diff --name-only --diff-filter=U | sed 's/^/  conflict: /'
  exit 1
fi
echo "testing PR head $head merged into main $main: tree $(git rev-parse 'HEAD^{tree}')"
if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "main=$main" >> "$GITHUB_OUTPUT"; fi
