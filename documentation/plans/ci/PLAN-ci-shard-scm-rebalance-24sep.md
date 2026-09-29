Status: small fix track - in review

# CI: shard the SCM backend suite 3-way, rebalance the main backend matrix to 6

## Problem

`test-backend-scm` is a single, unsharded runner, and it is the "Build and Deploy
Sorento" gate's critical path. `test-backend` is already sharded 4-way via
pytest-split, but the split is by test COUNT with no durations file, so the four
shards are wildly uneven and the gate still costs the slowest one.

## Measured facts (run 35945594213, 2026-09-24, PR event)

- `test-backend-scm`: one runner, `-n auto --dist loadfile -m "not serial_ddl"
  tests/scm/` = 3951 tests in 23:53, then the serial_ddl step 18 s. Total 25:39
  wall clock, the gate's critical path.
- `test-backend`: matrix shard 1..4 via `pytest-split --splits 4 --group N`, no
  durations file, split by count. Shard 1 = 9:03, shard 4 = 12:22, shard 3 =
  16:07, shard 2 = 19:34 plus the two serial steps that only ran on shard 2
  (migration tests 1:20, view/DDL tests 0:42) = 21:36.
- Install deps ~25 s, bootstrap ~6 s per job. Negligible against the above.
- `pytest-split>=0.10` and `pytest-xdist` are already in
  `sorento_crm_backend/requirements.txt` - no new dependency.

## Change

One file, `.github/workflows/deploy.yml`, no migration, no auth change:

1. `test-backend-scm` gets `strategy: { fail-fast: false, matrix: { shard: [1,
   2, 3] } }`, `--splits 3 --group ${{ matrix.shard }}` on the SCM pytest
   line, and the "Run SCM serial_ddl tests serially" step moves behind
   `if: matrix.shard == 1`. Job display name becomes `Backend test suite - SCM
   (Postgres, xdist)` so the matrix rows read `... (1)`, `... (2)`, `... (3)`.
2. `test-backend` matrix becomes `shard: [1, 2, 3, 4, 5, 6]`, `--splits 6
   --group ${{ matrix.shard }}`. Both serial steps ("Run migration tests
   serially", "Run view/DDL tests serially") move from `if: matrix.shard == 2`
   to `if: matrix.shard == 1`, since shard 1 was the measured shortest shard
   under the old 4-way split and has the headroom for them under the new
   6-way split.
3. Comments updated in place with the measured numbers above and the date, so
   the next person reading the job does not inherit stale numbers (the old
   comment said "Shard 2 is the shortest shard (about 7 minutes against shard
   3's 18)", which was already wrong against the 2026-09-24 measurement).
4. Nothing else in the workflow changes. `build-and-deploy`'s `needs:` list
   references the job ids `test-backend` / `test-backend-scm` unchanged - a
   matrix job still satisfies `needs` as one job regardless of shard count.
   Grepped the file for both job ids: no other hard-coded shard count exists
   outside the two `strategy.matrix` blocks and the `--splits`/echo lines
   touched above.

## Expected outcome

- `test-backend-scm`: roughly 23:53 / 3 ≈ 8-9 min per shard, plus the
  serial_ddl step on shard 1 only (18 s).
- `test-backend`: roughly the old total suite time split 6 ways instead of 4,
  so each shard drops from the 9-19.5 min range to roughly 13 min or less,
  with the two serial steps only adding to shard 1.
- Gate wall clock drops from ~26 min to roughly 13-14 min, since the SCM job
  is no longer the outlier holding up `build-and-deploy`.

## Acceptance

PR gate wall clock under 15 min on the PR's own CI run.
