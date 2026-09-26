# PLAN: the fulfilment board picks up a pending planning change on its own

**Status:** READY FOR PR, 12 September 2026 (built 39a5d8b07, reviewer fix round 22cf21e6c: per-order batch id never falls back onto a batchless order, one batch per order on the board, stable batch queries; hook is named usePlanningChangeBatchesByIds, the board-wide applied banner stays for the single-batch case only). Lane `lane/main-so-changes-12sep`, same lane as
`PLAN-scm-planning-change-gate-held-or-inquiry.md` (one lane, one PR).

## The problem, reproduced

User edited SO419772 line qty 134 to 234 on the SCM SO detail. The manual-edit trigger did
its job: batch `3beeca39` (`so_manual_edit`, `qty_up`, suggested `replan`, held Buy 134,
raised inquiry row) exists. Then the user opened the board from the fulfilment-planning list
(`/project-sales/fulfilment-planning?orders=SO419772`) and saw "Buy 134" and nothing else.

Cause: `FulfilmentBoardPanel` only fetches a batch when the URL carries `?batch=<id>`
(`FulfilmentPlanningClient.tsx:143`, `FulfilmentBoardPanel.tsx:240`). The only path that
writes that param is the `Changed` pill on the SCM Sales Orders list. Every other entry
(fulfilment-planning list, a bookmark, the SO detail's own board link) opens the board
blind. The fulfilment-planning list itself shows no change signal at all.

## The rule

A board knows, per order it shows, whether a pending planning change exists, and loads it
without being told. The URL `batch=` stays as an override for a deep link but is no longer
required. The fulfilment-planning list shows the same `Changed` pill the SCM list shows, and
it links to the board on that order (no `batch=` needed any more, but harmless if present).

## Changes

### Backend

1. One helper, three readers. `planning_change_service.pending_batch_id_by_sales_order(db,
   sales_order_ids) -> dict[str, str]`: newest pending batch (batch `applied_at IS NULL`,
   row `applied_state = 'pending'`) per core `sales_orders.id`, one query. The body is
   lifted out of `SalesOrderService.with_planning_changes` (`sales_order_service.py:1011`),
   which then calls it. No behaviour change on the SCM list.
2. `BoardOrderStanding.pending_change_batch_id: Optional[str]` (`schemas/project_board.py:1110`),
   populated in `FulfilmentBoardService._standings` (`project_fulfilment_board_service.py:4698`)
   from the helper keyed on the board's `sales_order_id`s.
3. `FulfilmentPlanningRow.planning_change_batch_id: Optional[str]`
   (`schemas/project_so_reconciliation.py:27`), decorated in
   `ProjectSOReconciliationService.list_fulfilment_planning` right before the envelope is
   returned (`project_so_reconciliation_service.py:1296-1305`), one query for the page.
4. Confirm: `batch_id` moves down to the order. `ConfirmManyOrderBody.batch_id:
   Optional[str] = None` (`schemas/project_supply.py:493`); `confirm_all`
   (`api/v1/projects/fulfilment_planning.py:408-414`) builds `_BatchedEntry(entry.lines,
   entry.batch_id or payload.batch_id)` per order. Body-level `batch_id` stays as the
   fallback so the current frontend keeps working during the deploy window.

### Frontend

5. `FulfilmentBoardPanel`: batch ids = distinct `board.orders[].pending_change_batch_id`
   unioned with the URL `batchId`. Fetch them with `useQueries` over
   `getPlanningChangeBatch`. Feed `{ orders: batches.flatMap(b => b.orders) }` to
   `uncoverChangedLines`, `preMarkedKeys` and `annotationsByCell` (no signature change,
   `boardChangeAnnotations.ts:170/239/309` already take `Pick<PlanningChangeBatch, 'orders'>`).
   `preMarked` becomes a `Set<batchId>` so a batch that arrives after the first render still
   seeds its suggestions exactly once. The applied guard is per order: an order whose batch
   has `applied_at` set is skipped with the existing "already applied" result; the board-wide
   `confirmBlockedReason` for an applied batch goes away (it only made sense with one batch).
   Confirm sends `orders: [{ pso_id, lines, batch_id }]`, `batch_id` = the batch that order's
   changed rows came from, null when the order has none.
6. `FulfilmentPlanningClient` list view: `Changed` pill in the `so_number` cell when
   `planning_change_batch_id` is set, copied from `SalesOrdersGrid.tsx:499-509`, linking to
   `/project-sales/fulfilment-planning?orders=<so>&batch=<id>`; `data-testid="so-changed-<so>"`.
   Types: `fulfilmentPlanning.types.ts:89` row gains `planning_change_batch_id?: string | null`;
   `project_board` types gain `pending_change_batch_id?: string | null` on the order standing;
   the confirm body type gains per-order `batch_id`.
7. Mocks: `_shared/__mocks__/planningChanges.ts` gains a second pending batch on a different
   `so_number` so a two-batch board is testable; the board mock's `orders[]` carry
   `pending_change_batch_id`.

## Not doing

- No polling or push. The board reads the batch on load; a change raised while the board is
  open shows on the next open, same as today.
- No new "changed" column on the list; the pill in the SO number cell is the SCM precedent.
- No change to how a batch is built or suggested (that is the gate plan).

## Verification

- pytest: board standing carries the id for an order with a pending batch and null otherwise;
  list row carries it; confirm-all with per-order `batch_id` applies that batch and marks its
  rows; body-level fallback still works; SCM list unchanged.
- vitest: board with no URL batch and one order flagged loads the batch, draws Was/Now, seeds
  the suggestion once; two orders on two batches merge; applied batch on one order skips that
  order only; confirm payload carries per-order `batch_id`; list renders the pill.
- Browser on :3050: open SO419772 from the fulfilment-planning list; Was 134 / Now 234 shows
  without `batch=` in the URL; the list row shows `Changed`.
