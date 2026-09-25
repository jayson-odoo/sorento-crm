# PLAN: ESB re-push must retire a stale pending change row (SO419122)

Status: implemented, review pending; issue #1240; lane `fix/esb-change-row-refresh`
(worktree `sorento_crm-esb-change-refresh`, private DB `sorento_ecr_ci`, redis 13). Opened
25 Sep 2026.

UAC: `esb-change-row-refresh-acceptance-criteria.md` (alongside).

## Journey

AutoCount pushes SO419122 twice within three minutes (ESB, `/external/ingest`,
`sales_orders`). Push 1 adds 52 lines at 15/01/2027. Push 2 moves 39 of them to
01/12/2026 / 01/11/2027 / 01/12/2027. The planner opens the fulfilment board and must see
each line at its CURRENT date with a live proposal, and Confirm must raise order inquiries
at the current date. Today the board prints 15/01/2027 ("Change proposed") and Confirm
would raise 39 OIs at that date.

## Measured cause (prod query by the owner + 24 Sep prod copy)

1. `planning_change_service.build_batch` (`app/services/planning_change_service.py`):
   push 1 kept 52 `added` rows (order-level gate: the order already had 13 inquired lines).
   Push 2's date move on the 39 un-inquired lines fails the per-line held-or-inquiry gate,
   `_build_row` returns None and the loop `continue`s at `:1080` BEFORE the
   supersede-the-older-row step at `:1087`. The 39 `added` rows from push 1 stay pending
   with `to_json.required_date` and `proposal_json` frozen at 15/01/2027.
2. Mirror `projects.sales_order_lines.delivery_date` is written on creation only; push 2's
   date change never reaches it (52 lines drift). Same for `sales_order_service.py:1792`
   (manual SO edit writes core only).
3. FE `uncoverChangedLines` (`_shared/lib/boardChangeAnnotations.ts:497`) does
   `{...contribution, ...proposal}`, so the frozen proposal's `required_date`, `qty`,
   `qty_outstanding`, `is_past`, `bucket_key` replace the live ones.
4. Apply writes OI `delivery_date` from `to_json.required_date`
   (`planning_change_service.py:3857`), so the stale row is not cosmetic.

## Fix (five seams, no migration, no auth change)

### S1 BE `build_batch`: a later change retires the older pending row even when it yields no row

In the per-entry loop, resolve `older = pending_lines.get(project_line_id)` BEFORE the
`if row is None: continue` exit. When `row is None` and `older` exists: mark `older`
`applied_state = superseded`, `applied_reason = "Line changed again; the row no longer
describes it"`, and continue - `orders_appended` is not touched on this path (there is no new
row to fold into an existing batch, only an older one retired in place). When `row` is not
None the existing replace-in-place path is unchanged. The `project_line_id` for the gate-failed
entry comes from `entry["project_line"]` (already resolved for every entry).

Review round 1: a pending `added` row commonly has NO `project_line_id` (a brand-new line has
no mirror yet), so `older` also falls back to a `core_line_id`-keyed map built from the same
open-batch query. `_entry_differs_from_older_row` also returns true for a `PRODUCT_CHANGED`
kind or an `item_code` that now differs from the older row's.

Only when the change actually alters what the older row describes (kind, qty or date
differ from `older.to_json`) - a re-push with identical facts must leave the row alone
(idempotent pushes are the normal case).

### S2 BE mirror follows core

`DocumentIngestService` sales-order apply (and `sales_order_service.update` manual edit):
after the core line's `required_date` / `qty_ordered` change, write the same values to the
mirror line found by `core_sales_order_line_id` (`delivery_date`, `qty`). One UPDATE per
changed line, inside the same transaction. No new table, no listener.

### S3 FE overlay keeps the live facts

`uncoverChangedLines`: after the spread, restore from the live contribution
`required_date`, `qty`, `qty_ordered`, `qty_delivered`, `qty_outstanding`, `is_past`,
`bucket_key`, exactly as it already restores `order_inquiry`. The batch proposal
contributes only the composition (`sources`, `qty_proposed_*`, `proposed`, `options`,
`locations`, `buy_origin`).

### S4 FE the overlay ignores rows that are no longer pending

Measured on prod after the datafix (25 Sep, 39 rows superseded, mirror drift 0): the board
STILL printed 15/01/2027 "Change proposed" for the 39 lines. `get_batch`
(`planning_change_service.py:2334`) returns every row of the batch, superseded and applied
included (append-only record, by design), and `proposalsByLine`, `annotationsByLine`,
`changedLineIds` and `preMarkedKeys` in `boardChangeAnnotations.ts` read `order.rows`
without looking at `applied_state`. So a superseded row still overlays its frozen proposal
and still pre-marks the line. Fix in the FE helpers: skip any row whose `applied_state` is
not `pending` (one shared predicate, used by all four). Superseded rows stay visible in the
batch lightbox / history as today; only the board overlay and pre-mark stop reading them.

### S5 FE a "Change proposed" line is a label, not a saved decision (owner ruling 25 Sep 2026, issue #1245)

Owner, after SO419122 read "Confirm (119)" with nothing ticked and one press handed 49 rows to
purchasing: "we should mark it as Change proposed, but it is not considered Saved". Supersedes
the Confirm half of the 18 Sep pill ruling (AC-C7 of PLAN-board-change-proposed-pill).

`FulfilmentBoardPanel.tsx`: the pre-mark effect still seeds `{ verdict: 'approved', preMarked:
true }` so the pill, the per-row proposal and the change icons keep working, but:
- `confirmSummary` ("N to confirm", the Confirm (N) label) and `runConfirmAll` skip every draft
  with `preMarked: true`. Only a verdict a person saved (row approve, amend, quick-save, Save all
  suggested) counts and is sent.
- "Save all suggested (N)" counts and saves pre-marked lines too, so tick + Save all turns
  "Change proposed" into Saved in one motion; `decide()` already overwrites the pre-mark object,
  so the flag drops itself on save.
- Reject (X) unchanged. A pre-marked line nobody saved is left alone by Confirm: its batch row
  stays pending.

## Out of scope

- The SO419122 rows themselves: one-off datafix SQL (scratchpad `so419122_datafix.sql`,
  run by the owner 25 Sep 2026: 39 stale `added` rows superseded, mirror = core).
- Re-walking the ladder for a gate-failed line. A line nobody planned gets no row, by
  the standing gate rule; it shows on the board as plain undecided demand.

## Test list (tester writes these red first)

BE `tests/test_planning_changes.py` (or a new `tests/test_planning_change_repush.py`),
against `blank_session()`:

- T1 push 1 adds a line at D1 on an order with one inquired line -> one pending `added`
  row; push 2 moves that line to D2 (line still un-inquired) -> the `added` row is
  `superseded` with the reason, no new row, core `required_date` = D2.
- T2 same as T1 but push 2 carries identical facts -> the `added` row stays `pending`.
- T3 push 2 moves an INQUIRED line -> existing behaviour: `delayed` row pending, older row
  superseded (regression pin).
- T4 mirror: after push 2 the mirror line's `delivery_date` and `qty` equal core.
- T5 manual SO edit of `required_date` updates the mirror too.
- T6 apply on an order after T1 raises no OI row at D1 (nothing pending for that line).

FE `boardChangeAnnotations.test.ts`:

- T7 `uncoverChangedLines` keeps the live `required_date`, `qty_outstanding`, `is_past`,
  `bucket_key` and takes `sources` / `qty_proposed_buy` from the proposal.
- T9 (S5) FulfilmentBoardPanel.change.test.tsx: a board with pre-marked lines and nothing saved
  reads "0 to confirm", Confirm disabled; Save all suggested (N) counts the pre-marked lines; after
  Save all the same lines count and Confirm's payload carries them; a pre-marked line left unsaved
  is absent from the Confirm payload; reject still works.
- T8 a batch whose only row for a line is `applied_state = superseded` (or `applied`):
  `uncoverChangedLines` leaves that contribution untouched, `preMarkedKeys` does not name
  it, `annotationsByLine` / `annotationsByCell` carry no annotation for it. A line with a
  superseded row AND a pending row uses the pending one only.

## Browser pass

None owed: no screen changes; the board reads the same fields. The owner re-checks
SO419122 on prod after deploy.
