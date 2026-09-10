# Phase 3 browser evidence - PO/SPO site pool + order sheet downloads

Lane stack: FE `http://localhost:3082`, BE `:8082`, RQ worker draining `imports`. Plan used:
`4f72aefe-d927-4597-851e-baddb603fad6` (started fresh via Reorder Planning > Start Plan,
defaults - every existing plan on the lane DB predated the site-pool fix). Product under test:
`SRTWC8518-SH`.

## Ground truth (measured against `sorento_ai_automation_pospo` before driving the browser)

```sql
select w.warehouse_code, w.is_active, w.segment, oo.on_order
from scm.on_order_v oo join warehouses w on w.id = oo.warehouse_id
where oo.product_id = (select id from products where product_code='SRTWC8518-SH');
```

| warehouse | active | segment | on_order |
| --- | --- | --- | --- |
| BRW | t | dealer | 394 |
| BRW-BB | t | project | 2 |
| BRW-RSV | f | project | 100 |
| BRW-SMC | t | project | 120 |

Site pool (active AND segment<>project) = **BRW only = 394**.

```sql
select w.warehouse_code, w.is_active, w.segment, po.ordered
from scm.po_ordered_v po join warehouses w on w.id = po.warehouse_id
where po.product_id = (select id from products where product_code='SRTWC8518-SH');
```

| warehouse | active | segment | ordered |
| --- | --- | --- | --- |
| BRW-RSV | f | project | 300 |

The ONLY open PO line for this product sits at BRW-RSV, which is **both inactive and
project-segment** - it fails the site-pool rule on two counts, so the correct PO cell is
**0**, not the "~300" a raw read of the line would suggest. This is a stronger negative
case than the brief anticipated: the fix must exclude a warehouse that is inactive even
when nothing else about it looks like a project bin.

## AC-22 - the SPO/PO cell, product-wide, site-pool only

| File | Observed |
| --- | --- |
| `AC-22-spo-modal-open-rows-sum-394.png` | SPO cell modal, Open (5) tab: SPO-2026/08-0064 (38) + SPO-2026/08-0066 (58) + SPO-2026/08-0066 (140) + SPO-2026/09-0024 (73) + SPO-2026/09-0028 (85) = **394**. No BRW-BB/BRW-RSV/BRW-SMC rows. |
| `AC-22-spo-modal-history-tab-36-rows.png` | SPO modal History (36) tab, non-empty. |
| `AC-22-po-modal-open-nothing-on-order.png` | PO cell modal, Open (0): "Nothing on order.", Total **0** - matches the grid's PO cell (correctly excludes the inactive+project BRW-RSV line). |
| `AC-22-po-modal-history-8-rows.png` | PO modal History (8) tab, non-empty (closed BRW lines). |
| `AC-22-ledger-net-now-spo-394.png` | The row's "Suggested qty" ledger, NET NOW block (extracted via `innerText`, visible in the screenshot's page-1 scroll): `On hand by site pool 0, + SPO (arriving) 394, - Retail demand 476, Net -82, Reorder level 50, Gap to line 132` - second, independent UI surface confirming SPO = 394. |

Grid row itself (`network requests` + snapshot text): `#155 SRTWC8518-SH ... 0 476 0 394 0 Suggested Buy 132` - on hand 0, retail 476, **SPO 394**, **PO 0**, matching both DB queries exactly.

Cover "From PO (open N)": this row's decision is a plain **Buy** (net -82 below level 50), which has no "Covered by stock" panel - that panel only renders for `rec_type='covered'` rows (`AC-12` is FE-only and already shipped in Phase 1; not itself in this lane's Phase 2 test list). Confirmed instead via the "Covered by stock" filter (see negative test below): those rows' PO figures also read correctly off the same po-book key.

## AC-23 - order sheet through My Downloads

| File | Observed |
| --- | --- |
| `AC-23-toast-preparing-order-sheet.png` | Actions > Order sheet Excel: toast **"Preparing the order sheet - it will appear in My Downloads."**, header download badge goes 0 -> 1. |
| `AC-23-drawer-xlsx-ready.png` | Drawer: `order-sheet-10092026.xlsx`, status **Ready** (the lane's RQ worker processed it in well under a second - too fast to catch a "preparing" row screenshot for the xlsx; the header badge text `"1 download preparing"` was observed for the PDF request instead, see below). |
| `AC-23-drawer-pdf-ready-both-jobs.png` | Second export (Actions > Order sheet PDF) - drawer with both rows, PDF also already **Ready** by the time the drawer opened. |
| `AC-23-pdf-rendered-62-pages.png` | The downloaded PDF (492,207 bytes, valid `PDF document, version 1.7`) rendered in-browser, page 1 of 62, 950 products - confirms non-empty, well-formed bytes. |

xlsx downloaded via the drawer's Download button (`~/Downloads/order-sheet-10092026.xlsx`,
74,936 bytes) and opened with `openpyxl` from the backend venv:

```
Item code: SRTWC8518-SH
BRW PO qty: 0
BRW incoming qty: 394
  SPO-2026/08-0064 - 38
  SPO-2026/08-0066 - 198   (the modal's two SPO-2026/08-0066 lines, 58 + 140, rolled up per document)
  SPO-2026/09-0024 - 73
  SPO-2026/09-0028 - 85
```

`BRW incoming qty` = **394** = the grid's SPO cell. `BRW PO qty` = **0** = the grid's PO cell.
Both match exactly.

PDF downloaded via its presigned R2 URL (`curl`, HTTP 200, 492,207 bytes) - ready + non-empty,
confirmed by `file(1)` and the rendered screenshot above (both consistent with the xlsx: e.g.
`ACC-SRT1024` on page 1 reads BRW PO qty 0 / BRW incoming qty 0, matching the DB query for that
product's `covered` recommendation with SPO=0, PO=0).

## Negative test - a covered row with 0 SPO

The grid's free-text search ("Search product, location, or supplier") did not return
`ACC-SRT1024` / `32MM TAIL PIECE COUPLING` (both confirmed via SQL to be `rec_type='covered'`
on this run) even after a full page reload - the default Lines search appears scoped to
actionable rows. Reaching a covered row required the **Filters** panel (`Rec type` `Equals`
`Covered by stock`), which narrowed the whole 950-line plan to 2 rows. Noted as a real UX gap,
not a regression this lane introduced - filed for the reviewer's attention, not fixed here.

| File | Observed |
| --- | --- |
| `negative-spo-modal-nothing-on-the-water.png` | `SRT95SS-GM`, decision "Stock 49" (pure covered, 0 buy): SPO modal Open to BRW (0): **"Nothing on the water to BRW."**, Total 0. |
| `negative-spo-cell-shows-zero.png` | Same row's grid SPO cell reads **`0`**, not a dash. |

## Console / network

`errors` and `console` showed no uncaught page errors across the whole run (one pre-existing
React key warning in `Demo1Layout`, unrelated to this lane). `network requests --filter
purchase-trend` confirmed the FE fires `GET .../purchase-trend?scope=site_pool` (AC-11's fix,
live) alongside the bare `GET .../purchase-trend` (the unrelated Last-price read, unchanged),
corroborating the amended AC-10/AC-11 contract end to end.
