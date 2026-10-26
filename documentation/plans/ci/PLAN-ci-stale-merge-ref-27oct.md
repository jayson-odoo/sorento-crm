# PLAN: the PR gate tests the PR head merged into main's CURRENT head (CI-STALE-MERGE-REF)

Status: in progress (small fix track: CI workflow + one CI script, no migration, no product code)

UAC: `ci-stale-merge-ref-27oct-acceptance-criteria.md` (alongside).

## Problem (measured)

On a `pull_request` event `github.sha` is GitHub's test merge commit (`refs/pull/N/merge`). GitHub
builds it when the PR head is pushed and does not rebuild it when main moves. The PR gate used it
three ways:

- `changes` / "Detect changed areas" keys the `pr-validated-tree-<tree>` marker lookup on that
  commit's tree (`PUSH_AFTER: ${{ github.sha }}`, `.github/workflows/deploy.yml:448`, lookup
  :474-482). Its comment (:467) assumes a re-label means "no new commit on either side".
- `lean-gate` (`PR gate`) checks out the default ref, that merge commit (:1504), and marks its tree.
- `changes` checks out the same commit sparsely for the import-based test selection (:677).

Run 40354117904 (#1876, 26 Oct 15:55Z): the PR gate checked out
`Merge 149c4b3dae into 1aaeed54ae` and "Detect changed areas" printed `merge tree 1a90bf70...
already passed a PR gate: nothing to test`. Main's head at that moment was 15bf09c181, seven
first-parent merges after 1aaeed54ae (1eb05ad15d, 494ee14424, 242cb0d554, 3ce30c5c85,
4b56708771, 36f571df3b, 15bf09c181). The PR merged having been tested against none of them.
Runs 40351072730 (#1878, `into 36f571df3b`) and 40333616875 (#1879, `into 1eb05ad15d`) show the
same marker skip.

## Fix

1. `changes`, pull_request case: read main's head (`git/ref/heads/main`) and the merge commit's
   parents (`git/commits/$PUSH_AFTER`). The marker counts only when parent 1 is main's head now
   and parent 2 is the PR head (`github.event.pull_request.head.sha`). Otherwise, or on any failed
   lookup, the gate tests (fail-safe direction, as today).
2. New `scripts/ci_merge_main.sh`: fetch `origin/main`, `git merge --no-edit origin/main` into the
   checked-out PR head, fail with an `::error` naming the conflicting files on a conflict, print
   what was tested, write `main=<sha>` to `$GITHUB_OUTPUT`.
3. `lean-gate`: Checkout `ref: ${{ github.event.pull_request.head.sha }}` (empty off a PR, so a
   release checks out exactly as before), then a PR-only step runs the script before every gate.
   The alembic head, PII, tests, tsc and vitest then run on the live merge, and "Mark this tree as
   validated" (`git rev-parse 'HEAD^{tree}'`) keys the marker on that merge's tree. The vitest
   `--changed` base becomes the merged main (the PR's own change) instead of the payload's
   `base.sha`.
4. `changes` selection checkout: same `ref:`, full (blobless, sparse already implies
   `blob:none`) history on a PR only, and the same script before "Select backend tests by import",
   so the selection reads the tree the gate tests.

Unchanged: every gate, the gitleaks range (base..head of the PR's own commits), the merge_group
trigger, every push / release / deploy path (each new `ref:` / `fetch-depth` / step is empty or
skipped off a pull_request).

## Known limit

When GitHub's cached merge commit is stale, a re-label on an unchanged head and main re-tests
(the marker is keyed on the live merge tree, which `changes` cannot compute without a merge). That
costs minutes, never correctness; it is the price of not adding a checkout to every `changes` run.

## Tests

`sorento_crm_backend/tests/test_ci_docs_only_filter.py` (the workflow logic executed as it ships)
plus a script test that runs `scripts/ci_merge_main.sh` against a throwaway git remote: clean
merge holds both sides, conflict fails loudly, an up-to-date head is unchanged.

## Proof run

One throwaway draft PR labelled by crew after main moves: the PR gate log must show
`Merge ... into <main's head at label time>` from the script, and no marker skip on a stale
GitHub merge commit.
