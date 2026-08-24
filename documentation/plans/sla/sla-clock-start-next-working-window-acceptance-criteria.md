# UAC - SLA clock starts at the next working-window open

Status: Draft (pre-code)
Date: 2026-07-20
Classification: CORE (SLA engine, not a toggleable module)
Related: `PLAN-sla-clock-start-next-working-window.md`

## Problem

An SLA clock currently starts at the raw event instant, even when that instant is
outside working hours. A stock inquiry submitted Sat 09:37 with a 72h (= 3 working
day) tier had its due computed from Sat 09:37, so the deadline carried a
weekend-anchored time-of-day. The team does not work weekends or nights, so the
responder never had the full window the policy promises.

## Rule

**Any SLA clock that starts outside a working window is normalized forward to the
next window open, in `Asia/Kuala_Lumpur`, before the duration is added.**

Working window = `work_calendar_configs.work_day_start_time` ..
`work_day_end_time` on a weekday flagged true, excluding `public_holidays`.
Production config today is Mon - Fri 08:00 - 18:00.

Window is half-open `[start, end)`: exactly `08:00:00` is inside, exactly
`18:00:00` is outside and rolls to the next open.

## Acceptance criteria

### Group A - the normalizer primitive

- **AC-1** Given a datetime on a working day inside the window, when normalized,
  then it is returned unchanged.
- **AC-2** Given a datetime on a working day before the window opens (e.g. Mon
  06:00), when normalized, then the result is the same day's window open (Mon
  08:00).
- **AC-3** Given a datetime on a working day at or after the window closes (e.g.
  Mon 18:00 or Mon 19:00), when normalized, then the result is the **next**
  working day's window open (Tue 08:00).
- **AC-4** Given a datetime on a non-working day (Sat 09:01), when normalized,
  then the result is the next working day's window open (Mon 08:00).
- **AC-5** Given a datetime whose next working day is a public holiday, when
  normalized, then the holiday is skipped to the following working day's open.
- **AC-6** Normalization is idempotent - normalizing an already-normalized value
  returns it unchanged.
- **AC-7** Input may be naive (interpreted as UTC) or aware; output is naive UTC.
- **AC-8** Given a degenerate work calendar (no working weekday, or non-positive
  window), when normalized, then the input is returned unchanged and a warning is
  logged - the SLA path never raises or hangs.

### Group B - due-date computation

- **AC-9** Given a 24h tier started Sat 09:01, when the due date is computed, then
  it is **Tue 08:00** (normalize to Mon 08:00, then +1 working day).
- **AC-10** Given a 72h tier started Sat 09:37, when the due date is computed, then
  it is **Thu 08:00** (normalize to Mon 08:00, then +3 working days).
- **AC-11** Given a sub-day tier (e.g. 3h) started Sat 09:01, when the due date is
  computed, then it is **Mon 11:00** - behaviour already correct via
  `add_working_hours`, and must not regress.
- **AC-12** Given any tier started **inside** a working window, when the due date is
  computed, then the result is unchanged from today's behaviour (no regression for
  the normal weekday case).

### Group C - the tracker's stored clock start

- **AC-13** Given a form SLA tracker created from an event outside working hours,
  when the tracker is written, then `current_tier_started_at` holds the
  **normalized** start (Mon 08:00), so the UI elapsed counter begins there.
- **AC-14** Given the same tracker, `initiated_at` holds the **true** event instant
  (Sat 09:37) - audit fidelity of when the user actually submitted is preserved.
- **AC-15** Given a form SLA tracker escalated outside working hours, when the tier
  advances, then `current_tier_started_at` is normalized while `escalated_at` holds
  the true escalation instant.
- **AC-16** Same as AC-13/AC-15 for the conversation SLA engine: automatic clock
  starts (create, escalate, tier/team change, resolve-reopen) normalize
  `current_tier_started_at`.
- **AC-17** Given an admin explicitly supplies `current_tier_started_at` via the
  update endpoint, when the row is saved, then the supplied value is stored
  **verbatim, not normalized** - an operator override is authoritative.

### Group D - no collateral damage

- **AC-18** The overdue predicate (`due_at < now`, `form_sla_service.py:411`) is
  unchanged and still compares naive UTC to naive UTC.
- **AC-19** Existing trackers are not retro-fitted. The change applies only to
  clocks started after deploy; no data migration.
- **AC-20** The extend-deadline path (`add_working_days` from an existing due) is
  unchanged.
- **AC-21** The <24h / >=24h split at `calendar_service.py:319` is left as-is; the
  23h-vs-24h inversion is out of scope and stays a known latent quirk.
- **AC-22** Full `pytest` suite green, including the existing
  `tests/test_working_hours_sla.py` cases.

## Out of scope

- Fixing the 23h/24h inversion (AC-21).
- Adding an explicit `start_tier` column to `form_sla_configs` (separate concern
  surfaced during the same investigation).
- Backfilling or repairing tracker `d7addb1a-0b43-4ace-96b6-d97096061870`.
