# PLAN: Working-day SLA due-date clamp

**Status:** Design locked (grill 2026-07-19). Not built.
**Classification:** CORE (extends the existing form-SLA engine; `public` schema; no new tables).
**Domain:** forms / sla
**UAC:** `documentation/plans/forms/form-workday-sla-clamp-acceptance-criteria.md` (contract - written first)
**Owner:** Claude + Jayson · **Created:** 2026-07-19

## Problem (proven)

Form due-dates funnel through `_working_due_naive` (`app/services/form_sla_service.py:65`) →
`CalendarService.add_working_days_from_hours` (`app/services/calendar_service.py:288`), which branches
at 24h:

- **`< 24h`** → `add_working_hours` (`:366`): a true 09:00 - 17:00 KL clock. Skips nights/weekends/
  holidays. **No bug.**
- **`>= 24h`** → `days = round(hours/24)` then `add_business_days` (`:233`): steps whole business days
  and **preserves the submission wall-clock time-of-day.** **The bug.**

Simulation (24h tier, Mon - Fri 09:00 - 17:00, no holidays):

| Submit | Due today | Effective working time | Verdict |
|---|---|---|---|
| Sat 09:01 | **Mon 09:01** | ~1 min | pathological (Hasni's case, CONFIRMED) |
| Mon 08:30 | Tue 08:30 | ~1 min | same bug, weekday |
| Sun 23:00 | Mon 23:00 | whole Mon, past close | loose |
| Fri 17:30 | Mon 17:30 | whole Mon, past close | loose |
| Wed 14:00 | Thu 14:00 | ~1 full day | fine |

Root cause: an early-morning / off-hours submit clock lands the deadline at that same early time on
the `>= 24h` branch → almost no working window.

## Solution - one-sided clamp in `_working_due_naive`

After the funnel computes `due` (naive UTC), convert to KL local; if the local time-of-day is
**before** `work_day_start_time` on a working day, set it to that day's **configured**
`work_day_end_time`; convert back to naive UTC. Only the pre-open case is touched.

- Sat 09:01, 24h → raw Mon 09:01 → **Mon 17:00**.
- After-close and in-window due-times untouched → clamp can **never** make an SLA tighter. Pure safety.
- `< 24h` branch already window-clamps → left alone.

### Implementation sketch

```python
# app/services/form_sla_service.py, inside _working_due_naive, after `out` is computed
def _clamp_to_workday_end(db, due_naive_utc):
    cal = CalendarService(db)
    start_t, end_t = cal.get_working_hours()
    local = due_naive_utc.replace(tzinfo=timezone.utc).astimezone(DEFAULT_WORKING_TZ)
    # only clamp when it lands on a working day at a pre-open time
    if cal._is_business_day(local.date(), cal.get_working_weekdays(),
                            cal.get_public_holidays_between(local.date(), local.date())) \
       and local.timetz().replace(tzinfo=None) < start_t:
        local = local.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
        return local.astimezone(timezone.utc).replace(tzinfo=None)
    return due_naive_utc
```
(Exact helper visibility TBD in coding - reuse `CalendarService` accessors, do not duplicate the
holiday/weekday logic. If a private accessor must become public, do it minimally.)

## Decisions

| # | Decision |
|---|----------|
| D1 | **Rule = one-sided clamp** (snap to end-of-day only when raw time is *before* `work_start`). Rejected: start-shift + unify-through-working-hours - both loosen every deadline, larger change than asked. |
| D2 | **Placement = `_working_due_naive`** (form-only funnel). NOT `add_business_days`/`add_working_days_from_hours` (also serve SLA extend + conversation SLAs). Narrowest blast radius (FUNNEL-1/2). |
| D3 | **End-of-day = configured `work_day_end_time`** via `get_working_hours()`, never hardcoded 18:00 (CLAMP-6). |
| D4 | **Scope = all 4 forms, response + resolution + escalation** (all pass through the funnel). `< 24h` branch untouched (CLAMP-8). |

## Phase mapping

- **Phase 1 (FE prototype):** N/A - pure backend calc; the FE already renders `due_at`. No prototype.
- **Phase 2 (BE, test-FIRST):** author CLAMP-1..9 + FUNNEL-1..6 as failing tests first (deterministic
  engine → golden expected timestamps before code), implement the clamp, green, refactor. Re-run the
  full existing SLA suite for FUNNEL-2 regression.
- **Phase 3:** `/code-review`; reviewer confirms one-sidedness invariant (CLAMP-9) + blast-radius
  containment.

## Risks

- **R1 - timezone/DST:** KL has no DST, but keep all math on `DEFAULT_WORKING_TZ` and store naive UTC;
  test asserts the returned naive-UTC equals the KL-17:00 conversion.
- **R2 - `_is_business_day` is currently "private":** avoid duplicating weekday/holiday logic; if
  needed expose a thin public predicate on `CalendarService` rather than re-implementing.
- **R3 - no schema change, no backfill:** existing open trackers keep their stored due until next
  recompute/escalation; this is acceptable (fix is forward-looking). Note in PR.
