# PLAN - Loading plan lightbox feedback, 3 Sep 2026

**Status:** APPROVED by the captain 3 Sep 2026 (Lavish markup: both peak cells; "ok good to go"). Implementation on `feat/scm-loading-plan-lightbox-3sep`. UAC: `scm-loading-plan-lightbox-feedback-3sep-acceptance-criteria.md`. Phase 3 review done 3 Sep (Opus), fix round applied; PR pending.
Lane: `feat/scm-loading-plan-lightbox-3sep` off `origin/main` (53723ed02), stack slot FE :3130 / BE :8130.

**Amends:** `PLAN-scm-loading-plan-feedback-2sep.md` (R7 lightboxes, AC-B2/B4/B6) and the
shared `scm/components/PlanRowDialog.tsx` those ACs shipped.

## 1. What the captain saw (prod, plan 8c2c2cec, JINBAICHUAN)

| Screenshot | Symptom | Cause (source on origin/main) |
| --- | --- | --- |
| History tab | "Project peak 2,861 Mar 26 · Retail peak 42 Jun 26" as a text line above the table | `ProjectRetailTabs` prints `peakOf()` for both channels, `PlanRowDialog.tsx:342-348`; no row is marked. |
| History tab | Project dialog shows a Retail column and vice versa | One table for both channels, `focus` only bolds a column (`:352-376`). |
| Need column | Not clickable | `open_so_need` cell is plain text, `ContainerRequestSection.tsx:519-538`; only Project / Retail open the channel dialog. |
| SPO dialog | Status is raw text `fully_received` | `<Td>{textCell(r.status)}</Td>`, `:546`. |
| SPO dialog | "Packing list" column reads Draft / Not shipped | `r.shipment_number ?? 'Draft'`, `:540`. The SPO SQL never selects `s.shipping_container_number` (`container_request_drill.py:297-318`); the Incoming PL SQL does (`:197`). |
| SPO dialog | Tabs say `Open to pools (1)` / `History (3)` = line counts | `open.length` / `history.length`, `:565-566`. Same on PO `:721-722` and the channel dialog `:280-281`. |
| SPO dialog | "46 arriving at site pools" beside the title | `dialogContext()` in `ContainerRequestSection.tsx:263-273`, rendered by the shell `:940`. |
| Incoming PL dialog | Status raw text; Packing list column redundant beside Container | `IncomingPlTable`, `:600-640`. |
| PO dialog | Status reads `active`, list reads Outstanding / Completed; headers "Still to come" / "ETA" | `textCell(r.status)` `:694`; PO list uses `purchaseOrderStatusPill` (`scm/lib/purchaseOrderStatus.ts:58`) and heads the date column "Delivery date" (`PurchaseOrdersList.tsx:257`). |

Answered, no code: "Not on your list" rows. `supplier_document_model._Asks` places each
requested line on the supplier's retained stock list by (1) their code = our code or (2) a
stock-snapshot binding; a line matching neither is appended in yellow with the remark
(`:702-717`). Past sales play no part. A product is in the ask because it is in the plan
universe (link, plan statement, alias, set driver, 2 Sep S6).

## 2. Slices

All in `sorento_crm_frontend/app/(protected)/scm/components/PlanRowDialog.tsx` unless named.

### S1. Channel history: highlight both peak months in the table

Captain's markup, 3 Sep: "the 12 month history needs to highlight both project and retail
peak month". So the table keeps both columns and marks each column's peak CELL.

- Drop the "Project peak ... Retail peak ..." line.
- History table stays Month · Project · Retail for every dialog. Total row stays.
- The Project column's highest cell and the Retail column's highest cell each carry
  `data-peak="project"` / `data-peak="retail"`, a `bg-primary/10` cell tint and
  `font-semibold`. First occurrence wins a tie. A column whose twelve months are all 0 has no
  marked cell. The two marks may land on the same row or on different rows.
- The Open tab is unchanged: Project dialog lists project SO lines only, Retail lists retail
  only (already so).
- `PeakCell` in the grid still opens the channel dialog on its history tab (AC-B6), unchanged.

### S2. Need lightbox, project and retail together

- `open_so_need` cell becomes a `PlanNumberButton` (same as Project / Retail) opening
  `PlanRowDialog kind='need'`; `PLAN_ROW_DIALOG_TITLES.need = 'Need'`.
- Body = `ProjectRetailTabs channel='need'`:
  - Open tab: every open SO line for the product (project and retail, unfiltered), one extra
    column **Channel** (Project / Retail) after Sales order. Total = Need.
  - History tab: Month · Project · Retail · **Total**; the Project and Retail peak cells are
    marked as in S1, and the Total column's peak cell too (`data-peak="total"`).
- Set rows: lines keyed by `product_id` as today (driver member's figures, R19).

### S3. Tab labels carry quantity, not line count; header context removed

- Channel dialogs: `Open before cut-off 31/10/2026 (1,075)` where 1,075 = sum of qty on the
  tab. No cut-off known = `Open (1,075)`.
- SPO: `Open to pools (46)` / `History (522)` = sum of `qty` per tab.
- PO: `Open (1,505)` = sum `still_to_come`; `History (N)` = sum `qty_ordered`.
- `context` prop and `dialogContext()` are deleted; the title is `<Kind> · <code>` only. The
  On hand and Incoming PL dialogs already end in a Total row.

### S4. SPO dialog: status pill, container column

- Backend `container_request_drill._spo_rows`: select + group by `s.shipping_container_number`,
  emit `container_number` on every SPO row (null when no shipment). Service type
  `ContainerRequestDrillSpoRow.container_number: string | null`.
- Column "Packing list" becomes **Container**: `container_number`, else `EM_DASH`.
- Status: `<Badge variant={getStatusBadgeVariant(status)} appearance="light" size="md">`
  with `formatStatusLabel(status)` (`lib/status-badge.ts`). A row with no shipment reads
  **Not shipped** (secondary).

### S5. Incoming PL dialog: status pill, drop the Packing list column

- Columns: Container · Supplier · Qty · ETA · Status. The Container cell keeps the
  `onOpenShipment` link the packing-list cell had.
- Status pill as S4.

### S6. PO dialog: the purchase-order list's words

- Status pill = `purchaseOrderStatusPill({ status, is_on_order: still_to_come > 0 })` in the
  same `Badge` the list uses, so Outstanding / Completed / Cancelled / Draft.
- Headers: "Still to come" becomes **Outstanding**, "ETA" becomes **Delivery date**; total row
  label "Total outstanding".

### S8. A manual match on a supplier with no links writes the first link

Captain, 3 Sep: CWC7601-RL-180 matched to CWC7601-S-200-RL on JINBAICHUAN's plan (Remembered
list shows it, Manual, 03/09 3:23 pm), yet the product's Suppliers tab lists only DEFAULT
and "Their code" is blank.

Cause (origin/main `supplier_code_alias_service._ensure_product_supplier_link`, `:178-228`):
lead time for the new link = mode of the SUPPLIER's existing `product_suppliers` rows, and
"a supplier with no existing link at all gets no row". JINBAICHUAN has ZERO
`product_suppliers` rows (its whole universe came from the stock list), so every manual
match on it returns before writing. "Their code" is read off the product's link rows
(`procurement_service.py:5660-5683`, LEFT JOIN alias on product + supplier), so no link = no
supplier row = no code. The alias itself is fine and still carries the product into the plan
universe.

Fix, backend only:
- Lead-time ladder in `_ensure_product_supplier_link`: (1) mode of the supplier's links, as
  now; (2) else mode of the PRODUCT's own links (what we already wait for this product;
  CWC7601-S-200-RL's DEFAULT link says 90); (3) else `default_product_standard_lead_time_days`
  from system settings (`product_service._default_standard_lead_time_days`, 90 when unset).
  The row is always written on a manual product match. `is_primary_supplier=False`.
- Repair script `scripts/backfill_manual_alias_links.py --dry-run|--apply`: for every
  manual alias with a `product_id` and no `(product_id, supplier_id)` link, call the helper.
  Prints supplier · code · product · lead time chosen. Run on prod after deploy, on the
  captain's go (JINBAICHUAN alone has 29 remembered codes).
- pytest: supplier with zero links + product with a DEFAULT link at 90 => link written at
  90; neither => settings default; existing link untouched; dry-run writes nothing.

### S7. Tests + browser evidence

- `PlanRowDialog.test.tsx`: both peak cells marked, no peak text line (S1); Need tabs
  with Channel column + Total column (S2); tab labels sum qty (S3); Container column and
  status pills (S4/S5); PO pill words + headers (S6).
- `ContainerRequestSection.test.tsx`: Need cell opens the Need dialog; no context beside
  the title.
- `tests/scm/test_container_request_drill.py`: SPO rows carry `container_number`, null on an
  unshipped allocation.
- S8 pytest above.
- agent-browser run on :3130 via sidebar to the plan, each of the seven lightboxes opened.

## 3. Not in scope

- Per-supplier filtering of the PO / SPO / PL drills (they are company-wide per product by
  design; the JINBAICHUAN / FENGTA case is a product-supplier link question, not a dialog bug).
- Linking SPO rows to a shipment page.
