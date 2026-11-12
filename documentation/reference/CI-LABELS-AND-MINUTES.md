# CI labels and the minute budget

The repo is private on a 3,000 GitHub-hosted minutes a month quota (CI-CLOUD-GATE, 4 Nov 2026;
the Enterprise plan of 10 Oct did not happen), billed per job and rounded up to the minute. So
GitHub runs fast checks and the release build/deploy only; tests run in Claude Code cloud
sandboxes (`documentation/agents/cloud-lanes.md`, "Tests before crew-done" and "Release
sweep"; plan `documentation/plans/ci/PLAN-ci-cloud-gate-04nov.md`). No job runs on the Mac
runner. One workflow,
`.github/workflows/deploy.yml`, runs everything. This page says what each trigger runs, what it
costs, and how to read the usage. The workflow file's comments are the authority on the
mechanics; this page is the operator's view. The design and its measurements:
`documentation/plans/ci/PLAN-ci-lean-10oct.md` (CI-LEAN).

## What runs when

| Trigger | Runs | Billed minutes (target) |
| --- | --- | --- |
| PR labelled `ci` | Two jobs: `Changed areas`, then `PR gate`, fast checks only (CI-CLOUD-GATE): main's head merged in, alembic single head, PII, Outline guides, gitleaks; the app and worker import chains plus `pytest --collect-only` when the backend changed; the MCP import check when MCP changed; `tsc` plus ESLint over the changed files when the frontend changed. No test executes and no Postgres/Redis container starts: the lane posted `crew-tests:` from its sandbox. A merge tree whose PR gate already passed is not checked again. | ~2 docs-only or re-label, ~5 one area, ~9 backend + frontend (see the budget) |
| PR labelled `ci-full` | REFUSED (owner, 9 Oct 2026: no full suite per PR). One job removes the label and fails with the reason; nothing else runs. | 1 |
| `workflow_dispatch` on main (the release) | Default (`skip_tests` true since CI-CLOUD-GATE): the alembic head check, build only the images whose service tree changed (an unchanged one is retagged), the owner-approved deploy. `Changed areas` refuses it unless the sha carries a `success` `release-sweep` commit status, which crew sets after a green full-suite cloud sweep on that sha (runbook: `documentation/agents/cloud-lanes.md`); `-f allow_unswept=true` overrides that as a visible emergency (the run summary says UNSWEPT RELEASE). `-f skip_tests=false`: the lean release tests first (core tier plus what the batch since the last release reaches, one `Release tests` job, ~25-50). `-f full_suite=true` (emergency, wins over `skip_tests`): the full shards. | ~25 default (build-images median 7 + build-and-deploy median 18); ~470 full (38099410256) |
| Push to main | The alembic single-head gate only (PII and gitleaks ran on the same commits in the PR gate). No tests, no deploy. | 1 |
| Any other label | Nothing (every job skips). | under 1 |

There is no nightly of any kind (owner, 10 Oct 2026): the deploy.yml schedule is gone and the
never-stuck smoke (`never-stuck-nightly.yml`) runs by hand only.

`PR gate` is the one check a PR needs: it runs the fast gates itself and fails when `Changed
areas` did not pass, and it runs with `always()` so a red root job never turns it into "skipped". The ruleset
`protect-main-branch` requires it once crew switches the ruleset (owner Q3). A merge-queue
entry reports `CI gate (full)`.

## The labels

`ci` is one-shot: the run removes it, so adding it again re-runs against the PR's current
head. A push to the PR branch never starts a run. `ci` runs share one concurrency group per PR
with cancel-in-progress on: adding `ci` while a `ci` run is live cancels that run (the head
moved). A `ci-full` label is refused by its own job and joins no group, so it cancels nothing.
Never change labels while a run you want is live; to re-run, remove the label, wait ten
seconds, add it alone.

- `ci` once per PR head that is ready to merge (CI-LEAN budget: about ten PR runs a day).

Above the 3600 CPU-s selection budget the `ci` run executes the PR's own changed test files
only and says so in the "Select backend tests by import" step of the `Changed areas` job; the
whole selection then runs in the release. That replaces the earlier behaviour (CI-SPEED,
1 Oct 2026) of running all six shards on the PR, which fired on most backend PRs and was 59% of
all minutes in the week of 29 Sep to 5 Oct 2026.

Until crew switches the ruleset to `PR gate`, it requires the five old names (`Single alembic
head (fast gate)`, `Changed areas`, `Validate backend imports`, `Validate MCP imports`,
`Type-check frontend`): the first two still run on a PR and the other three report "skipped",
which a ruleset accepts.

## Timeouts

Every test and gate job carries `timeout-minutes`: 60 on the three backend test jobs (main
shards, SCM shards, changed tests), 20 on everything else. GitHub's default is 6 hours and a
hung job bills all of it. The caps are for a hung runner, not targets, and they sit at about
twice the worst observed run time: a main shard measures 18 to 24 minutes, 29 in the worst
run seen (37158487882), and a cap at 35 cut a healthy shard at 94% on run 37369427779 (33:55
of pytest, a shard that took 22 minutes two days earlier, so run-to-run variance is about
1.6x). If a balanced shard runs past 45 minutes, rebalance `.test_durations` or raise the cap
with that evidence. The deploy jobs (`build-images`, `build-and-deploy`, `notify-owner`) are
deliberately outside this: the deploy step already has its own 70-minute command timeout for
the worker drain.

A job that shows `cancelled` with no runner and no steps did not hit its cap. The first
`ci-full` run (37369427779, 5 Oct 2026) lost eleven jobs that way, each exactly 15 minutes
after it was queued whatever its cap, with the check-run annotation "The job was not acquired
by Runner of type hosted even after multiple attempts": GitHub gave up finding a hosted runner
while the account's 20 concurrent job slots were held by other PRs' runs. The workflow cannot
cause or cure that; the gate job goes red, and the fix is to re-add the label once the queue
has drained (or to run fewer runs at once, or to add runners). Read the annotation under the
job before blaming a cap.

## The budget

### CI-CLOUD-GATE (4 Nov 2026): 3,000 minutes a month

PR gate step times. The sandbox figures are from a 4 vCPU / 15 GB cloud VM on 4 Nov 2026 (npm
install running alongside for part of it). GitHub's private-repo `ubuntu-latest` has about half
that CPU, so the GitHub column roughly doubles the CPU-bound steps.

| Step (runs when) | Sandbox | GitHub, estimated |
| --- | ---: | ---: |
| `Changed areas` (always; its own job) | seconds | 1 billed |
| Label removal, full-history checkout, merge main, alembic head, PII, Outline guides, gitleaks (always) | under 1 min | ~1 |
| Python setup (pip cache) + `pip install -r requirements.txt` (backend) | not timed (warm venv) | ~1-2 |
| app + worker import smoke (backend) | 44 s | ~1 |
| `pytest --collect-only`, 56,489 tests, no DB reachable (backend) | 3 min 19 s | 1.8 (38074897990) to ~3 |
| Node setup + `npm ci --force` (frontend) | not timed (warm) | ~2 |
| `next typegen` + `tsc` (frontend) | 1 min 57 s | ~3-4 |
| ESLint over the changed files (frontend; 40 files) | 4 s | under 1 |

So a PR gate bills about 2 minutes docs-only, about 5-6 for one area and about 9-11 with backend
and frontend both changed: at the ~10 minute target, slightly over when both areas change.
ESLint lints changed files only: the whole tree has 195 errors on main today (1 min 43 s).

**`next build` does not fit the PR gate.** On the same VM it compiled in 5 min 30 s and then
failed its type-check phase after 8 min 49 s (`app/(auth)/signin/page.tsx` exports
`isSafeCallbackUrl`, which Next.js rejects as a page export; not investigated in CI-CLOUD-GATE,
possibly an artefact of the earlier `next typegen` in that checkout). A full build is therefore
10+ min there and about 15-20 on a GitHub runner. It stays in the release's `build-images`.

| Item | Count a month | Each | Month |
| --- | ---: | ---: | ---: |
| Releases, default (build-images median 7 + build-and-deploy median 18) | 60 (2 a day) | ~25 | ~1,500 |
| PR gate runs (`Changed areas` + `PR gate`) | ~7 a day | ~7 | ~1,500 |
| **Total** | | | **~3,000** |

Fewer releases buy PR gates at about 3.5 per release. A `full_suite=true` emergency
release (~470) or a `skip_tests=false` release (~25-50 more) comes out of the same pool. The
tests themselves (each lane's `crew-tests.sh`, the ~2 h release sweep) bill no GitHub minutes.

### CI-LEAN (10 Oct 2026, superseded)

CI-LEAN (owner, 10 Oct 2026, GitHub Enterprise: 50,000 minutes a month, 2-3 releases a day,
release <= ~60 billed minutes, PR gate ~10-15, no nightly, no `ci-full` on PRs):

| Item | Count a month | Each | Month |
| --- | ---: | ---: | ---: |
| Releases (lean) | 75 | ~35 | ~2,600 |
| PR gate runs | 30 a day | ~10 | ~9,000 |
| Full-suite releases (over the cap, by hand) | a few | ~250 | ~500-1,000 |
| **Total** | | | **~12,000-13,000** |

The release run of 10 Oct 2026 (38017372957, the old design) billed 280. The history below
is what led here.

Measured 29 Sep to 5 Oct 2026 (701 runs): 85,687 minutes in seven days, 512 of them
`ci`-labelled PR runs at 126 minutes each. At that pace, about 73 PR runs a day:

| Lever | Minutes a month |
| --- | --- |
| Before: 73 PR runs a day at 126 min | about 276,000 |
| After: 73 `ci` runs a day at about 20 min (backend-only typical) | about 44,000 |
| Plus one `ci-full` per merged PR, say 15 a day at 210 min | about 95,000 |
| Plus the nightly when main moved, 30 days at 200 min | 6,000 |
| Plus releases, 29 a month at 230 min (15 with `skip_tests`) | 6,700 (or 450) |

Even after the cut, the pace of October 2026 does not fit in 3,000 minutes a month on
GitHub-hosted runners: the `ci-full` merge gate alone is about 30 times the allowance. The
cut makes the cheap gate cheap; fitting the budget needs either a self-hosted runner (free
minutes on GitHub's side, see the PR body of CI-MINUTES-CUT for the per-job profile) or far
fewer full runs. The levers, cheapest first:

1. Release with `skip_tests=true` once every merged PR has a green `ci-full` (saves about
   6,000 a month).
2. Make the nightly weekly (`cron: "17 19 * * 0"`) or drop it (saves up to 6,000).
3. Batch merges so one `ci-full` covers several PRs: `ci-full` tests the PR head merged onto
   main as it was when labelled, so the last PR of a batch labelled after the others merged
   covers the combination.
4. A self-hosted Linux runner for the shards (`runs-on` on the three backend test jobs): the
   SCM and main shards need Postgres (pgvector) and Redis as service containers, so Docker is
   required; peak concurrency on a `ci-full` run is 16 jobs (7 main entries, 3 SCM, 4 vitest,
   validate backend, validate MCP, type-check).

## How to read usage

- The month to date: GitHub, repository Settings, Actions, then the "Usage" panel under
  Billing at the organization or account level (`Settings > Billing and plans > Usage`). It
  shows minutes by workflow and by runner type; `deploy.yml` is the only one that matters.
- One run: `gh run view <id> --repo jayson-odoo/sorento-crm --json jobs` lists every job with
  `startedAt` and `completedAt`; sum the minutes, each job rounded up, for what the run
  billed. `gh api repos/jayson-odoo/sorento-crm/actions/runs/<id>/timing` gives the billable
  milliseconds directly (zero on a public repo, which is why the week of measurement used the
  job timestamps).
- A period: crew's `ci_minutes.py` (the script behind the numbers above) lists every run of a
  window with `gh run list --json databaseId,event,createdAt` and sums the jobs the same way.
- The skip reasons: a `ci` run's `Changed areas` job log says which areas changed, which test
  files were selected and whether the selection was above the budget; the gate job's log
  lists every needed job's result.
