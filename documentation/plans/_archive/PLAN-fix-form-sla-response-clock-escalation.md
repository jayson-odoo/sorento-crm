# PLAN - Fix form-SLA escalation on stale response clock (+ event-log TZ & duration)

**Status:** IMPLEMENTED (Phase 2 done) - pending Phase 3 review + PR

## Implementation summary (2026-07-02)
- **Fix 1** `form_sla_service.py` `scan_overdue_and_escalate` - added `is_responded` guard to the overdue computation. Verified: pytest + real scan (`escalated:0` for the bug scenario) + FE (CMP2026-0014 stays Tier 1 / Pending though response due is Overdue).
- **Fix 2** `form_sla_service.py` `_write_event_log` - wrapped `event_at` + `due_at` in `_to_aware_utc`. Verified: buggy naive path stored −8h (21:05), fixed aware path stored correct UTC (05:05).
- **Fix 3** `EventLogTable.tsx` - extracted `formatEventDuration()` (exported, event-type-aware); cell delegates to it. Verified: vitest 6/6.
- **Tests:** `tests/test_form_sla_response_clock.py` (10 passed - UAC 1-4, 9, 10); `EventLogTable.test.tsx` (+4 duration cases). Pre-existing unrelated failure noted: `test_sla_due_escalations.py::test_escalate_without_reason...` fails on clean tree too (mock fragility, not this change).
**Owner:** jayson
**Origin:** Live bug on CMP26-0035 - a complaint responded on time, resolution extended to a future date, still escalated. Root-caused + reproduced end-to-end in the browser on local CMP2026-0014 (2026-07-02).

## Problem

Three clustered defects in the form-SLA escalation / event-log path.

### Bug 1 (PRIMARY) - escalation ignores `is_responded`
`FormSLAOrchestrator.scan_overdue_and_escalate` (`sorento_crm_backend/app/services/form_sla_service.py:340`):

```python
overdue = (due is not None and due < now) or (
    due_resolution is not None and due_resolution < now
)
```

`due` = response clock (`due_at`), `due_resolution` = resolution clock (`due_at_resolution`). The gate ORs the **response** clock with **no `is_responded` guard**. Once a tracker is responded, the response clock should stop mattering (KPI calc `sla_service.py:370` and active-due `:1028` already treat it as stopped post-response). Because `extend_tracking` only pushes `due_at_resolution`, a responded + resolution-extended tracker whose response `due_at` is in the past keeps being flagged overdue → escalates wrongly, then `_escalate_tracker` recomputes both clocks (clobbering the extension - this recompute is intended per product).

**Blast radius:** every `FORM_SLA_TYPES` entry - `complaint, purchase_request, stock_inquiry, sponsorship_form, ticket`.

**Why now:** gate written 2026-05-10 (`68914d8ec`). Conversation SLA got the correct split-clock guard 2026-06-06 (`38270f38f`, `list_due_escalations` `sla_service.py:2636`) - never back-ported to form SLA.

**Reference correct implementation** - `sla_service.py:2636`:
```python
or_(
    and_(is_responded == False, due_at != None, due_at < now),        # not responded → response breach
    and_(is_responded == True,  due_at_resolution != None, due_at_resolution < now),  # responded → resolution breach
)
```

### Bug 2 - form-SLA event logs written with naive datetimes (Event At 8h off)
`_write_event_log` (`form_sla_service.py:1041`) passes `event_at=_utc_naive_now()` and `due_at=<naive tracker due>` into `create_event_log`. Per the documented gotcha, `create_event_log` treats **naive datetimes as Malaysia time (UTC+8)**. The extend path (`sla_service.extend_tracking`) wraps with `_to_aware_utc`; escalation/assignment do not. Result: escalation "Event At" renders ~8h behind the true wall-clock (observed 4:09 AM vs the extend's 12:09 PM, seconds apart). Affects BOTH `_write_event_log` call sites - escalation (`:445`) and initial assignment (`:720`).

### Bug 3 - Event Log "Duration" negative on extend rows
FE `EventLogTable.tsx:207-212` computes duration as `event_at − from_time`. For an extend event, `extend_tracking` sets `from_time = old due_at_resolution` (a FUTURE date), so `event_at − from_time` is negative ("-1 day 23h…"). The `event_at − from_time` formula only holds for response/resolution events (from_time = initiated_at, in the past).

## Fixes

### Fix 1 - add `is_responded` guard to the form-SLA escalation gate
`form_sla_service.py:340`, mirror the conversation-SLA split-clock rule:
```python
responded = bool(getattr(tracker, "is_responded", False))
overdue = (
    (not responded and due is not None and due < now)
    or (due_resolution is not None and due_resolution < now)
)
```
- Post-response → gate on resolution clock only.
- Pre-response → response clock, unchanged.
- Escalation still recomputes both clocks (intended).
- **Scope (DECIDED):** guard lives ONLY in `scan_overdue_and_escalate`'s overdue computation. `_escalate_tracker` (shared) and manual `escalate_form_tracking` / FE "Escalate" stay ungated - pre-breach manual force-escalate of a responded tracker must keep working (`:489`).
- **Type-agnostic:** the gate filters candidates by `FORM_SLA_TYPES` then applies one overdue rule to all; the guard change therefore covers `ticket` and every other form type uniformly. `tickets_service.py:309` is a separate *display* flag, unaffected.
- **Edge:** responded + `due_at_resolution` NULL → `overdue = False` → never escalates (matches the conversation-SLA reference). Acceptable - no clock to breach.

### Fix 2 - wrap event-log datetimes in `_to_aware_utc`
In `_write_event_log`, import `_to_aware_utc` from `sla_service` and wrap `event_at` + `due_at` before constructing `ConversationSLAEventLogCreate`. Confirm no double-conversion in `create_event_log`.

### Fix 3 - Duration column: event-type-aware rendering
FE `EventLogTable.tsx` (shared - used by both `ConversationSLATrackingDetail` and `_shared/FormSLATrackerDetail`, so one edit fixes conversation + form/complaint surfaces). Render by `event_type`:
- `extend` → `+N working day(s)` from stored `duration` (interpreted as **days** - extend stores days, unlike response/resolution which store hours). Never the `event_at − from_time` diff (from_time = old/future due → negative).
- `response` / `resolution` → elapsed time (`event_at − from_time`), as today.
- `escalation` / `assign` (no from_time) → `-`.

Unit split to respect: `sla_service.py:4187` stores response/resolution `duration` in **hours**; `extend_tracking` stores `added_days` in **days**. The current FE fallback (`:216`) treats all as hours - the event-type branch supersedes it for extend. Leave `from_time` storage as-is (previous due, useful context); only the render changes.

## Decisions (grill 2026-07-02)
1. **Backfill → none.** Leave pre-fix escalations as historical noise; PR documents the fix is forward-only; ops corrects any live complaint ad hoc. No query, no mutation script.
2. **Fix 3 → event-type-aware** (see Fix 3): extend `+N working day(s)`, response/resolution elapsed, escalation/assign `-`. `from_time` storage unchanged.
3. **Scope → single PR** - all three fixes (same feature area, one screenshot narrative).
4. **Ticket → covered** by the type-agnostic guard; no special-casing.
5. **Guard scope → auto-scan only** (`scan_overdue_and_escalate`); manual `escalate_form_tracking` + FE Escalate stay ungated (pre-breach force-escalate preserved).

## Acceptance criteria (UAC)
- **UAC-1** Responded tracker, response `due_at` in the past, `due_at_resolution` in the future → scan does NOT escalate. (pytest, exact prod scan fn)
- **UAC-2** Responded tracker, `due_at_resolution` in the past → scan DOES escalate. (pytest)
- **UAC-3** Not-responded tracker, `due_at` in the past → scan DOES escalate. (pytest - no regression)
- **UAC-4** All 5 FORM_SLA_TYPES exercised for UAC-1/2/3 semantics (parametrized).
- **UAC-5** Escalation event log "Event At" renders in MYT consistent with the extend event (within seconds of real time), verified via API `event_at` value, not just UI.
- **UAC-6** Extend event-log row shows a non-negative, meaningful Duration (stored working-days or - ), never a negative timespan. (vitest on EventLogTable)
- **UAC-7** End-to-end browser: responded → extend via FE → response due lapses → scan → NOT escalated; both banners behave correctly. (Playwright MCP, mirrors the repro)
- **UAC-8** Existing conversation-SLA escalation path untouched (regression: `list_due_escalations` tests still green).
- **UAC-9** Responded tracker with `due_at_resolution` NULL → scan does NOT escalate and does NOT crash. (pytest)
- **UAC-10** Manual `escalate_form_tracking` on a responded, non-breached tracker still escalates (ungated) - no regression. (pytest)

## Three-phase breakdown
- **Phase 1 (prototype):** none - no new UI; Fix 3 is a tweak to an existing column. Skip, note here.
- **Phase 2 (wiring + tests):**
 - BE: Fix 1 + Fix 2 in `form_sla_service.py`.
 - FE: Fix 3 in `EventLogTable.tsx`.
 - Tests: pytest (UAC 1-4, 8) reusing the repro harness (`scratch_repro_*.py` → promote to `tests/test_form_sla_response_clock.py`); vitest for UAC-6; Playwright MCP for UAC-7.
- **Phase 3 (review):** `/code-review`, then PR with before/after screenshots (`before-scan-tier1.png`, `after-scan-tier2-escalated.png`, `repro-0014-both-banners-like-0035.png`).

## Cleanup
- Remove local scratch files: `sorento_crm_backend/{scratch_repro_setup,scratch_repro_scan,scratch_repro_reset,scratch_repro_ff}.py`, root `repro_*.py`.
- Local dev DB has ~78 trackers escalated by repro scans + CMP2026-0014 mutated - dev-only noise; reset if it bothers testing.
