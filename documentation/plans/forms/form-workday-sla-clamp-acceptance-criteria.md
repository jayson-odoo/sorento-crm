# UAC — Working-day SLA due-date clamp (off-hours / weekend submits)

**Status:** Draft (pre-code) · **Classification:** CORE · **Domain:** forms / sla
**Plan:** `documentation/plans/forms/PLAN-form-workday-sla-clamp.md`
**Contract:** when a form-SLA due date computed on the working-**days** branch (`>= 24h` tier) would
land at a time-of-day **before** the work-day opens, it is clamped forward to that day's configured
`work_day_end_time`. The clamp is **one-sided** — it never moves any due date earlier than today's
behaviour. Applies to all four form types (Purchase Request, Sponsorship Form, Complaint, Stock
Inquiry), across response + resolution + escalation due dates.

Tags: `[BE]` backend · `[FE]` frontend · `[E2E]` playwright · `[T]` unit/service test.

Fixed reference calendar for all examples: Mon–Fri working, 09:00–17:00 Asia/Kuala_Lumpur, no
public holidays unless a case says so. All timestamps stored naive UTC; working-day/-hour math is
evaluated on the KL calendar per `CalendarService`.

Code anchors: `_working_due_naive` (`app/services/form_sla_service.py:65`) is the single funnel;
`CalendarService.add_working_days_from_hours` (`app/services/calendar_service.py:288`) branches at
24h; `add_business_days` (`:233`) preserves time-of-day; `add_working_hours` (`:366`) is the
`< 24h` clock; work window via `get_working_hours` (`:104`), weekdays via `get_working_weekdays`.

---

## Group CLAMP — the one-sided clamp (deterministic engine, test-FIRST)

- **CLAMP-1 `[T]`** GIVEN a 24h response tier and a submit at **Sat 09:01**, WHEN the response due is
  computed, THEN the raw working-days result **Mon 09:01** is clamped to **Mon 17:00** (configured
  `work_day_end_time`). *(Hasni's reported case.)*
- **CLAMP-2 `[T]`** GIVEN a 24h tier and a submit **Mon 08:30** (pre-open weekday), WHEN due is
  computed, THEN raw **Tue 08:30** → clamp → **Tue 17:00**.
- **CLAMP-3 `[T]` (REGRESSION, hard)** GIVEN a 24h tier and an **in-window** weekday submit **Wed
  14:00**, WHEN due is computed, THEN it stays **Thu 14:00** (in window → NO clamp; byte-identical to
  today).
- **CLAMP-4 `[T]` (REGRESSION, hard)** GIVEN a 24h tier and an **after-close** submit **Fri 17:30**,
  WHEN due is computed, THEN it stays **Mon 17:30** (after close on the landing day → NO clamp; clamp
  is one-sided and never pulls a deadline earlier).
- **CLAMP-5 `[T]` (REGRESSION, hard)** GIVEN a 24h tier and a **Sun 23:00** submit, WHEN due is
  computed, THEN it stays **Mon 23:00** (raw time is after close, not before open → unchanged).
- **CLAMP-6 `[T]`** GIVEN a work calendar whose `work_day_end_time` is changed to **18:00**, WHEN
  CLAMP-1 is re-run, THEN the clamp target is **Mon 18:00** (reads configured end time, never a
  hardcoded value).
- **CLAMP-7 `[T]`** GIVEN a public holiday on the Monday following a Sat 09:01 submit (24h tier),
  WHEN due is computed, THEN `add_business_days` skips the holiday to **Tue 09:01** AND the clamp
  snaps it to **Tue 17:00** (holiday skip and clamp compose correctly).
- **CLAMP-8 `[T]` (REGRESSION, hard)** GIVEN a **3h** response tier (the `< 24h` branch) and a **Sat
  09:01** submit, WHEN due is computed, THEN it is **Mon 12:00** via `add_working_hours`,
  byte-identical to today (the `< 24h` branch is NOT touched — it already window-clamps).
- **CLAMP-9 `[T]`** the clamp is provably one-sided — for a representative sweep of submit
  times/days, the clamped due is always `>=` the unclamped due (never earlier).

## Group FUNNEL — placement + scope (blast-radius containment)

- **FUNNEL-1 `[T]`** the clamp lives in **`_working_due_naive`** only. GIVEN a direct call to
  `CalendarService.add_business_days` / `add_working_days` / `add_working_days_from_hours` with a
  pre-open time, WHEN it returns, THEN the raw (unclamped) value is returned — those callers are
  unchanged.
- **FUNNEL-2 `[T]` (REGRESSION, hard)** GIVEN the SLA **extend-deadline** path (`sla_service`, uses
  `add_working_days` / `count_working_days`) and the **conversation-SLA** path, WHEN their existing
  tests run, THEN all stay green (no behavioural change).
- **FUNNEL-3 `[T]`** the clamp applies to **response due** (`due_at`) at tracker start
  (`_start_for_config`, `form_sla_service.py:821`).
- **FUNNEL-4 `[T]`** the clamp applies to **resolution due** (`due_at_resolution`) at start.
- **FUNNEL-5 `[T]`** the clamp applies to **escalation** — next-tier due recomputed in
  `_escalate_tracker` (`form_sla_service.py:501-508`) is also clamped.
- **FUNNEL-6 `[T]`** clamp applies for **all four** `source_entity_type`s (`purchase_request`,
  `sponsorship_form`, `complaint`, `stock_inquiry`) with a `>= 24h` tier — one funnel, one behaviour.

## Group DISPLAY — the FE just shows the corrected due (no FE logic)

- **DISPLAY-1 `[FE]`** GIVEN a form whose tracker due was clamped, WHEN its detail page renders the
  SLA due date, THEN it shows the clamped value via `formatDateTimeInMalaysia` (no new FE code beyond
  what already renders `due_at`; this AC is a visual confirmation, not new behaviour).

## Group E2E — round-trip (light; the logic is unit-proven)

- **E2E-1 `[E2E]`** Seed/submit a form on a Saturday-equivalent fixture with a 24h tier; navigate via
  sidebar to its detail; assert the displayed response-due time is the end-of-working-day (17:00), not
  an early-morning time. *(May be covered by service tests + a targeted DTO assertion if a
  clock-controlled E2E fixture is impractical — note in the report.)*

---

## Test report skeleton (fill in Phase 2, key back to these ids)

| AC id | Layer | Test file / verification | Result |
|-------|-------|--------------------------|--------|
| CLAMP-1..CLAMP-9 | pytest | `tests/test_form_sla_workday_clamp.py` | ☐ |
| FUNNEL-1,FUNNEL-2 | pytest | `tests/test_form_sla_workday_clamp.py` + existing SLA suites | ☐ |
| FUNNEL-3..FUNNEL-6 | pytest | `tests/test_form_sla_workday_clamp.py` | ☐ |
| DISPLAY-1 | manual/MCP | form detail render | ☐ |
| E2E-1 | playwright / DTO | `e2e/form-sla-clamp.spec.ts` or DTO assertion | ☐ |
