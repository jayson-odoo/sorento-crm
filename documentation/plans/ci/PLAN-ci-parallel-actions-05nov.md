# PLAN: release/nightly tests sharded on GitHub Actions; reorder planning nightly only (CI-PARALLEL-ACTIONS)

Status: built, measured, in review on PR #2198; switch-over is crew's decision (small fix track: CI + test config only, no product code, no migration, no auth change)

## Owner (5 Nov 2026 ~14:00 MYT)

"is using the cloud claude to run CI the most efficient way? is our SCM test really needed? ...
reorder planning are not really in use". Crew proposal accepted ("yeap ok"):

- (2) the release delta and the nightly full sweep move from a Claude Code cloud sandbox (4 cores,
  2 h command cap; the 5 Nov release delta took ~2.5 h and its vitest step was killed) to GitHub
  Actions jobs sharded in parallel on GitHub-hosted runners;
- (3a) the SCM reorder-planning tests run only in the NIGHTLY full sweep, never at release or PR.

## Today (cited)

- `scripts/nightly-sweep.sh` and `scripts/release-delta.sh` run serially in one sandbox
  (`scripts/sweep-lib.sh`). PR #2191 (RELEASE-DELTA-AFFECTED) replaces the delta selection with
  `sorento_crm_backend/scripts/release_delta_select.py` (changed + dependents + depended-by).
- The PR gate (`deploy.yml` `lean-gate`, `ci` label) runs fast checks only; this lane does not
  touch it or the deploy jobs.

## Change

1. `.github/workflows/tests-sharded.yml`, `workflow_dispatch` ONLY (mode full|delta, base sha,
   head sha, comment target; crew 5 Nov: no push / schedule trigger). Jobs: `select`
   (`sorento_crm_backend/scripts/sharded_tests_plan.py`: file lists, whole files packed onto
   shards by estimated seconds), `backend` matrix (pgvector Postgres + Redis service
   containers; main pool, tests/scm pool, one serial runner), `vitest` matrix (`--shard i/M`, or
   one `vitest related` runner on a delta), `summary`
   (`sorento_crm_backend/scripts/sharded_tests_summary.py`) posting one `crew-tests:` line with
   per-shard results, failing test ids, wall clock and billable minutes.
2. Reorder-planning tests: ONE list, `sorento_crm_backend/tests/nightly_only.txt`; the delta
   selection and `scripts/crew-tests.sh` drop its entries; only the nightly full sweep runs them.
3. Measured run on main HEAD; numbers in the PR.

## Measured (5 Nov 2026, full sweep of main, GitHub-hosted ubuntu-latest)

| Run | Config | Wall clock | Billable min (crew's count) | Result |
| --- | --- | --- | --- | --- |
| 41977895392 | 20 main (pytest-split chunks) / 4 SCM / serial / 6 vitest | 40 min | 714 | 10 main reds on 30bbcc6a (5 of 20 main shards red) |
| 41982964838 | 36 main (pytest-split least_duration) / 3 SCM / serial (ddl files only) / 6 vitest | ~46 min | 1,243 | same main reds over 10 of 36 shards |
| 41986047860 | 36 main (whole files packed) / 3 SCM / serial / 6 vitest | 20.6 min of jobs (43 incl. 21 queued behind run 2) | 412 | 55,998 passed / 3 failed, vitest 22,726 / 0 on 8cec8487 |
| 41992915180 | 24 main / 3 SCM / serial / 8 vitest | cancelled by crew's stop order | ~6 | n/a |

What each change bought: pytest-split made every shard collect the whole ~50k-test pool before
deselecting (the serial runner spent 949 s collecting to run 109 `serial_ddl` tests), so whole
files packed by the planner cut the main pool from ~560 to 252 job-minutes; `least_duration`
spread every file over every runner and doubled the cost. The reds are main's own tests, not this
workflow.

Cost: ~USD 0.008 per billable minute (crew: 2,375 min ~ USD 19). Full sweep at run 3's shape:
412 min ~ **USD 3.30** (a nightly every night ~USD 99 a month, over the USD 40 budget). Release
delta: its share of the full sweep by estimated seconds plus ~1.6 min of setup per runner; the
42d1a56c..019770c1 delta (262 files) ~40-60 min ~ **USD 0.35-0.50**; a delta that falls back
to the full suite (conftest, requirements, `app/models/user.py`) costs a full sweep.
Cheaper: fewer shards save only the per-runner setup (~1.6 min each; 36 to 12 main shards saves
~40 min ~ USD 0.30 and makes the wall clock ~25-30 min): the bill is the suite's own CPU. The
real saving is where the nightly runs: on the self-hosted Mac runner (no Actions minutes; 5-6 h
serially, measured 2 Nov, which a 01:47 nightly can afford) or in the cloud sandbox as today,
with only the release delta on GitHub Actions. (`tests/test_ci_cloud_gate.py` pins every job
to ubuntu-latest today; a Mac nightly would change that pin.)
