# PLAN: order inquiry PO/SPO reserving, feedback batch 8 September 2026

Status: DRAFT, slices E/F/G gated on the AutoCount shared service reply.

Owner feedback batch of 8 Sep 2026 against the Order Inquiries worklist
(`/project-sales/order-inquiries`) and its PO/SPO reservation. Eleven items,
grouped into seven slices. Three of them cannot be built until the AutoCount
extract widens, and those are named as gated rather than guessed at.

## 0. What was measured before writing this

Read against the 7 Sep prod copy (`sorento_ai_automation_0907`, alembic head
`492_mcp_tool_chatbot_domain`).

**The BRW-IB reservation the owner could not find is real.** PO `202405-S0045`,
item `SRTWCX8605-S-RL-PJ`, open lines by location:

| location | ordered | received | outstanding |
| --- | --- | --- | --- |
| BRW-IB | 52 | 0 | 52 |
| BRW | 8 | 28 | -20 |
| BRW-BB | 0 | 59 | -59 |
| BRW-IR | 0 | 205 | -205 |
| (none) | 0 | 282 | -282 |

Two genuine open BRW-IB lines carry it: 50 expected 2026-08-19 and 2 expected
2026-07-29. The `BRW-IB 2` on SO419595 is that second line. The document is 89
lines long and the detail page shows ten at a time, so the evidence was two
pages away.

It is also the WRONG line to take, and that is slice H. The SO419595 rows
stand at BRW-IB and the line is at BRW-IB, which today scores
`TIER_SAME_LOCATION` and is dealt, because `_cascade_take`'s gate is
`own_location is None or tier <= TIER_POOL`. The owner ruled on 8 Sep that the
ceiling was never meant as a range: the automatic pass may take from the SITE
POOL and from nowhere else, because stock standing at a project location is
already spoken for by that project. Slice B still applies (the lightbox has to
be searchable), and slice H fixes the gate.

**The feed is dirty and that is what made the screen unreadable.** The rows
with `Qty 0 / TransferedQty > 0`, and the four with no location at all, come
from AutoCount PODTL (`source_ref = AED_SORENTO:36880005:<DtlKey>`). They make
the document total read 9,013 ordered against 10,041 received. Slice G.

**No SO linkage reaches us from the live feed.** `purchase_order_lines` holds
no sales-order key. `scm.order_link_claim` holds 36,397 SO to PO claims, every
one of them from `po_history` (the Excel upload) or `order_inquiry` (our own
placement), and none from `autocount`. The extract in the owner's message
selects no FromDoc column, which matches. Slice F.

**The cascade ranks by location and nothing else.** `link_location_tier`:
same location (1), same ownership group at another site (2), site pool (3,
own site first), sibling at the same site (4), elsewhere (5). The automatic
pass takes tier 3 and better (`cascadable`); the Link dialog offers the rest.
There is no notion of "this PO line belongs to this sales order". Slice E.

**Partial cover is deliberate today.** `_cascade_take`: "Partial coverage is
allowed and is not a failure", leaving the row `partly_linked` with the
balance still counting as demand. Slice D reverses that.

## Slice A. The row is one line (items 1, 2, 3)

`orderInquiryWorklistColumns.tsx`, the `po_number` column.

The cell renders a headline, a `SupplyBar`, then one block per linked
document with a location, a quantity and a `late N d` badge. A row with three
documents is five lines tall, and purchasing scrolls a hundred of them.

* Drop the `SupplyBar` from this column. It is a proportion of a number the
  same cell already prints in full, and the three tiles above the grid carry
  the vocabulary.
* Drop the `late N d` badge and the lateness words from the title. Nothing is
  ever acted on from it (AC-D17 says as much: "Said, never acted on").
* The cell becomes ONE line: the draft or confirmed mark, the coverage
  headline (`115 of 493`), then an info icon.
* The info icon opens a lightbox listing every document backing the row: kind,
  document number, location, quantity, expected date, and the standing (draft
  or confirmed). Document numbers there keep the existing lightbox trigger.
* Where the row has exactly one document, print it inline after the headline
  and still offer the icon.

Nothing is removed from the API. This is a rendering change.

## Slice B. The document lightbox is a DataGrid (item 4)

`OrderInquiryDocumentDialog.tsx` currently hand rolls two `<table>` elements.
A PO with 89 lines is unreadable and unsearchable in it.

* Replace both `LinesTable` bodies with the shared DataGrid, per the CRUD
  standard (`tableLayout: { width: 'fixed', columnsResizable: true }`,
  `columnResizeMode: 'onChange'`, explicit `size` per column). `PanelDataGrid`
  in `project-sales/_shared/components` is the existing in-dialog grid; reuse
  it rather than adding a third table shape.
* Client-side search over SKU AND location, one input, same placeholder idiom
  as the PO detail page.
* Paginate. Default 10 rows, same control as the PO detail Lines tab.
* "Open document" gets `target="_blank" rel="noopener noreferrer"`. It leaves
  a read-only lightbox for a full page, and losing the list behind it is the
  complaint.
* The Allocated-to panel stays as it is. It is short by construction.

## Slice C. An SPO reservation names its purchase order (item 8)

GATED on slice F. Buyers read the PO, not the SPO, so an `SPO-2026/09-0036`
reservation has to print the PO it came from. AutoCount holds it on the SPO
detail as From doc type / From doc no. We do not capture it.

Once captured: `get_spo_detail` carries `source_po_number` per line, the
lightbox prints it as a column, and the worklist's reservation lightbox
(slice A) prints it under the SPO entry.

## Slice D. Cover is all or nothing (item 11)

Ruled by the owner, 8 Sep: when PO and SPO together cannot cover the row in
full, link NOTHING and let the whole quantity go to Buy. Half covering a
493-piece line and buying 378 helps nobody, and it strands 115 units of
supply that could have covered a row in full.

* `_cascade_take` gains the rule: sum the cascadable candidates' `remaining`;
  if that total is less than `need`, return no takes.
* It applies to the AUTOMATIC pass only. The Link dialog is override and
  audit, and a buyer naming a line by hand keeps being allowed to take a
  partial (same carve-out `manual` already has for a non-active PO and for a
  group in deficit).
* `po_candidates_for_row` computes `default_take` through the same walk, so
  the dialog's preview will show zeros for a row nothing can cover in full.
  That is correct and is the point: the preview must not promise what the
  cascade will not do.
* NOT retro-applied. Rows already `partly_linked` keep their links until
  somebody re-deals them. No prod script in this plan.
* `partly_linked` stays a real state: a re-deal, a book re-upload or a manual
  partial can still produce one.

## Slice E. A PO line tied to this sales order wins (item 6)

GATED on slice F.

The flow the owner described: an order inquiry arrives, purchasing reserves
against a pool PO line at BRW, and then a user opens AutoCount and creates a
line under the project location (BRW-BB) tied to the sales order. Our link
must move from the BRW line to the BRW-BB line, and a later cascade must
prefer the SO-tied line over any pool line.

* A new tier ahead of `TIER_SAME_LOCATION`: the candidate PO line carries a
  resolved link to THIS row's sales order. Call it `TIER_SAME_SO = 0`.
* It is a RANK, never a filter, exactly as every other tier is: a row whose
  SO-tied line is short still reaches the pool.
* `relink_to_matching_lines` already re-points placements onto the line of the
  same document whose warehouse matches the demand after a re-upload. It gains
  the SO-tied line as the first thing it looks for.
* Evidence for the tier is `scm.order_link_claim` resolved to a `po_line_id`,
  which is the mechanism that exists. Nothing new is invented.

## Slice F. The AutoCount extract carries the linkage (item 5)

GATED on the shared service. Asked of `@autocount-ss` on 8 Sep:

1. Which PODTL column carries the sales order a PO line was raised for, and
   can the extract carry the SO DocNo AND the SODTL DtlKey per line? If PODTL
   holds nothing, which view or link table do we join instead?
2. Which SPO detail columns are the From doc type / From doc no, and can the
   SPO extract carry the source PO DocNo and PODTL DtlKey per line?
3. What do the `Qty 0 / TransferedQty > 0` and no-location PODTL rows mean.

On the answer:

* `purchase_order_lines` gains no FK. The pairing is written as an
  `OrderLinkClaim` with `source = 'autocount'`, item code stated, resolved by
  `order_link_service` the way the `po_history` feed's claims already are.
  A claim survives either document arriving first, which a nullable FK cannot.
* SPO source PO is a column on the SPO allocation, because it is a property
  of the line rather than a pairing to resolve.

## Slice G. The PODTL rows that cannot be true (item 7 follow up)

NO LONGER GATED. Answered by the shared service on 8 Sep against live
`AED_SORENTO`: `Qty` and `SmallestQty` are GENUINELY 0 on those rows, with
`TransferedQty` 28 / 52 / 62 / 76. `DtlType 'N'`, `MainItem 'T'`, no package
or sub-item, UOM UNIT at rate 1, `FOCQty` NULL, header not cancelled. Three of
the four were transferred from a sales order. The reading is an order quantity
zeroed AFTER the goods were received; the mechanism is not visible from PODTL
alone because it carries no line-level `LastModified`, and a follow-up probe
is queued with the owner.

The extract is NOT losing anything, so this is entirely ours to fix:

* Outstanding is `GREATEST(qty_ordered - qty_received, 0)`. It is negative on
  70 lines today.
* A line with `qty_ordered = 0` and `qty_received > 0` is CLOSED, not
  outstanding. 68 lines carry that shape. The PO detail page currently labels
  them `Outstanding`, which is the lie the owner caught.
* Neither shape may reach the cascade as supply. `remaining <= 0` already
  drops them, so this is a display and status fix, not a cascade one. Assert
  it anyway so it cannot regress.
* The document footer must not present a received total above an ordered
  total without saying why. On `202405-S0045` it reads 9,013 against 10,041.

No FOC fields on the wire: `FOCQty` is NULL on every one of those rows.

## Slice I. The warehouse master is missing codes: NOT BUILT

Found on 8 Sep and RETIRED the same day by the owner: "BRW-TERA is a stale
warehouse, it is noise, do not worry about it, it can just stay blank."

Kept here as the record, because the finding was real and somebody will hit it
again:

* AutoCount holds a `Location` on all four rows and on all 247,569 PO and SPO
  lines fleet wide. `PODTL.Location` is foreign-keyed to the Location master,
  so a code on a line always exists upstream.
* `BRW-TERA` is absent from our `warehouses` table (104 rows, no `TERA` in any
  spelling), so the ingest resolved it to nothing and wrote NULL.
* 432 of 65,126 purchase order lines from the live `autocount` feed carry no
  warehouse. (The 7,947 from `scm_po_history` are the banded Excel report,
  which names no location at all. Expected, and documented by that importer.)
* Our warehouse master has not been written since 2026-08-17, while the PO
  line feed beside it is current at 2026-09-06.
* `MWH-RSV` appears twice in our table. AutoCount has a unique constraint on
  the code, so that duplicate is ours.

WHY IT IS SAFE TO LEAVE. Slice H makes the automatic pass take from POOL
locations only. A retired project location is never cascadable under that rule
whether we hold its code or not, so an unresolved `BRW-TERA` costs us nothing
that slice H was not already going to refuse.

THE ONE THING THAT WOULD CHANGE THAT: a missing POOL code. A pool line at a
code we do not hold IS supply that exists and can never be reserved. Our five
pools (`BRW`, `DC1`, `MWH`, `RSW`, `WH3`) are all present today, so there is no
live exposure. If the location diff ever arrives, check it for pool codes and
nothing else.

## Order of work

A and B are independent of everything and ship first. D and H ship with them,
in that order, because both touch `project_order_inquiry_service.py`. That is
one PR, ruled by the owner on 8 Sep.

G is unblocked and is ours alone; it can join that PR or follow it.
C and E wait on F. F is confirmed buildable: `PODTL.FromSODtlKey` carries the
sales order on 20,802 of 37,692 PO lines since 2025, and SPO lines resolve to
their purchase order through `FromDocDtlKey` on 37,503 of 40,645. `UDF_SOList`
is never used, so this is a code slice and not a process rule.
I is retired by the owner and not built.

## Files

* `sorento_crm_frontend/app/(protected)/project-sales/order-inquiries/components/orderInquiryWorklistColumns.tsx` (A)
* `sorento_crm_frontend/app/(protected)/project-sales/order-inquiries/components/OrderInquiryDocumentDialog.tsx` (A, B, C)
* `sorento_crm_frontend/app/(protected)/project-sales/_shared/components/PanelDataGrid.tsx` (B, reuse)
* `sorento_crm_backend/app/services/project_order_inquiry_service.py` (D, E, H)
* `sorento_crm_backend/app/services/order_inquiry_worklist_service.py` (C, `get_spo_detail`)
* `sorento_crm_backend/app/services/scm/order_link_service.py` (F)
* `sorento_crm_frontend/app/(protected)/scm/purchase-orders/[id]/components/PurchaseOrderDetail.tsx` (G)
