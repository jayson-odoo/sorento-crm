# PLAN - Planning record mirrors every core line on its own (no Re-sync click)

Status: **APPROVED 17 Sep 2026, building.** Issue #969. UAC: `scm-planning-record-mirror-acceptance-criteria.md`.
Owner ruling 16 Sep 2026 ("i think we should go with the fixes"): code fixes, no backfill script.

## 0. What the owner hit

Confirming SO390808 on the fulfilment board (0915 production copy, 16 Sep): "SRTKS915 line 4,
CKSW015 line 3 are not on the planning record yet, so this confirmation leaves them out. Re-sync
the sales order to add them." Measured on that copy: 51 open orders carry 354 open core lines
with no planning-record mirror.

## 1. Why (measured)

- The board plans on the adopted copy (`projects.sales_orders` / `projects.sales_order_lines`,
  the "planning record"). A core line with no mirror line cannot be confirmed
  (`unpostableNotices.ts` reason `no_mirror`; `project_board.py` `project_line_id` null).
- Only two places add missing mirrors today, both on demand:
  `ProjectSOAdoptionService.adopt` (already-adopted branch) and
  `ProjectSOReconciliationService` for an adopted order (the planning sheet's Re-sync button),
  both via `ProjectSOAdoptionService.mirror_missing_lines(order)`
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

1. **Confirm self-heals.** At the top of the board confirm paths, for each order in the batch,
   call `mirror_missing_lines(order)` and flush BEFORE the line index is built, so a line that
   arrived after adoption is confirmable in the same click. Paths: `POST /sales-orders/{pso_id}/confirm`
   (`fulfilment_planning.py:599`) and `POST /fulfilment-planning/confirm-all` (383), and the
   planning-change apply per order if it builds the same index (coder verifies; one seam inside
   the service that both routes pass through is preferred over two route-level calls).
2. **Ingest re-mirrors.** In `_upsert_lines`, after the new core lines are inserted, if the order
   has an adoption mirror (`projects.sales_orders.so_id = so.id`, status `adopted`), call
   `mirror_missing_lines` for it in the same transaction. Symmetric with the prune it already does.
   Applies to every caller of `_upsert_lines` (outstanding-book upload, AutoCount ESB ingest;
   coder lists the callers in the PR).

No new table, no flag, no script. Existing gaps heal on the first confirm or the first ingest.

## 4. Tests (captain's list, tester first)

| AC | test | assertion |
| --- | --- | --- |
| PR1 | `test_confirm_mirrors_missing_line_then_posts` | adopted order, add a core line after adoption, confirm it: no `no_mirror` skip, the mirror line exists, the decision covers it |
| PR2 | `test_confirm_all_mirrors_for_every_order` | two adopted orders each with one late core line: confirm-all posts both |
| PR3 | `test_ingest_new_line_on_adopted_order_mirrors_it` | `_upsert_lines` with a payload adding a SKU on an adopted order: a mirror line with `core_sales_order_line_id` exists after the call, line_no = max + 1 |
| PR4 | `test_ingest_on_unadopted_order_adds_no_mirror` | same payload on an order with no planning record: no `projects.sales_order_lines` row |
| PR5 | `test_ingest_prune_and_mirror_in_one_pass` | payload removes one line and adds one: the empty mirror is pruned, the new one mirrored, existing mirrors keep their line_no |
| PR6 | `test_mirror_is_idempotent_on_confirm` | confirm twice: no duplicate mirror lines |

## 5. After merge

Owner re-tests SO390808 style orders on the copy: no message, confirm posts. Guide line in
`sales-order-changes.md` ("Re-sync is no longer needed for adopted orders").
