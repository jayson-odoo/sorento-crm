# UAC - Loading plan lightbox feedback, 3 Sep 2026

Plan: `PLAN-scm-loading-plan-lightbox-feedback-3sep.md`. Tags: `[FE]` vitest, `[BE]` pytest,
`[E2E]` agent-browser evidence on :3130 via the sidebar.

## A. Channel history (S1)

- **AC-A1** `[FE]` History tab renders Month · Project · Retail with no "Project peak" /
  "Retail peak" text anywhere.
- **AC-A2** `[FE]` The Project column's highest cell carries `data-peak="project"` and the
  Retail column's highest cell `data-peak="retail"`; exactly one per column when that column
  has any month > 0; first wins a tie; none when the column is all 0.
- **AC-A3** `[FE]` Total row still sums both columns.
- **AC-A4** `[E2E]` Grid Project-peak cell opens the Project dialog on the history tab with
  that month tinted.

## B. Need lightbox (S2)

- **AC-B1** `[FE]` The Need cell is a button; clicking opens a dialog titled `Need · <code>`.
- **AC-B2** `[FE]` Open tab lists project and retail lines together with a Channel column;
  its Total equals the Need figure on the row.
- **AC-B3** `[FE]` History tab shows Month · Project · Retail · Total; Project, Retail and
  Total peak cells are each marked (`data-peak="total"` on the third).
- **AC-B4** `[FE]` Set row: lines and history are the driver member's.

## C. Quantities in tab labels, no header context (S3)

- **AC-C1** `[FE]` Channel open tab label: `Open before cut-off <dd/mm/yyyy> (<sum qty>)`;
  without a horizon `Open (<sum qty>)`.
- **AC-C2** `[FE]` SPO tabs: `Open to pools (<sum qty>)`, `History (<sum qty>)`.
- **AC-C3** `[FE]` PO tabs: `Open (<sum still_to_come>)`, `History (<sum qty_ordered>)`.
- **AC-C4** `[FE]` No dialog renders a context string beside the title; `PlanRowDialog` has
  no `context` prop.

## D. SPO dialog (S4)

- **AC-D1** `[BE]` `GET /container-requests/drill?kind=spo` rows carry `container_number`
  (the shipment's `shipping_container_number`), null when the allocation has no shipment.
- **AC-D2** `[FE]` Column header reads Container; value is the number or a dash. No
  "Packing list", "Draft" or "Not shipped" text in the column.
- **AC-D3** `[FE]` Status renders as a Badge whose text is the formatted status
  (`Fully Received`, `In Transit`); a row with no shipment shows a `Not shipped` badge.

## E. Incoming PL dialog (S5)

- **AC-E1** `[FE]` Columns are Container · Supplier · Qty · ETA · Status; no Packing list column.
- **AC-E2** `[FE]` The Container cell is the button that opens the packing list when
  `onOpenShipment` is given.
- **AC-E3** `[FE]` Status is a Badge as AC-D3.

## F. PO dialog (S6)

- **AC-F1** `[FE]` Status badge reads Outstanding when `still_to_come > 0` and the order is
  on order, Completed otherwise, Cancelled / Draft per `purchaseOrderStatusPill`.
- **AC-F2** `[FE]` Headers read Outstanding (not "Still to come") and Delivery date (not
  "ETA"); total row label "Total outstanding".

## G. First link on a manual match (S8)

- **AC-G1** `[BE]` Manual alias to a product on a supplier with zero `product_suppliers` rows,
  product already linked to DEFAULT at 90 days: a `(product, supplier)` link is written with
  `standard_lead_time_days = 90`, `is_primary_supplier = false`.
- **AC-G2** `[BE]` Same with no product links either: lead time = system settings default
  (90 when the setting is unset).
- **AC-G3** `[BE]` Supplier with links: mode of its own links still wins (existing behaviour).
- **AC-G4** `[BE]` Existing link untouched; alias delete never removes the link (AC-D4 of 2 Sep).
- **AC-G5** `[BE]` `scripts/backfill_manual_alias_links.py --dry-run` writes nothing and lists
  every missing link; `--apply` writes them; a second `--apply` is a no-op.
- **AC-G6** `[E2E]` After a manual match on the plan's Supplier codes tab, the product's
  Suppliers tab lists the supplier with "Their code" = the matched code.

## H. Evidence

- **AC-H1** `[E2E]` One recorded agent-browser run: from `/` via the sidebar to the plan,
  open Need, Project, Retail, On hand, SPO, Incoming PL, PO dialogs; screenshots of each.
- **AC-H2** Full `npm run test` and the scm pytest directory green before push.
