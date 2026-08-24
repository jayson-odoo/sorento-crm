# PLAN - SLA clock starts at the next working-window open

Status: Phase 2 code complete, tests green (43 passed); awaiting live re-verification
Date: 2026-07-20
Branch: `worktree-observability-monitoring`
Classification: CORE
UAC: `sla-clock-start-next-working-window-acceptance-criteria.md`

## Origin

Diagnosing stock inquiry `3c892c32-08d3-4855-ac10-8bd7552b06b0` (submitted Sat
18/07 09:37, 72h tier) surfaced that an SLA clock starts at the raw event instant
even when nobody is working. The user then simulated the case on
`ce360d26-0dc6-44eb-beb3-bf053bc85033` with Monday flagged non-working and the
window set to 08:00 - 23:00.

**Observed:** submit Mon 20/07 22:48 MYT, 24h tier → `due_at` = Tue 21/07 23:00 MYT.
**Wanted:** clock starts Tue 08:00 (next window open), +24h → due **Wed 22/07 08:00**.

Backend-only. No FE work, no migration, no new endpoint. Phase 1 (FE prototype) is
not applicable and is explicitly skipped, recorded here per the methodology gate.

## What produces today's behaviour

This branch already carries a first attempt:
`_clamp_offhours_due_to_workday_end` (`app/services/form_sla_service.py:65-103`).
For an off-hours submit it lifts the working-days due to that day's
`work_day_end_time` - hence Tue 23:00 above.

It is a **one-sided relaxation of the deadline**, not a correction of the start.
The rule the user wants normalizes the *start* instead, which subsumes it.

**The clamp is removed in this change.** Keeping both compounds: normalized start
Tue 08:00 → +1 working day → Wed 08:00 → clamp still sees an off-hours submit and
pushes to Wed 23:00. They are mutually exclusive.

## Design

One new primitive plus a normalization call at each **automatic** clock start.

### 1. `CalendarService.next_working_window_open` (new)

`app/services/calendar_service.py`

```python
def next_working_window_open(
    self,
    start_value: datetime,
    *,
    tz: ZoneInfo = DEFAULT_WORKING_TZ,
) -> Optional[datetime]:
    """Roll a clock start forward to the next working-window open.

    Returns start_value unchanged when it already falls inside a working window
    (business weekday, not a holiday, [work_day_start, work_day_end)). Otherwise
    returns the next business day's work_day_start (or the same day's open when
    start is before it). Naive input treated as UTC; output naive UTC.
    Idempotent. Degenerate calendar config -> returns input unchanged + warns.
    """
```

Reuses `get_working_weekdays`, `get_working_hours`, `get_public_holidays_between`,
`_is_business_day` - the same helpers the existing `_StubCalendar` test harness
already stubs, so no new fixtures. Iteration bounded by the same guard style as
`add_working_hours` (`calendar_service.py:428`) so a bad calendar can never hang
the request path.

Satisfies AC-1..AC-8.

### 2. Normalize inside `add_working_days_from_hours`

`app/services/calendar_service.py:288`

Insert the normalize call after the aware-UTC conversion and the `hours <= 0`
guard, before the `< 24.0` branch at line 319, so both branches receive a
normalized start.

The `< 24.0` branch delegates to `add_working_hours`, which already rolls a
non-window start forward (`calendar_service.py:378-379`, implemented at 432-435)  - 
normalizing first is a no-op there, which AC-6 (idempotence) pins.

This single edit fixes `due_at` for every caller:
- form SLA via `_working_due_naive` (`form_sla_service.py:105`)
- conversation SLA via `_working_due` (`sla_service.py:348`), covering all its
  call sites (`sla_service.py:2164, 2166, 3395, 3396, 3904, 3905, 3972, 3973`)

Satisfies AC-9..AC-12.

### 3. Delete the clamp

Remove `_clamp_offhours_due_to_workday_end` and its call inside
`_working_due_naive`, plus the docstring paragraph describing it.

### 4. Normalize the stored clock start

`due_at` alone is not enough - the UI counter reads `current_tier_started_at`.
Normalize it at automatic clock starts only.

**Form SLA** (`app/services/form_sla_service.py`):
- Add `_working_clock_start_naive(db, dt)` beside `_working_due_naive`, same
  defensive try/except shape - on failure return `dt` unchanged.
- `_start_for_config`: compute `clock_start` once; keep `initiated_at=now`
  (AC-14), set `current_tier_started_at=clock_start`, pass `clock_start` (not
  `now`) into both `_working_due_naive` calls.
- `_escalate_tracker`: same - `escalated_at=now` stays true (AC-15);
  `current_tier_started_at` and both dues derive from `clock_start`.

**Conversation SLA** (`app/services/sla_service.py`) - new `_working_clock_start`
helper (aware UTC, matching that module), applied at the two genuine automatic
clock starts:
- create: `current_tier_started_at` when not caller-supplied
- escalate: `current_tier_started_at`, with `escalated_at` keeping the true instant

**Explicitly excluded, after reading the call sites:**
- **Admin override** - an operator who types a `current_tier_started_at` has it
  stored verbatim (AC-17). Its `due_at` still flows through the normalized
  primitive, which is correct: the operator states when the clock started, not what
  the deadline should be.
- **Routing-correction restart** (team flip / misroute fix). Its own comment states
  it deliberately keeps calendar-hour math because it is not a real SLA countdown;
  normalizing only its start would leave it internally inconsistent. Left untouched.

Satisfies AC-13..AC-17.

## Phase 2 - TDD order (red → green → refactor)

Tests first, extending `tests/test_working_hours_sla.py` (stub-based, no DB, free
of the global-listener interference that hits sqlite fixtures).

1. **Red:** `next_working_window_open` - inside window unchanged, before open, at
   close, after close, weekend, holiday, idempotence, degenerate config
   (AC-1..AC-8). Fails: method does not exist.
2. **Green:** implement the primitive.
3. **Red:** `add_working_days_from_hours` - off-hours start + 24h → next-next
   working day at open; + 72h → three working days later at open; + 3h →
   working-hours clock unchanged; in-window starts byte-identical to today
   (AC-9..AC-12). The stub window is 09:00 - 17:00, so stub expectations use 09:00
   as open, not production's 08:00.
4. **Green:** wire normalization in; delete the clamp.
5. **Red:** service-level tests - tracker created off-hours stores a normalized
   `current_tier_started_at` with a true `initiated_at` (AC-13/AC-14); an
   admin-supplied start is not normalized (AC-17).
6. **Green:** the form-SLA edits + the conversation-SLA edits.
7. **Refactor + full `pytest`** (AC-22).

## Verification against the live sim

After deploy to the running `:8002` backend, submit a fresh stock inquiry with
Monday non-working and the window 08:00 - 23:00. Expect `current_tier_started_at` =
Tue 08:00 MYT and `due_at` = **Wed 08:00 MYT**, and the detail page at `:3002` to
show the same.

## Risk

- **Blast radius is every SLA due computed after deploy.** Weekday-inside-window
  starts are unaffected (AC-12 pins this), which is the overwhelming majority. Only
  nights/weekends/holidays shift, and they shift **later**, never earlier - so no
  tracker becomes retroactively overdue.
- **Escalation cadence improves.** The 2-minute sweep escalates at breach time;
  with normalized starts, dues land on window-open boundaries, so escalations fire
  inside working hours rather than at 02:00.
- **No data migration** (AC-19). Existing trackers keep their current dues.

## Related findings (not in this plan)

Surfaced while diagnosing the same inquiry, tracked separately:

1. `start_tier` is hardcoded to 1 (`form_sla_service.py:730` on main); a stage lands
   on a higher tier only because `resolve_team_with_tier_fallback`
   (`user_service.py:2074-2095`) skips tiers with no team. So `project_sales`
   starting at tier 2 is emergent, not configured - add a tier-1 team to that team
   set and every stock inquiry silently changes SLA. Candidate fix: an explicit
   `start_tier` column on `form_sla_configs`.
2. `POST /api/v1/sla/integration/escalate` (`sla_tracking.py:814`) escalates
   unconditionally, with no overdue check, resolving the tracker by contact.
3. `_start_for_config` raises when the policy has no row for the resolved start
   tier, but `procurement_service.py:3604-3611` swallows the exception - a
   misconfigured stage silently gets no SLA at all.
4. The `stock_inquiry`/`project_sales` config still points at policy **NORMAL**,
   not the **STOCK_INQUIRIES** policy (tier 2 = 72h) created for it.
