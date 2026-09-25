# UAC: the decision trail on screen (who saved, who confirmed, what raised)

Plan: `PLAN-oi-decision-trail-ui.md`. Issue #1238. Owner ruling 25 Sep 2026.

Field names below: AC-DT-3/AC-DT-6 say `raised_kind` / `raised_by_name` / `raised_at`.
Shipped as `raise_event_kind` / `raise_event_by_name` / `raise_event_at` instead - see the
plan's own "Deviation" note; `raised_by_name`/`raised_at` were already a different,
shipped fact on the same row.

- AC-DT-1 [BE][T] The fulfilment board response carries, for the order being planned, the
  active decision's `revision_no`, `confirmed_by_name`, `confirmed_at` and line count; all
  null-safe when the order has no decision.
- AC-DT-2 [BE][T] Every board line carries `decided_by_name`, `decided_at`,
  `decision_revision` (from the active decision holding that line's snapshot) and
  `draft_saved_by_name`, `draft_saved_at` (latest draft for the core line); `None` where
  absent. Asserted on the actual response payload, not on a helper.
- AC-DT-3 [BE][T] Every worklist / Lines-tab row carries `raised_kind`, `raised_by_name`,
  `raised_at`, read from the `order_inquiry_raises` event of the same inquiry with the smallest
  `raised_at` inside `[created_at - 1s, created_at + 10 min]` (review round 1: the upper bound
  keeps a row with no event of its own off the next reconfirm hours later); a row with no such
  event within the window carries `None` on all three. One grouped query per page.
- AC-DT-4 [FE][T] Board header prints `Revision N · confirmed by <name>, <date time> · N
  lines` beside "N to confirm · N rejected", or `No decision yet`; one segment per order when
  several are planned together, order number first. Dates render in the app's existing
  format (`formatDateTimeInMalaysia`, e.g. `25/09/2026, 9:20 am`).
- AC-DT-5 [FE][T] The Confirmed verdict chip is a popover trigger (a real button - tap at
  375px, keyboard reachable; review round 1, not a Tooltip) opening to `Confirmed by <name>,
  <date time> (revision N)` and, only when a draft exists, a second line `Saved by <name>,
  <date time>`. Other verdict chips are unchanged.
- AC-DT-6 [FE][T] The OI detail Lines tab shows a column titled `Raised via` (captain
  ruling, review round 1: `Raised` sat beside the existing `Raised by`; column id stays
  `raise_event`) after `Instruction`: `<Kind> by <name> · <date time>` where Kind is `Raised`,
  `Reconfirmed` or `Planning change` (note is exactly what `planning_change_service.py`
  writes: `Was <YYYY-MM-DD>`, `Was <qty>, now <qty>` or `No previous delivery date`; an
  ordinary `Was 5 on 2026-09-01` raise note is NOT one); a bare `Sheet` with no name or date
  when the note starts with "Migrated from order inquiry sheet", checked BEFORE any event
  (review round 1: sheet rows otherwise matched migration 523's anonymous backfill event or a
  later reconfirm); a dash when null. Dates in the app's existing format (`25/09/2026,
  9:20 am`). The worklist has the same column, hidden by default (column preferences apply).
- AC-DT-7 [FE] No UUID anywhere on screen; no explanatory sentence in the UI; every date in
  the app's existing date-time format; usable at 375px and 1280px (tooltip and header wrap).
- AC-DT-8 [BR] Browser run on this lane's :3086 stack against the 24 Sep prod copy, sidebar
  navigation from `/`: SO390524 board header reads revision 1 confirmed by Nurain on 25 Sep
  2026 with 11 lines; OI-2609-0731 Lines tab shows `Reconfirmed by Nurain · 25/09/2026,
  9:20 am` (the app's existing date format) on the CB6622-PP rows and a bare `Sheet` on the
  migrated rows.
- AC-DT-9 [DoD] No migration; PR body names the small fix track, the measured diff, and
  states `security-reviewer` was not run (no auth, RBAC, ingest, upload or multi-company
  change).
