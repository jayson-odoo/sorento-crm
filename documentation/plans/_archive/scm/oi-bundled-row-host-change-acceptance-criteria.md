# Acceptance criteria: a bundled row's (i) lists each host's own change

Companion to `PLAN-oi-bundled-row-host-change.md`. Backend criteria are verified by a
pytest on Postgres (`tests/_pg_fixture.py`, via the `api` fixture in
`tests/test_order_inquiry_worklist.py`); frontend criteria by Vitest
(`orderInquiryAck.test.ts`, `orderInquiryWorklistColumns.test.tsx`).

The rule for the owner: **a bundled row's (i) shows each HOST's own change, read from
the host rows at display time - nothing is written to the companion row.**

## Backend

* **AC-1** A bundled row with two hosts, one carrying a Was (`previous_qty` 182,
  `previous_delivery_date` 2026-06-01, `qty` 280 delivering 2027-03-01) and one with no
  Was of its own: `GET /project-sales/order-inquiries` reports `bundled_host_changes`
  as two entries, in RULE order, each with the exact `item_code`/`qty`/
  `delivery_date`/`previous_qty`/`previous_delivery_date` its own host row carries.
* **AC-2** A row nobody's rule ever bundled (`bundled_with_row_id` null) reports
  `bundled_host_changes` as `null` - never an empty list, never a missing key.
* **AC-3** A rule's second host has never had a row raised for it at all: its own entry
  still comes back, at its own position in the list, with every row field `null`.
* **AC-4** A host's own CANCELLED row and a REDIRECTED (`redirected_to_pool = true`)
  row are both excluded - neither counts as that host's live row, so an entry backed
  only by rows in either state reads exactly as AC-3 (every field `null`), never as if
  a superseded or pooled row were the host's current state.
* **AC-5** `response_model` (`OrderInquiryWorklistRow`) declares
  `bundled_host_changes` - asserted directly against the route's own JSON, not the
  service function, since an undeclared field is silently dropped on the wire.
* **AC-12** (review round 1 BLOCKER) A host carries its own live ORDER row (280 @
  2027-03-01, Was 182 @ 2026-06-01) AND a DELAY exception row on the same item code (7
  @ 2028-01-01, no Was): the DELAY row never answers for the host's own change, and the
  answer is IDENTICAL under the default sort and under `sort=item_code&dir=desc`.

## Frontend

* **AC-6** `bundledHostChangeLines` returns `null` for a row with no
  `bundled_host_changes` at all (undefined, `null`, or `[]`).
* **AC-7** A host with a Was reads `"with {item}: Was {previous_qty} on {dd/mm/yyyy},
  now {qty} on {dd/mm/yyyy}"`, dates in the SAME `dd/mm/yyyy` format the delivery date
  and Qty cells already print.
* **AC-8** A host with a live row but no Was reads `"with {item}: {qty} on {date}, no
  change"`.
* **AC-9** A host with no live row at all reads `"with {item}: no open row"`.
* **AC-10** The Qty cell's (i) renders, as a TOOLTIP (not the existing rejected/changed
  dialog), for a bundled row that is itself neither rejected, changed, redirected nor
  moved - the three marks `QtyAnnotationButton` already reads take priority when a row
  carries one of them too.
* **AC-11** A row with neither its own mark nor `bundled_host_changes` renders no icon
  at all, exactly as today.
* **AC-13** (review round 1 SHOULD) A row that is ALSO rejected or changed keeps that
  dialog, never the bundled tooltip - the tooltip's own lines never render at all on
  such a row.

## Not covered here

* The `po_number` cell's "Included with" headline/lightbox (`PLAN-scm-supplied-with-
  companions.md`'s own UAC) - unchanged by this plan.
* The per-project order inquiry route (`OrderInquiryRowOut`) - out of scope (see plan).
