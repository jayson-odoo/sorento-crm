# PLAN: release/nightly tests sharded on GitHub Actions; reorder planning nightly only (CI-PARALLEL-ACTIONS)

Status: in progress (small fix track: CI + test config only, no product code, no migration, no auth change)

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

1. `.github/workflows/tests-sharded.yml`: `workflow_dispatch` (mode full|delta, base sha, head
   sha, comment target) plus a nightly `schedule`. Jobs: `select` (file list + shard plan),
   `backend` matrix over N shards (Postgres pgvector + Redis service containers), `vitest`
   matrix (`--shard i/M`), `summary` posting one `crew-tests:` line with per-shard results and
   failing test ids.
2. Reorder-planning tests: ONE list, `sorento_crm_backend/tests/nightly_only.txt`; the delta
   selection and `scripts/crew-tests.sh` drop its entries; only the nightly full sweep runs them.
3. Measured run on main HEAD; numbers in the PR.
