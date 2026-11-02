# PLAN: Simulate confirm speed

Status: In build. Track: small fix (no migration, no auth/RBAC change, no new ingest; diff well
under 300 lines). Lane SIMULATE-CONFIRM-SPEED.
UAC: `simulate-confirm-speed-03nov-acceptance-criteria.md`.

## Owner ask (3 Nov 2026)

"Simulate confirm" on production (Fulfilment Planning, Board actions menu, admin only) waits a
long time.

## What exists (read on main)

- `simulate_confirm` (`app/api/v1/projects/fulfilment_planning.py:727`) runs `_run_confirm_many`
  once over every order, then probes a failing order that named no line by re-running the full
  confirm once per posted line (`_SIMULATE_PROBE_LINE_CAP` 60 lines per order,
  `_SIMULATE_PROBE_BUDGET` 200 runs per request), each in a rolled-back savepoint that clears the
  session cache. Every order-level error is probed too, including a refused job
  (`SimulationWouldCommit`) and a 409; it only gives up after running every line.
- `_facts_for` (`app/services/project_supply_service.py:9529`) resets
  `_active_decision_rows` on every call, so `_active_decision_snapshots` re-reads every active
  decision's `line_snapshots` JSON (prod copy: 254 decisions, 6.5 MB, 70-230 ms per read) once per
  order and once per probe.
- `line_snapshots` is mutated in place on an active decision in three places
  (`planning_change_service.py:3644`, `:4377`, `project_order_inquiry_service.py:6889`), so a
  cache keyed by decision id alone would be wrong.

## Change

1. Probe skip and early stop (`_simulate_on`):
   - An order-level error is not probed: a `SimulationWouldCommit` (refused job or commit) or an
     `AppException` with status 409. `confirm_many(raw_errors=True)` carries the exception's
     status and class on the result for the simulation only; Simulate pops them before replying.
   - Stop probing when the first 5 probed lines all failed with the same text (the order's own
     failure, reported exactly as today's "every line failed the same way": no
     `simulated_errors`). A real line-level failure (a line that fails alone with its own text)
     keeps the probe.
2. Active-decision snapshot reuse: `_active_decision_snapshots` keeps the parsed snapshots in
   `Session.info` keyed by `(id, xmin, ctid)` of each active row. Each call runs one cheap query
   for those keys and re-reads `line_snapshots` only for rows whose key changed, so an in-place
   rewrite, a new revision, a retirement or a rolled-back savepoint is always seen. The per-call
   memo and its resets stay; only the 6.5 MB re-read goes.
3. Timing: one INFO log line per simulated order (`simulate_confirm order=<pso> ms=<n>` for the
   main run and its probes) and one for the whole request.

No migration. No change to what Simulate reports beyond the two skips above. The Confirm guide
dry run is out of scope (lane CONFIRM-PREVIEW-STALE, #2091).
