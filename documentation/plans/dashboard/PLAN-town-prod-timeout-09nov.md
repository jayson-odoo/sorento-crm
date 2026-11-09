# PLAN: Town snapshot statement timeout on prod (Sorento company)

Status: in review, PR #2292 (reviewer READY). Small fix track (backend only, no migration, no auth/RBAC change, no new ingest).

Lane: TOWN-PROD-TIMEOUT. UAC: `town-prod-timeout-acceptance-criteria.md`.

## Problem

Prod, System > Operations > Scheduled Tasks > "Sorento town snapshot" > Last error, every run since
9 Nov 16:17: "Town snapshot failed for 1 of 2 companies: Sorento: (psycopg2.errors.QueryCanceled)
canceling statement due to statement timeout". Traceback at `snapshot.py:87` (`_today_and_compare`).
Mocha builds. The same build on the dev copy (`sorento_prod_1104`) runs in about 2 s with no failure.

## Which timeout

The job's own: `STATEMENT_TIMEOUT_MS = 5000` (`app/services/town/snapshot.py:51`), set with
`SET LOCAL` on the build session (`snapshot.py:473`, `_build_session.__enter__`), primary or replica.
The ranking raises it to 30 s for its one statement (`snapshot.py:52`, `:169`). The engine has no
statement timeout (`app/database.py:11`, only `-c timezone=utc`), nor does `scheduler_session`
(`app/scheduler/task_scheduler.py:35`).

## Cause

Not the execution: on `sorento_prod_1104` under the same 5 s `SET LOCAL`, every statement of the
Sorento build runs in at most 0.34 s (the 30 s ranking 1.4 to 3.6 s). The difference is JIT:
the dev Postgres is Homebrew 17 without LLVM (`pg_jit_available()` = false), so it never compiles.
UNVERIFIED (not measured, prod is out of bounds): prod's Postgres has JIT at the defaults
(`jit_above_cost` 100000, inline/optimize 500000). Inferred from the Sorento-only failure lining up
with the planner costs below, and from INVOICED-CHANNEL-PERF.
`_today_and_compare` reads the per-document sales type (`inv.document_sales_type()`, a lateral of
about a dozen correlated subqueries), so its planner cost is 0.63M to 2.09M for Sorento (the
2 Nov Monday that 9 Nov compares against has 688 documents): above the inline+optimize threshold,
where compile time is seconds. Mocha's is 0.18M: plain JIT, no inlining or optimization, so it
passes. The same mechanism cost the invoiced report 5.2 s of JIT on 0.3 s of execution
(INVOICED-CHANNEL-PERF, `PLAN-invoiced-channel-perf-01nov.md:22`), and the report engine has run
its statements with `SET LOCAL jit = off` since (`app/services/reports/engine.py:1035`). The town
build reads the same sales type expression on its own session and never switched JIT off.

## Fix

`_build_session.__enter__` also runs `SET LOCAL jit = off`, beside the 5 s timeout: the same rule
the report engine applies to the same expression. It lasts for the build's own transaction only
(both the primary and replica branch), covers the ranking too (its savepoint inherits it), and no
other job or session changes. No query change, so every figure stays identical. The 5 s timeout
is not raised: every statement runs at most 0.34 s on the dev copy, so it keeps 15 times headroom.

## Post-deploy proof

Sorento's "Last error" on the Town scheduled task clears on the first run after the deploy. To
confirm the cause itself, the owner can run `SELECT pg_jit_available(), current_setting('jit')` on
prod (expected `t`, `on`). If JIT turns out not to be the cause, the change is harmless (one
transaction, no figure changes) but the timeout would remain, and the next step is the prod plan of
`_today_and_compare`.

## Tests

- Red first: `tests/town/test_town_snapshot_tick.py` a build inside the tick sees `jit` = off
  (primary); `tests/town/test_town_snapshot_replica.py` the same on the replica branch.
- Kill test: drop the line, both go red again.
- Unchanged and run: `tests/town/test_town_snapshot_figures.py`, the tick and replica suites.

## Evidence script

Scratch only (not committed): timed each captured statement under the 5 s `SET LOCAL` on
`sorento_prod_1104`, plus `EXPLAIN (FORMAT JSON)` total cost per statement against the JIT tiers.
