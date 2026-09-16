# PLAN - Planning record mirrors every core line on its own (no Re-sync click)

Status: **BUILT 17 Sep 2026, review READY, PR pending.** Issue #969. UAC: `scm-planning-record-mirror-acceptance-criteria.md`.
Owner ruling 16 Sep 2026 ("i think we should go with the fixes"): code fixes, no backfill script.

## 0. What the owner hit

Confirming SO390808 on the fulfilment board (0915 production copy, 16 Sep): "SRTKS915 line 4,
CKSW015 line 3 are not on the planning record yet, so this confirmation leaves them out. Re-sync
the sales order to add them." Measured on that copy: 51 open orders carry 354 open core lines
with no planning-record mirror.

The owner then tested SO384897 on the same copy (17 Sep) and the gap there is NOT a late
ingest. Measured: its planning record was created 2026-09-14 02:24, all 194 of its core lines
were created on or before 7 September, before the record existed at all, and 64 of them carry
no mirror (20 still open).

## 1. Why (measured)

- The board plans on the adopted copy (`projects.sales_orders` / `projects.sales_order_lines`,
  the "planning record"). A core line with no mirror line cannot be confirmed
  (`unpostableNotices.ts` reason `no_mirror`; `project_board.py` `project_line_id` null).
- **Two causes, measured** (`sorento_ai_automation_0915_1900`, read-only): unmirrored OPEN
  lines on adopted, unauthored records split by `line.created_at < planning_record.created_at`.
  174 lines across 46 orders existed BEFORE their record's adoption - the 14 Sep sheet
  migration (`adopt_for_migration`) mirrored only the lines the Order Inquiry sheet named, not
  every line the order carried, and SO384897 (section 0) is this shape.
- 220 lines across 16 orders arrived AFTER adoption, from the AutoCount ingest that landed on
  prod before the backup was taken - the shape SO390808 (section 0) is. Only two places add
  missing mirrors today, both on demand: `ProjectSOAdoptionService.adopt` (already-adopted
  branch) and `ProjectSOReconciliationService` for an adopted order (the planning sheet's
  Re-sync button), both via `ProjectSOAdoptionService.mirror_missing_lines(order)`
  (`project_so_adoption_service.py:180`, additive, stable line numbers).
- The line ingest `scm/sales_order_service.py::_upsert_lines` (1599) inserts new core lines
  (1762) and PRUNES empty adoption mirrors for removed lines, but never adds a mirror for a new
  line. The September sheet migration (`adopt_for_migration`) mirrored only the lines the sheet
  named.

## 2. Journey

CS opens the board for an order whose lines changed in AutoCount after adoption, ticks the lines,
presses Confirm. Every line is on the record; the confirmation posts. Nobody presses Re-sync.
Purchasing's reorder plan sees the new lines' demand as soon as the ingest lands them.

## 3. Design (simplest thing that works, two seams)

1. **Board read self-heals.** When the backend builds the fulfilment board for an adopted
   order (`GET /fulfilment-planning/board`, `FulfilmentBoardService.build`, the one read the
   FE's `fulfilmentBoard.ts` derives `no_mirror` from and the list confirm-all reads too), it
   first runs `ProjectSOAdoptionService.mirror_missing_lines(order)` for each selected order
   (gated `status = 'adopted'`, `project_id IS NULL`) and flushes, so every core line comes
   back with a `project_line_id`. The confirm write (`POST /sales-orders/{pso_id}/confirm`,
   `POST /fulfilment-planning/confirm-all`) stays a pure write and never mirrors on its own:
   one seam, not two.
   Owner ruling 17 Sep 2026 (B2): heal on the board read, so the first Confirm posts every
   line; historical gaps heal when the board is opened. It heals both causes: a line the
   migration skipped and a line an ingest added later; the ingest seams stop the second from
   recurring, the first cannot recur (the migration ran once, `adopt` mirrors every line).
2. **Ingest re-mirrors.** Review round 1 found `_upsert_lines` has ONE caller, the manual FE edit
   (`PUT /sales-orders/{so_id}`); the ESB push and the book upload each write core lines their
   own way, bypassing it entirely. So the same call lands at all THREE writers, each gated on the
   order carrying an adopted, unauthored mirror (`projects.sales_orders.so_id = so.id`,
   `status = 'adopted'`, `project_id IS NULL`), in the same transaction as the write, symmetric
   with the prune each already does or is adjacent to:
   - `scm/sales_order_service.py::_upsert_lines` - the manual FE edit.
   - `document_ingest_service.py::DocumentIngestService._sync_lines` - the AutoCount ESB push
     (`POST /api/v1/external/ingest/sales_orders`), the true writer behind almost every
     unmirrored line measured live (394 of 394, all `source_system = autocount`).
   - `outstanding_import_service.py::apply` - the Excel book upload, called per order right
     after that order's own line-create pass, not per row.

No new table, no flag, no script. Existing gaps heal on the first board read or the first ingest.

## 4. Tests (captain's list, tester first)

| AC | test | assertion |
| --- | --- | --- |
| PR1 | `test_board_read_mirrors_missing_line_then_confirm_posts` | adopted order, add a core line after adoption, read the board: the late line carries a `project_line_id` and its mirror exists; confirm every returned line: `lines_undecided == 0`, the decision covers it |
| PR2 | `test_board_list_read_mirrors_for_every_order` | two adopted orders each with one late core line: the multi-order board read heals both (mirrors exist, `project_line_id` set); confirm-all posts both |
| PR3 | `test_ingest_new_line_on_adopted_order_mirrors_it` | `_upsert_lines` with a payload adding a SKU on an adopted order: a mirror line with `core_sales_order_line_id` exists after the call, line_no = max + 1 |
| PR3b | `test_esb_ingest_new_line_on_adopted_order_mirrors_it` | the ESB push (`POST /api/v1/external/ingest/sales_orders`, `document_ingest_service._sync_lines`) creates a new core line on an adopted order: a mirror line for it exists in the same transaction, line_no = max + 1, the core line carries `source_system = autocount` |
| PR3c | `test_outstanding_book_upload_new_line_on_adopted_order_mirrors_it` | the outstanding book upload (`outstanding_import_service.apply`) creates a new core line on an adopted order: a mirror line for it exists in the same transaction, line_no = max + 1 |
| PR4 | `test_ingest_on_unadopted_order_adds_no_mirror` | same payload on an order with no planning record: no `projects.sales_order_lines` row |
| PR5 | `test_ingest_prune_and_mirror_in_one_pass` | payload removes one line and adds one: the empty mirror is pruned, the new one mirrored, existing mirrors keep their line_no |
| PR6 | `test_mirror_is_idempotent_on_board_read` | read the board twice: no duplicate mirror lines |
| PR8 | `test_confirm_without_a_prior_board_read_does_not_mirror` | adopted order plus a late line, confirm the existing lines directly with no board read: confirm succeeds, no mirror is created (pins the seam) |

## 5. After merge

Owner re-tests SO390808 style orders on the copy: no message, confirm posts. Guide line in
`sales-order-changes.md` ("Re-sync is no longer needed for adopted orders").
