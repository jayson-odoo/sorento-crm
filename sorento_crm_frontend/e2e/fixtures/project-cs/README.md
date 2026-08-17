# Project CS golden set (real client documents)

These are Sorento's own documents for one real project, Tuju Residences, supplied by the
client on 2026-08-01. They are committed on purpose: an AI extraction feature that is only
tested against fixtures we invented tests our imagination, not the client's paper.

Nothing here is a mock. The scan is a real scan, the pencil on it is the client's pencil,
and the expected outputs are what their staff actually produced by hand from these inputs.

## Inputs

| File | What it is |
|---|---|
| `quotation-qt-004188.pdf` | The quotation the PO is priced against. Filing ref `PS26-0143`. |
| `customer-po-buimaco-r1.pdf` | The customer PO. **Scanned, no text layer**, 10 pages, 52 lines. Carries two handwritten amendments: a strike-through cancelling line 7, and a pencil note naming a successor PO. |
| `delivery-schedule-buimaco-r1.pdf` | Delivery schedule R1. A matrix: phase rows by product columns, in the customer's own item codes (`BUI-HB-*`). Its `TOTAL QTY` row is a free checksum on extraction. |
| `delivery-schedule-slg-r2.pdf` | Delivery schedule R2, issued by a **different company** than the PO. Dates move, quantities do not. |

## Expected outputs

| File | What the pipeline must reproduce |
|---|---|
| `expected-so397450-tower.pdf` | 99 TOWER lines, line for line: product, qty, delivery date, unit price. |
| `expected-so397460-common-area.pdf` | The COMMON AREA split of the same PO. |
| `expected-so376200-early-subset.pdf` | A third SO, an early product subset dated **before** the PO existed. This is why an area split is a proposal and never a rule. |
| `expected-order-inquiry-2025-12-18.xlsx` | The order inquiry to purchasing, as their staff wrote it. Fixed columns, verbs in `ORDER` / `RESERVE & ORDER` / `ADVANCE` / `DELAY` / `CHANGE SO NO` / `CANCEL BALANCE`. |
| `expected-order-inquiry-2026-03-04.xlsx` | The R2 revision's inquiry: 12 tower `DELAY` rows plus 3 common area rows, quantities unchanged. |

## Two facts that trip up a naive reading

The PO speaks in **SETS**; the quotation and the SO speak in **components** (a priced parent
plus zero-priced companions). The explosion is not cosmetic, it is what makes 52 PO lines
become 99 SO lines.

A quantity on this project sits under a **different debtor**: `SO383057` was raised under
HONG BEE as a pre-order for the same project and later re-pointed. The project is constant,
the customer is not, so no order row should be raised for quantity that pre-order covers.

Acceptance criteria live in `documentation/plans/UAC-project-lead-to-so.md`, group M.
