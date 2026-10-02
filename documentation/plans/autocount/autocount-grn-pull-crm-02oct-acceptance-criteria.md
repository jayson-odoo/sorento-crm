# UAC: GRN pull from AutoCount with PO/SPO line linkage (GRN-PULL-CRM)

Plan: `PLAN-autocount-grn-pull-crm-02oct.md`. Owner rulings 2 Oct: Q3 (a), Q4 (a), Q5 (a);
Q1 / Q2 as proposed rejected ("every GRN line must link"), design held for live evidence.
Criteria marked **(held)** are rewritten once that lands.

## Entity, permission, migration

- **AC-GP-01 [BE]** `ENTITY_PERMISSIONS["goods_receive_notes"] == "procurement.grn.autocount_pull"`,
  `JOB_TYPES` `autocount_grn_pull`, `APPLY_JOB_TYPES` `autocount_grn_apply`; the slug is in the
  permission registry.
- **AC-GP-02 [BE]** `POST /autocount/pulls {"entity": "goods_receive_notes"}` is 403 without the
  slug (no FoundryX call, no job); with it, 200, phase `building`, one build call
  `{"companyCode", "entity": "goods_receive_notes"}`; a `scope {fromDay, toDay}` travels flat
  and is stored.
- **AC-GP-03 [BE]** Migration `grn_pull_0001_perm` (<= 32 chars, on the single head) grants
  the slug to roles holding `procurement.grn.import` and to `admin`, never to an
  `integration_*` role; downgrade removes it.

## Preview

- **AC-GP-10 [BE]** A snapshot of the GRN sample (rows carry `source_ref` `db1:GRN:{DocKey}`)
  previews `received 1, created 1`, one `success` row valued `ZZGRN-0001`, and writes no
  `picking_headers` row.
- **AC-GP-11 [BE]** A snapshot whose lines carry NO `FromDocType` / `FromDocNo` /
  `FromDocDtlKey` / `OurPONo` keys at all previews exactly like one carrying them as null.
- **AC-GP-12 [BE]** A GRN already in the CRM from the Excel import (same number, no
  `doc_key`) previews as `adopted 1` and is unchanged after the preview.
- **AC-GP-13 [BE]** The preview counts carry `lines_linked`, `lines_unlinked`,
  `lines_ambiguous`; a record with a linkage warning names it in words on its row.

## Line linkage (ingest, push and pull alike)

- **AC-GP-20 [BE]** `FromDocDtlKey > 0` keeps the exact rule (existing AC-AG033).
- **AC-GP-21 [BE]** Key 0, `FromDocType "PO"`, `FromDocNo` = a PO holding ONE line of the
  product: `po_line_id` and `purchase_order_id` set, no warning. (Owner sample
  `PO-2026/07-0013`; dev `GR-2026/09-0070` / `PO-2026/09-0018`.)
- **AC-GP-22 [BE]** Same, the PO holds the product on two lines, one in the GRN's Location:
  that one links. Both in other warehouses (or both in the same one): **(held)**, the owner
  wants a link, never "ambiguous".
- **AC-GP-23 [BE]** Key 0, `FromDocNo` = an SPO whose product has one allocation with enough
  capacity: `spo_allocation_id` set, `spo_number_raw` = the SPO; after apply the
  allocation's received quantity includes the line (receipt hook ran).
- **AC-GP-24 [BE] (held)** Key 0, SPO with the product on several allocations (dev
  `GR-2026/09-0090`: SRT1000-CR 2640 over 7 SPO lines in 3 warehouses; `GR-2026/09-0075`):
  every line links to SPO line(s); the shape waits on the live evidence.
- **AC-GP-25 [BE]** Key 0, SPO with ONE allocation of the product, qty above its remaining
  capacity: linked to it (the only candidate), warning `spo_over_receipt`.
- **AC-GP-26 [BE]** Two GRNs against the same SPO allocation (partial receipts): the second
  sees the first's draw; when the first used it up and the SPO has a second allocation of
  the product, the second GRN links to that one.
- **AC-GP-27 [BE]** `FromDocNo` set and `OurPONo` set to a different document: `FromDocNo`
  wins (Q3 a).
- **AC-GP-28 [BE]** No `FromDocNo`, no `OurPONo`: unlinked, no linkage warning.
- **AC-GP-29 [BE]** `FromDocType` other than `PO` (e.g. `GR`): unlinked,
  `from_doc_type_unsupported`.
- **AC-GP-30 [BE]** `FromDocNo` in neither table: `purchase_order_unresolved`; when the PO
  arrives later, the next GRN batch fills the line link.
- **AC-GP-31 [BE]** A PO / SPO with the same number in company B never links.
- **AC-GP-32 [BE]** A cancelled GRN's lines no longer consume SPO capacity: a later GRN for
  the same SPO and product links to the allocation the cancelled one had used (Q4 a).
- **AC-GP-33 [BE]** Unknown ItemCode: `retryable`. Unknown Location: lands with no
  warehouse (unchanged).

## Apply

- **AC-GP-40 [BE]** Confirm creates the `autocount_grn_apply` job; apply writes through the
  ingest (`doc_key`, `source_book`, `source_record` without `source_ref`); a second apply of
  the same snapshot is all `unchanged`.

## Rows, download, compare

- **AC-GP-50 [BE]** `GET /rows` answers one row per GRN line with `doc_no, doc_date,
  creditor_code, creditor_name, item_code, description, location, qty, uom, from_doc_no`.
- **AC-GP-51 [BE]** `GET /download.xlsx` header row matches AC-GP-50 in words.
- **AC-GP-52 [BE]** `POST /compare source=lines` keys by (Doc No, Item Code, Location), sums
  Qty, compares the stated source ("Our PO No.") with `FromDocNo` normalised; `source=headers`
  keys by Doc No (Q5 a; column aliases fixed once crew sends the two real files' headers).

## Frontend

- **AC-GP-60 [FE]** Goods Receive Notes list shows "Pull from AutoCount" only with the slug;
  it opens the DocDate dialog; the job page renders the review card labelled "AutoCount GRN
  Pull" with Back to Goods Receive Notes.

## Real-data gate

- **AC-GP-90** On a real DocDate window, compare against the users' GRN Excel shows 0
  unexplained differences, and every unlinked line carries a stated reason.
