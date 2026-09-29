Status: small fix track - in review (PR pending; follow-up to #1370)

# CI: fast PR gate, full suite in the merge queue, no replay on a validated push

## Ruling

Owner, 29 Sep 2026, on the options the orchestrator put forward: "I lean towards
3 for now, and also 2 okay". Option 3 is the fast PR gate with the full suite in
the merge queue; option 2 is the push to main not replaying a suite that already
passed on the same code. Both land here, in one workflow change. The ruleset
changes that make option 3 real are the owner's to apply (section "Ruleset
changes" below); the orchestrator gets the approval and applies them, this lane
changes no repo setting.

## Measured facts (29 Sep 2026, from gh)

- Every job runs on GitHub-hosted `ubuntu-latest`; no self-hosted runner. The
  account is capped at 20 concurrent jobs (Free plan).
- One `ci`-labelled PR run: 18 jobs, about 190 job-minutes. The six main backend
  shards (`test-backend`, deploy.yml matrix `shard: [1..6]`) are about 60% of
  that; the SCM shards are 3 jobs, vitest 4.
- One push to main: 23 jobs (the 18 above plus build-images x3, build-and-deploy,
  notify-owner). Main pushes replaying the full suite were about 18% of daily
  job-minutes.
- The `merge_group` trigger is wired (deploy.yml `on:`), but the
  `protect-main-branch` ruleset has no merge-queue rule and no required status
  checks. The two comments in deploy.yml that said an unlabelled PR "cannot
  merge" were therefore false; both are rewritten in this lane.
- `npm run lint` on main today: 287 errors, 706 warnings (run in this lane's
  sandbox on f0880989). Lint is NOT added as a gate: it would block every PR on
  pre-existing errors. It stays a local command until the count is zero.
- Tests that read `documentation/` as input, and `.md` fixtures inside the
  service trees, are handled by #1370 and unchanged here.

## Change

One file, `.github/workflows/deploy.yml`, no migration, no auth change.

### Fix 3: fast PR gate, full suite in the queue

- `test-backend` (six shards) gets `&& github.event_name != 'pull_request'`. It
  runs for a merge-queue entry and for an unvalidated push to main, never for a
  PR.
- `changes` gains an `scm` area flag. On a PR it is true when a path matches
  `SCM_RE`: `app/api/v1/scm/`, `app/services/scm/`, `app/modules/scm/`,
  `app/models/scm*`, `app/schemas/scm_*`, `tests/scm/`, an `alembic/versions/*scm*`
  migration, and the harness every backend test depends on (`tests/conftest.py`,
  `tests/_pg_fixture.py`, `tests/ci_excluded.txt`, `.test_durations`,
  `scripts/bootstrap_env.py`, `requirements.txt`), plus the workflow file. Off a
  PR it equals `backend`. `test-backend-scm` gates on `scm` instead of `backend`.
  54 non-scm backend files import scm services, so a change outside `SCM_RE`
  can still break an SCM test; the queue's full run is what catches that, by
  design.
- A `ci`-labelled PR therefore runs: alembic head, Changed areas, Validate
  backend imports (image build + collect + regression guards), Validate MCP
  imports (when mcp changed), Type-check frontend and the four vitest shards
  (when frontend changed), and the three SCM shards (when `scm` changed). About
  8 to 11 jobs and 50 to 80 job-minutes instead of 18 jobs and 190.
- A merge-queue entry runs everything as today (the `if` lines do not filter on
  `merge_group`).

### Fix 2: a validated push to main runs build + deploy only

- New step "Look for a prior green run of this exact code" in `changes`, push
  events only. It lists successful runs of this workflow whose `head_sha` is the
  push's SHA (a merge-queue run: the queue fast-forwards main to the commit it
  tested), and, when there is none, the merged PR(s) for the commit
  (`commits/{sha}/pulls`, `merged_at` set) and successful runs on their head
  SHA. A candidate validates only when every job in `GATES` (the 17 test jobs
  main would run, by reported name) has conclusion `success` in it; `skipped`
  does not count, so a docs-only queue run, a non-`ci` label run and a
  fast-gate PR run (six shards skipped) never validate. First qualifying
  candidate wins.
- `validated=true` zeroes every area flag (the 16 test jobs skip) while
  `docs_only` stays false, so `build-images`, `build-and-deploy` and
  `notify-owner` run: about 15 job-minutes.
- `build-and-deploy` no longer relies on the default "every need succeeded"
  rule (its needs are skipped on purpose now). It is `!cancelled()` plus
  explicit results: alembic gate and image build `success`, no need `failure`
  or `cancelled`, not docs-only. A failed gate on an unvalidated push still
  skips the deploy and still mails the owner.
- Anything uncertain (direct push, no candidate, a skipped or failed gate in
  every candidate, an API error) leaves `validated=false` and the full suite
  runs exactly as before.
- Until the merge queue is on, PRs merge directly, the PR run was a fast-gate
  run, and the push to main runs the full suite (as today, minus docs-only).
  Fix 2 pays out once Fix 3's ruleset is applied.

### The two false comments

The trigger comment and the `check-migration-heads` comment now say: an
unlabelled PR shows no checks; whether that blocks a merge is the ruleset's
call, and as of 29 Sep 2026 it does not.

## Ruleset changes the owner applies (Settings > Rules > Rulesets > `protect-main-branch`)

Nothing in this PR changes a setting. Apply after this PR merges, in this order.

1. **Require status checks to pass**: enable. "Require branches to be up to
   date before merging": OFF (the queue tests the merge result; ON would force a
   re-run of the fast gate on every base move). Source for every check: GitHub
   Actions, workflow "Build and Deploy Sorento". Add exactly these 18 names, as
   the jobs report them (a matrix leg reports `<name> (<shard>)`):

   | # | Required check name |
   |---|---|
   | 1 | `Single alembic head (fast gate)` |
   | 2 | `Changed areas` |
   | 3 | `Validate backend imports` |
   | 4 | `Validate MCP imports` |
   | 5 | `Type-check frontend` |
   | 6 | `Validate frontend (vitest) (1)` |
   | 7 | `Validate frontend (vitest) (2)` |
   | 8 | `Validate frontend (vitest) (3)` |
   | 9 | `Validate frontend (vitest) (4)` |
   | 10 | `Backend test suite - SCM (Postgres, xdist) (1)` |
   | 11 | `Backend test suite - SCM (Postgres, xdist) (2)` |
   | 12 | `Backend test suite - SCM (Postgres, xdist) (3)` |
   | 13 | `Backend test suite (Postgres, xdist) (1)` |
   | 14 | `Backend test suite (Postgres, xdist) (2)` |
   | 15 | `Backend test suite (Postgres, xdist) (3)` |
   | 16 | `Backend test suite (Postgres, xdist) (4)` |
   | 17 | `Backend test suite (Postgres, xdist) (5)` |
   | 18 | `Backend test suite (Postgres, xdist) (6)` |

   A job skipped by its `if` reports `skipped`, which satisfies a required
   check, so on a PR the six backend shards (and any area not touched) block
   nothing; in the queue they run for real and gate. A PR with no `ci` label
   reports none of these, so it cannot merge until labelled: that is the
   intent. Do NOT add `Build and push images`, `build-and-deploy`, `Notify owner
   by email` or `Release ci label (one-shot trigger)`.

2. **Require merge queue**: enable, with:
   - Merge method: **Squash and merge** (main's history is one squash commit per
     PR, `... (#NNNN)`).
   - Build concurrency: **1** (runners are scarce; one queue run at a time, and
     deploys are serial anyway via the `deploy-production` group).
   - Minimum group size: **1**; maximum group size: **5**; wait time to meet
     minimum: **5 minutes**.
   - Only merge non-failing pull requests: **ON**.
   - Status check timeout: **60 minutes** (a full run is 25 to 35 minutes; an
     entry queued behind one in flight waits its turn).
3. Leave the existing bypass list (the owner's admin bypass) as it is.

After the first queue merge, confirm on the push-to-main run that step "Look
for a prior green run of this exact code" printed `validated=true` for the
`merge_group` run: that proves the queue's tested SHA is the SHA that landed on
main. If it printed "no successful run has head_sha", the fallback through the
merged PR's head ran instead (full suite, safe), and the step needs the queue's
`merge_group.head_sha` recorded differently; report it rather than loosening
`GATES`.

## Operating notes

- Orchestrator flow is unchanged: add `ci` once, the run removes it; re-add to
  re-run on a new head. To merge: "Merge when ready" puts the PR in the queue;
  the queue's `merge_group` run is the full suite.
- A hotfix that must skip the queue is a direct push; it runs the full suite on
  main, as today.
- `workflow_dispatch` always runs the full suite and deploys.

## Tests

`sorento_crm_backend/tests/test_ci_docs_only_filter.py` (111 tests), the same
mechanism as #1370: the two `changes` steps are extracted from the workflow and
executed under GitHub's bash flags with a stub `gh` that answers each endpoint
from a canned payload through the real `jq` filter; the jobs' `if` lines and
the concurrency expressions are evaluated as written. New in this lane:

- `scm` flag: every `SCM_RE` path on a PR runs the SCM shards; non-scm backend
  paths do not; off a PR `scm` follows `backend`.
- "prior" step: a queue run on the same SHA validates; one skipped or failed
  gate does not; an all-skipped run does not; a full PR run on the merged PR's
  head validates; a fast-gate PR run does not; a second candidate can validate;
  direct push, no run, a failed jobs call and a failed API all leave
  `validated=false`. `GATES` is asserted equal to the 17 test-job names parsed
  from the workflow.
- Job table: which jobs run for a PR (backend with and without scm paths,
  frontend + mcp, docs-only, another label), a merge_group entry, a validated
  push, an unvalidated push, a docs-only push, dispatch; a failed gate skips the
  deploy and still notifies; a validated push with a failed build or alembic
  gate does not deploy.

Kill tests: putting the backend shards back on `pull_request` fails the PR
scenario tests; removing a name from `GATES` fails the drift test; restoring the
old `build-and-deploy` condition fails the validated-push tests.

UAC: `ci-fast-gate-29sep-acceptance-criteria.md` alongside.
