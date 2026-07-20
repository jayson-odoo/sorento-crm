# Monitoring enhancement — test report

Keyed to `monitoring-enhancement-acceptance-criteria.md`. Updated per slice.

| Slice | Status |
|-------|--------|
| **S2 — scheduled task overdue** | **PASS** (2026-07-20) |
| **S4 — WhatsApp latency SLA (CRM side)** | **PASS** (2026-07-20). n8n half handed off — see `n8n-contract-handoff.md`. Inert until it lands. |
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

---

## S4 — WhatsApp round-trip latency SLA (CRM side)

The n8n half (OBS-S4-01..04) is specified in `n8n-contract-handoff.md` and implemented by
the n8n session. Everything below is the CRM side and ships independently: all new ingest
fields are optional, so today's n8n payloads keep validating. Until n8n lands, the metric
simply has no data — nothing breaks and no alert fires on an empty window.

### Results

| Id | Verdict | Evidence |
|----|---------|----------|
| OBS-S4-05 | PASS | `test_pairs_incoming_to_outgoing_by_turn_id` — pairing is by `turn_id`, never proximity. |
| OBS-S4-06 | PASS | `test_pairing_is_immune_to_bursts` — 3 rapid turns with mixed latencies resolve to 30s/2s/3s; proximity pairing would mis-assign all three. |
| OBS-S4-07 | PASS | `test_proactive_send_is_excluded_not_paired` — a campaign send between an incoming and its reply neither steals the pairing nor invents a turn. |
| OBS-S4-08 | PASS | `test_multi_part_reply_measures_the_first_outgoing` — a 3-part answer is judged on when it starts (perceived responsiveness). |
| OBS-S4-09 | PASS | `test_sent_at_is_never_used_as_the_clock` — feeds a row whose outgoing `sent_at` *precedes* its own incoming, as observed in production, and asserts latency comes out 4.0s rather than −15s or 10s. |
| OBS-S4-10 | PASS | `test_unresolved_respond_ts_is_not_measured` — rows awaiting resolution are omitted, never approximated from `sent_at`. |
| OBS-S4-11 | PASS | `test_p99_tolerates_exactly_one_percent` + `test_p99_reflects_a_slow_tail_beyond_one_percent`. |
| OBS-S4-12 | PASS | `test_min_sample_size_prevents_alerting_on_one_turn`, `test_stats_empty_window_is_not_a_breach`. |
| OBS-S4-13 | PASS | `test_stalled_turn_detected_regardless_of_sample_size` — hard ceiling has no sample floor. |
| OBS-S4-14 | PASS | `test_incoming_with_no_reply_is_reported_separately`, `test_unanswered_within_threshold_is_not_flagged`. |
| OBS-S4-15 | PASS | `test_undelivered_message_does_not_affect_latency` — an offline recipient cannot breach the SLA. |
| OBS-S4-16 | PASS | `test_undelivered_counted_separately`, `test_recently_sent_not_yet_delivered_is_not_counted`. |
| OBS-S4-17 | PASS | `test_webhook_lag_is_measurable_and_separate_from_latency` — 45s webhook lag reported alongside, not inside, the 50s latency. |
| OBS-S4-18 | PASS | `test_webhook_lag_null_when_ingest_at_missing`. |
| OBS-S4-19 | PASS | `test_resolves_respond_timestamp_and_status`, `test_passes_contact_identifier_not_just_message_id` (the endpoint needs contact **and** message id). |
| OBS-S4-20 | PASS | `test_not_found_increments_attempts`, `test_not_found_at_max_attempts_marks_not_sent` — "not found = not sent", but only after transient failure is ruled out. |
| OBS-S4-21 | PASS | `test_transient_error_increments_without_concluding` — a 503 must never be recorded as `not_sent`. |
| OBS-S4-22 | PASS | `test_one_bad_row_does_not_abort_the_batch`, `test_respects_limit`, `test_exhausted_rows_are_not_retried`. |
| OBS-S4-23 | PASS | `test_seconds_epoch_is_handled_as_well_as_milliseconds` — treating ms as seconds yields year-58xxx dates. |
| OBS-S4-24 | PASS | `test_missing_timestamp_in_payload_is_not_resolved` — never substitute `now()` for a clock the payload didn't carry. |
| OBS-S4-25 | PASS | Ingest verified over real HTTP: `turn_id` stored, `ingest_at` server-stamped, `resolve_attempts` defaulted. A legacy payload with neither `turn_id` nor `message_id` still returns 201. |

### Scenario simulation (`scripts/simulate_chat_latency.py`)

Synthesizes turns into `chat_histories` inside a rolled-back transaction and evaluates
them through the same path the scheduled task uses:

```
p99 target 10s | ceiling 30s | min sample 30 | no-reply 5m

healthy — 40 turns @ 3s                turns=40  p99=3.0s   ok
degraded — 40 turns @ 25s              turns=40  p99=25.0s  ALERT  p99 exceeds target
one stalled turn among 40 healthy      turns=41  p99=90.0s  ALERT  + ceiling, worst 90s
incoming with no reply (12m)           turns=40  p99=3.0s   ALERT  no reply, longest 12m
webhook arrived 40s late               turns=1   p99=44.0s  ALERT  ceiling; lag max 40s
proactive sends only (no turns)        turns=0   p99=—      ok
```

The fourth row is the important one: it alerts while p99 reads a healthy 3.0s. A turn that
never completes never enters the distribution, so a p99-only alert would stay green
through exactly the dropped-webhook outage this slice exists to catch.

### Suite results

`pytest tests/test_chat_latency.py tests/test_chat_message_resolver.py` → **34 passed**.

### Defects found during the slice

1. **Two of my own test expectations were wrong**, and the code was right. `p99` over 99
   fast + 1 slow turns is 1.0s, not 45s — a 99th percentile tolerates exactly 1% by
   definition, and I had conflated it with `max`. Separately, a 20-turn breach test sat
   below the default `min_sample` of 30, so staying quiet was correct behaviour. Both
   tests rewritten; the percentile case is now pinned by a pair of tests that state the
   distinction explicitly.
2. **`run_chat_latency_watchdog` called a `_mark_ok` helper that did not exist.** The
   recovery branch would have raised `NameError` the first time the condition cleared —
   in production, after an incident, which is the worst possible moment. Found by reading
   the module rather than by a test: the service tests exercised `_eval_chat_latency` but
   never the entry point's fire/recover state machine. Added `_mark_ok` (symmetric with
   the existing `_mark_alerting`, replacing an inline duplicate in the original watchdog)
   and two tests that drive fire -> recover end to end.
3. **sqlite cannot autoincrement a `BigInteger` primary key**, so every fixture insert
   failed `NOT NULL constraint failed: chat_histories.id`. Added a DDL-only shim
   (BigInteger PK → Integer for sqlite) in the same style as the existing JSONB/ARRAY
   shim in `tests/conftest.py`. Postgres uses a sequence and is unaffected.

### Migrations

- `290_chat_history_latency_columns` — `respond_ts`, `delivery_status`, `delivered_ts`,
  `read_ts`, `resolve_attempts`, `turn_id`, `ingest_at`, plus two partial indexes (the
  resolver's unresolved-rows query, and turn pairing). All nullable with **no backfill**:
  existing rows genuinely have no Respond timestamp and no turn, and inventing one would
  fabricate latency data (OBS-X-02).
- `291_chat_latency_settings_and_tasks` — four `system_settings` thresholds (p99 target
  10s, ceiling ×3, no-reply 5min, min sample 30) and seeds the `chat_message_resolver`
  and `chat_latency_watchdog` tasks at 60s, `ON CONFLICT (key) DO NOTHING`.

Applied to the local DB; `alembic current` → single head `291`.

### Not yet done for S4

- No FE surface yet — the p99 tile and breach list land with S1 (dashboard) and S5 (chat
  page), per the plan's sequencing.
- The resolver has not been exercised against the live Respond API; its behaviour is
  pinned by a fake client. First real run happens once n8n starts populating `message_id`.
