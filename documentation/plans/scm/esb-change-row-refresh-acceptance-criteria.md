# UAC: ESB re-push retires a stale pending change row (#1240)

Plan: `PLAN-esb-change-row-refresh.md`. Journey: two AutoCount pushes of one SO three
minutes apart; the board and Confirm must follow the second push.

## S1 build_batch

- **AC-1 [BE]** Order has one inquired line. Push 1 adds line L at D1. `build_batch`
  writes one pending `added` row for L with `to_json.required_date = D1`.
- **AC-2 [BE]** Push 2 moves L to D2, L still not held and not inquired. `build_batch`
  writes no new row for L and sets the `added` row from AC-1 to
  `applied_state = superseded`, `applied_reason = "Line changed again; the row no longer
  describes it"`. Core `required_date` for L is D2.
- **AC-3 [BE]** Push 2 carries facts identical to push 1 (same qty, date, status). The
  `added` row stays `pending`, untouched.
- **AC-4 [BE]** Push 2 moves an INQUIRED line. Existing behaviour holds: a `delayed` row is
  pending and the older row for that line is `superseded` with "Replaced by a later change".
- **AC-5 [BE]** Batch `line_count` after AC-2 counts every row the batch ever carried
  (superseded included), unchanged from today's append-only rule.

## S2 mirror follows core

- **AC-6 [BE]** After push 2 (AC-2), the mirror `projects.sales_order_lines` row whose
  `core_sales_order_line_id` is L has `delivery_date = D2` and `qty` equal to core
  `qty_ordered`.
- **AC-7 [BE]** A manual SO edit (`sales_order_service.update`) that changes a line's
  `required_date` or `qty_ordered` updates the mirror line the same way.
- **AC-8 [BE]** A line with no mirror (order never adopted) is left alone; no error.

## S3 board overlay

- **AC-9 [FE]** `uncoverChangedLines` on a contribution with `required_date = D2`,
  `qty_outstanding = 5`, `is_past = false`, `bucket_key = K2` and a batch proposal frozen
  at D1 returns `required_date = D2`, `qty_outstanding = 5`, `is_past = false`,
  `bucket_key = K2`, `covered = false`, `decision = null`, and the proposal's `sources` and
  `qty_proposed_buy`.
- **AC-10 [FE]** With no batch, `uncoverChangedLines` is the identity (existing test pin).

## S4 overlay ignores non-pending rows

- **AC-13 [FE]** Given a batch payload where line L's only row has `applied_state =
  'superseded'` (proposal frozen at D1), `uncoverChangedLines` returns L's contribution
  unchanged (`required_date = D2`, `covered` and `decision` untouched), `preMarkedKeys` omits
  L's key, and `annotationsByLine` / `annotationsByCell` hold nothing for L.
- **AC-14 [FE]** Given line M with a superseded row (D1) and a pending row (D3), the overlay
  and annotations use only the pending row.
- **AC-15 [FE]** Rows with `applied_state = 'applied'` still overlay and pre-mark exactly like
  a `pending` row - `superseded` is the only state S4 retires from the overlay. Captain ruling,
  R3 (`PLAN-board-draft-on-confirmed-line.md`, review round 3), restated for #1240: only the
  BATCH's own `applied_at` gates whether a line stays covered and blocked from a second
  Confirm, never a row's own `applied_state` - pinned by `FulfilmentBoardPanel.change.test.tsx`'s
  "does not block Confirm ... even if a row says it was".

## S5 Change proposed is not Saved (owner ruling 25 Sep 2026, #1245)

- **AC-16 [FE]** A board whose batch pre-marks N lines and where nothing has been saved reads
  "0 to confirm", the Confirm button is disabled, and every pre-marked row's pill still reads
  "Change proposed".
- **AC-17 [FE]** "Save all suggested (M)" counts the pre-marked lines among M; pressing it saves
  them; their pills read Saved and "M to confirm" now counts them.
- **AC-18 [FE]** Confirm's request body contains only lines with a saved verdict; a pre-marked
  line the planner never saved is absent, and its batch row stays pending.
- **AC-19 [FE]** Reject (X) on a pre-marked line still counts as rejected and is sent as such.

## Apply

- **AC-11 [BE]** After AC-2, `apply` on that order raises no order-inquiry row for L at D1.

## Datafix (already run by the owner, 25 Sep 2026, prod)

- **AC-12 [DATA]** SO419122 batch `718bacd5`: 39 `added` rows superseded, remaining
  pending = 13 added @2028-01-04, 55 cancelled, 12 delayed @2027-10-01; mirror drift 0.
