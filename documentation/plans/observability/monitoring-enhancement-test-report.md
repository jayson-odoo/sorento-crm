# Monitoring enhancement — test report

Keyed to `monitoring-enhancement-acceptance-criteria.md`. Updated per slice.

| Slice | Status |
|-------|--------|
| **S2 — scheduled task overdue** | **PASS** (2026-07-20) |
| S4 — WhatsApp latency SLA | not started (blocked on n8n contract) |
| S5 — chat history UI | not started |
| S1 — health dashboard | not started |
| S3 — api_call_log | not started |
| S6 — timezone | not started |

---

## S2 — scheduled task overdue

Branch `worktree-observability-monitoring`. Backend `pytest`, frontend `vitest`,
browser verification via Playwright MCP against a dev server on `:3002`
(the user's own `:3000` was left untouched — it serves the main checkout).

### Results

| Id | Verdict | Evidence |
|----|---------|----------|
| OBS-S2-01 | PASS | `test_due_at_is_last_run_plus_interval`, `test_due_at_ignores_next_run_at_entirely` — the second poisons `next_run_at` with a value a year out and asserts `due_at` does not move. |
| OBS-S2-02 | PASS | `test_never_run_with_past_start_at_is_due_at_start_at`, `test_never_run_without_start_at_falls_back_to_created_at`, `test_never_run_task_is_reported_overdue`. |
| OBS-S2-03 | PASS | `test_future_start_at_not_overdue`. |
| OBS-S2-04 | PASS | `test_grace_is_percentage_clamped_60s_to_30min` (4 params covering both clamp ends), plus the boundary pair: `== due_at + grace` not overdue, `+1s` overdue. |
| OBS-S2-05 | PASS | `test_per_task_grace_percent_overrides_global`, `test_task_without_override_uses_global`, `test_invalid_per_task_grace_falls_back_to_global`. |
| OBS-S2-06 | PASS | `test_health_and_watchdog_report_identical_overdue_sets` drives both surfaces off one helper. Both inline queries deleted, not patched. |
| OBS-S2-07 | PASS | `test_disabled_task_never_overdue`. |
| OBS-S2-08 | PASS | `test_scheduled_tasks_overdue_detail_is_itemized` asserts key, interval phrasing, MYT last-run, lateness, and deep link. Rendered body in the simulation output below. |
| OBS-S2-09 | PASS | `test_late_by_measured_from_due_at` — 33m since last run on a 10m interval reports `23m`, i.e. measured from `due_at`, not from `due_at + grace`. |
| OBS-S2-10 | PASS | Pre-existing `health_alert_state` de-dup tests pass unchanged (fire once / suppress in cooldown / re-fire after / recovery notice). |
| OBS-S2-11 | PASS | Live prod-copy DB: old rules flagged `takeover_request_commit`, new rule reports zero. See below. |
| OBS-S2-12 | PASS | "Grace period (%)" renders with the effective value as placeholder and the computed grace inline ("Currently 2m 30s"); blank = use global. |
| OBS-S2-13 | PASS | Playwright via sidebar → set 50 → save → reload: field shows 50, server-computed grace updates 2m 30s → 5m, DB shows `{"grace_percent": 50}`. Zero console errors. |
| OBS-S2-14 | PASS | Zod rejects non-numeric/NaN with a message and blocks submit; `mapFormToUpdateBody.test.ts` covers the value mapping including `0` as a real value. |

### Live-data validation (OBS-S2-11)

Against the local prod-copy DB, 12 enabled tasks:

```
OLD card rule    : 1 overdue -> ['takeover_request_commit']
OLD watchdog rule: 1 overdue -> ['takeover_request_commit']
NEW shared rule  : 0 overdue -> []
```

`takeover_request_commit` runs every 15 seconds and was being reported overdue while
sub-second late. That is the standing false-alarm mechanism, reproduced and removed.

### State simulation (`scripts/simulate_overdue_states.py`)

Drives one task through every lateness state inside a rolled-back transaction:

```
task      : system_health_watchdog        interval: every 10 minutes
grace     : 150s  (25% of interval, clamped)

scenario                              ran ago   card   alert  agree
healthy — ran just now                  0.0m      0      no   ok
late, inside grace                     11.2m      0      no   ok
exactly at due + grace (boundary)      12.5m      0      no   ok
overdue — past grace                   14.0m      1     YES   ok
badly overdue                         200.0m      1     YES   ok
```

Resulting alert body:

```
Scheduled tasks — overdue (1):
  • system_health_watchdog (System health watchdog) — every 10 minutes,
    last run 20/07/2026 10:26 MYT, 3h 10m late —
    http://localhost:3000/system-management/scheduled-tasks/2ccb4ede-…
```

### Suite results

- `pytest tests/test_scheduled_task_overdue.py tests/test_system_health_watchdog.py tests/test_health_summary.py` → **50 passed**.
- `vitest .../scheduled-tasks/lib/mapFormToUpdateBody.test.ts` → **6 passed**.
- `tsc --noEmit` → no errors in touched files (4 pre-existing errors remain in `products/*` tests).
- `eslint` on the touched directory → clean (1 pre-existing error remains in `RunLogsTable.tsx`).

### Defects found and fixed during the slice

1. **Clearing the grace override silently did nothing.** The FE sent a metadata object
   with the key omitted, but `update_task` *merges* metadata and removes a key only on an
   explicit `null`. Caught by browser verification, not by the unit tests — the DB still
   read `{"grace_percent": 50}` after a save that appeared to succeed. Fixed by sending the
   `null` sentinel, and pinned by `mapFormToUpdateBody.test.ts`.
2. **Four watchdog tests were already failing on the base branch**, masked by a stale test
   double: `notify_spy` did not accept the `dedup_id` kwarg. Fixing that exposed a second
   pre-existing gap — the digest test seeded no users, so `sent` (which reflects resolved
   recipients) was always `False`. Both fixed; these tests cover the code this slice edits.

### Migration

`289_scheduled_task_grace_percent` adds `system_settings.health_task_grace_percent`
(default 25), guarded by an `information_schema` existence check so it is idempotent.
Applied to the local DB; `alembic current` → single head. Per-task overrides need no
migration — they reuse the existing `scheduled_tasks.metadata` JSONB.
