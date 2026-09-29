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
- AC-DT-5 [FE][T] (round 2, replaces round 1's popover) A History icon button sits beside
  the State pill on the OI worklist and the Lines tab (every row, not only a reserved one)
  and right after the verdict chip on the fulfilment board (list view and grid cell
  breakdown), shown there only when the line carries a decision, a draft or an order
  inquiry - `aria-label="Decision trail"`, `title="Decision trail"`, ghost variant, same
  size as the reserve History icon it sits beside / the board's own verdict pencil. It
  opens `DecisionTrailDialog`, reading `GET .../sales-order-lines/{core_line_id}/
  decision-trail`. The Confirmed verdict chip carries no popover of its own any more (the
  round-1 tooltip and its vitests are retired); the pre-round-1 Saved-by popover on a
  non-confirmed draft line is unchanged.
- AC-DT-10 [BE][FE][T] `GET /api/v1/project-sales/sales-order-lines/{core_line_id}/
  decision-trail` returns `{"entries": [...]}`, newest first, each entry `{"kind",
  "actor_name", "at", "detail"}`. Sources, keyed by the CORE sales-order line
  (`OrderInquiryRow.so_line_id` -> the project mirror -> `core_sales_order_line_id`;
  `BoardContribution.line_id` names it directly): every `so_supply_decisions` revision
  (active AND superseded) whose `line_snapshots` names the line (`confirmed`); the one
  `so_supply_decision_drafts` row for the line, if any (`saved`); the `order_inquiry_raises`
  event matched to each of the line's own OI rows by the same window
  `_raise_events_by_row` (now `nearest_raise_event`, shared) uses, or `sheet` when that
  row's note starts with the sheet-migration stamp, checked first (`raised` /
  `reconfirmed` / `sheet`), PLUS (round 3 reviewer B3) one entry per raise event of that
  same inquiry landing more than 10 minutes past a row's own birth that no row's own
  origin match already reported - deduped one per `(inquiry, event)` even when several of
  the line's own rows share the inquiry, and never for an event some row's own origin
  match already carries; and, independently, a `planning_change` entry for any such row
  whose note matches the exact `planning_change_service.py` stamps. 404 on an unknown
  line id; an empty list when the line carries nothing; `response_model` keeps all four
  keys on the actual response. (Amended round 3, reviewer: a `sheet` entry's `at` is the
  row's own `created_at`, not `None` - the row is a real fact with a real time, so it
  sorts among the other entries rather than always trailing them; `actor_name` stays
  `None`, the sheet import records no uploader.) `DecisionTrailDialog` (`_shared/
  components/` - round 3 reviewer N2: shared code must not import from a route folder)
  renders each entry as a card - the kind label and the detail, then, when `actor_name`
  is null (a `sheet` mark, a `planning_change` note, or an anonymous backfill `raised`/
  `reconfirmed` event), ONLY the date, with no actor line at all - never "Unknown", which
  would claim a person was simply left unnamed; every other entry keeps the actor and,
  when present, the date - in the app's existing format. `No trail recorded yet.` is the
  empty state; a skeleton renders while the read is in flight and `extractApiError`'s own
  message renders on a failed one (round 3 reviewer S1), neither ever mistaken for the
  empty state.
- AC-DT-6 [FE][T] (amended round 2: hidden by default on BOTH screens now) The OI detail
  Lines tab AND the worklist both show a column titled `Raised via` (captain ruling, review
  round 1: `Raised` sat beside the existing `Raised by`; column id stays `raise_event`,
  hidden by default on both - column preferences let it on either screen), after
  `Instruction`: `<Kind> by <name> · <date time>` where Kind is `Raised`, `Reconfirmed` or
  `Planning change` (note is exactly what `planning_change_service.py` writes:
  `Was <YYYY-MM-DD>`, `Was <qty>, now <qty>` or `No previous delivery date`; an ordinary
  `Was 5 on 2026-09-01` raise note is NOT one); a bare `Sheet` with no name or date when the
  note starts with "Migrated from order inquiry sheet", checked BEFORE any event (review
  round 1: sheet rows otherwise matched migration 523's anonymous backfill event or a later
  reconfirm); a dash when null. Dates in the app's existing format (`25/09/2026, 9:20 am`).
  The column carries an `accessorFn` so the shared column picker
  (`data-grid-column-visibility.tsx`) can list and re-enable it.
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
- AC-DT-11 [FE][T] (round 2) The board's own Stock button (Outstanding qty column) is icon
  only - the `<span>Stock</span>` label is gone - and ghost variant, matching the
  verdict-row pencil (`BoardVerdictActions.tsx`); `aria-label="Stock"` and `title="Stock"`
  are kept.
