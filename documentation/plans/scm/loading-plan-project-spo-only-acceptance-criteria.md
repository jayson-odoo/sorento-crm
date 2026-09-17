# UAC: loading plan - Project column nets SPO placements only

Plan: PLAN-loading-plan-project-spo-only.md (18 Sep 2026)

## Backend - `container_request_service.build` (S1)

- AC-P1: A project SO line of 100, open, before cut-off, with a 100-unit
  `order_inquiry_links` row whose `po_line_id` is set and `spo_allocation_id` is null,
  counts `project_qty == 100` and `open_so_need == 100`. The row is present.
- AC-P2: The same line with a 100-unit link whose `spo_allocation_id` is set counts
  `project_qty == 0`; with no other demand the product has no row (`rows == []`).
- AC-P3: A line of 100 with 30 on an SPO link and 70 on a PO link counts
  `project_qty == 70` (SPO nets, PO does not).
- AC-P4: A line of 100 with 30 on an SPO link only counts `project_qty == 70`.
- AC-P5: `include_lines=True` on AC-P3 lists that line once with `open_qty == 100` and
  `qty == 70`. On AC-P1 it lists `open_qty == 100`, `qty == 100`. On AC-P2 it is not
  listed.
- AC-P6: Invariant kept: for every demand row, `sum(line.qty for lines of that product)
  == open_so_need`, on a mix of PO-placed, SPO-placed and unplaced project lines plus a
  retail line. A retail line carries `open_qty == qty`.
- AC-P7: The horizon still applies after the change: a PO-placed line with
  `required_date` past `plan_horizon_date` is neither counted nor listed.
- AC-P8: `test_build_on_hand_nets_a_placed_projects_bin_stock_against_retail_demand` is
  rewritten so the "placed in full" line is placed on an SPO, and still passes with the
  same numbers.

## Frontend - PlanRowDialog Open tab (S2)

- AC-F1: The Open tab of the Project, Retail and Need lightboxes shows an `Open` column
  and a `Balance` column where `Qty` was, in that order, both right-aligned, both
  `fmtInt`. Column order: Sales order, (Channel), Customer, Project, Agent, Price, Open,
  Balance, Required.
- AC-F2: The footer under Balance is the tab's total (unchanged: `total` prop). The
  footer under Open is blank.
- AC-F3: `toDemandLines` maps `open_qty` from the build's `lines`; a line with
  `open_qty: 234, qty: 134` renders `234` and `134`.
- AC-F4: Existing PlanRowDialog tests updated for the extra column; no test asserts a
  `Qty` header on the Open tab any more.

## Browser (S3)

- AC-B1: On the lane stack (prod copy), CHAOZHOU JINBAICHUAN loading plan, CWB242: the
  Project popup lists SO414033 three times (14/09, 05/10, 19/10) with Open 234 and
  Balance 233 / 234 / 234; footer = Project cell.
- AC-B2: The popup total equals the Project cell on the row, and To request moved by the
  same amount as Project versus the pre-change figure (503 -> 1,204 on the 16 Sep copy:
  233 + 234 + 234 = 701, since the 14/09 line carries 1 on an SPO).
- AC-B3: Usable at 375px and 1280px; the two new columns do not clip.
