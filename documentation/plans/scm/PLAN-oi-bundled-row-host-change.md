# PLAN: a bundled row's (i) lists each host's own change

Status: Track: small fix - ready for PR review. Worktree `sorento_crm-oi-sheet-date`,
branch `feat/oi-bundled-row-host-change`. Backend and frontend, one PR.

UAC: `oi-bundled-row-host-change-acceptance-criteria.md`.

## The case, as the owner showed it

SO314593's SRTWC8605-SC-RL row (280) reads "Included with 2 items - 282 of 280" on the
Order Inquiries worklist - a "supplied with" companion (`PLAN-scm-supplied-with-
companions.md`): it ships inside SRTWCX8605-S-RL-PJ and SRTWCY8605-PJ, so it carries no
sheet row of its own, no PO of its own, and no Was of its own. The owner: "it comes with
the X and Y, so it should follow them, to have the same delay."

## The rule, for the owner

**The (i) on a bundled row shows EACH HOST's own change, read from the host rows at
display time. Nothing is written to the companion row.** A companion's own delay is
whatever its hosts' own delay is, worked out fresh every time the screen is read - never
stamped onto the companion row itself, which would drift the moment a host changed again.

## What was measured in the code

* The serializer already resolves a bundled row's anchor and item codes
  (`_bundled_po_number`, `_bundle_map_for_rows`,
  `app/services/order_inquiry_worklist_service.py`) off
  `product_companion_service.bundled_with_item_codes_map` /
  `resolve_bundled_item_codes` - the rule's own host codes, in rule order, for a whole
  page in two queries rather than two per row.
* `_COLUMNS` (the worklist's own SELECT) did not carry `order_inquiry_id` - needed to
  group a bundled row's hosts to the SAME header, added here.
* The (i) idiom already exists twice on this screen (`Tooltip`/`TooltipTrigger`/
  `TooltipContent` around an `Info` icon for the Instruction column's note and the
  Raised at column's raise history) and once as a DIALOG (`QtyAnnotationButton` /
  `OrderInquiryQtyAnnotationDialog` for a row's OWN rejection/change/redirect). A
  bundled companion carries none of those three marks of its own, so its icon was
  never rendered at all before this change.

## The change

**Backend** (`app/services/order_inquiry_worklist_service.py`):

* `_COLUMNS` gains `OrderInquiryRow.order_inquiry_id.label("order_inquiry_id")`.
* `_host_changes_for_rows(rows, bundle_map)`: for every bundled row on the page (one
  with `bundled_with_row_id` set), resolves its rule's host item codes (the SAME
  `resolve_bundled_item_codes` call `_serialize` already makes for `bundled_with`) and
  reads each host's own LIVE row (`state != cancelled`, `redirected_to_pool = false`)
  on the SAME order inquiry header. Built from rows already on the page first; the
  rest costs ONE extra query for the whole page (never per row), keyed by
  `(order_inquiry_id, item_code)`. A host with no live row still gets an entry, with
  every row field `null` - the (i) always names every host the rule requires.
* `_serialize` gains `bundled_host_changes`: `null` on a non-bundled row, otherwise a
  list of `{item_code, qty, delivery_date, previous_qty, previous_delivery_date}`, one
  per host, in rule order.
* `OrderInquiryBundledHostChangeOut` (new schema) and `OrderInquiryWorklistRow.
  bundled_host_changes` (new field) in `app/schemas/project_order_inquiry.py` -
  `response_model` drops what it is not told about, asserted in
  `tests/test_order_inquiry_worklist.py`.
* Scoped to the WORKLIST route (`GET /project-sales/order-inquiries`) only, not the
  per-project route (`OrderInquiryRowOut`) - the journey is purchasing's cross-project
  list; the per-project route's own `bundled_qty`/`bundled_with` fields are untouched.

**Frontend**:

* `orderInquiryAck.ts` gains `bundledHostChangeLines(row)`: one line per host, in the
  order `bundled_host_changes` carries - `"with {item}: Was {pq} on {dd/mm/yyyy}, now
  {qty} on {dd/mm/yyyy}"` when the host carries a Was, `"with {item}: {qty} on {date},
  no change"` when it has a live row but no Was, `"with {item}: no open row"` for a
  null entry. `null` when the row carries no `bundled_host_changes` at all. Dates via
  `formatDateInMalaysia` (`dd/mm/yyyy`), the same formatter the delivery date and Qty
  cells already use.
* `QtyAnnotationButton` (`orderInquiryWorklistColumns.tsx`) gains a fourth branch: when
  a row is NEITHER rejected, changed, redirected NOR moved (its three existing marks),
  but carries `bundled_host_changes`, the (i) opens a TOOLTIP (not the dialog) printing
  `bundledHostChangeLines`, one line per host. A row that IS also rejected or changed
  keeps that dialog, exactly as today - the bundled tooltip is what a companion falls
  back to only when it has nothing of its own to say.
* `OrderInquiryBundledHostChange` (new type) and `OrderInquiryWorklistRow.
  bundled_host_changes` (new field) in `orderInquiry.types.ts`.

## Not in scope

* The per-project order inquiry route/schema (`OrderInquiryRowOut`).
* Any write to the companion row's own `previous_qty`/`previous_delivery_date` - the
  rule is explicitly read-only, computed at display time.
* The `po_number` cell's own "Included with" headline and lightbox - unchanged.

## Files touched

* `app/services/order_inquiry_worklist_service.py` - `_COLUMNS`, `_host_changes_for_
  rows` (new), `list_rows`, `_serialize`.
* `app/schemas/project_order_inquiry.py` - `OrderInquiryBundledHostChangeOut` (new),
  `OrderInquiryWorklistRow.bundled_host_changes`.
* `tests/test_order_inquiry_worklist.py` - four new tests (two hosts one with a Was,
  non-bundled row, host with no row at all, cancelled/redirected host rows excluded).
* `app/(protected)/project-sales/_shared/lib/orderInquiryAck.ts` -
  `bundledHostChangeLines` (new).
* `app/(protected)/project-sales/_shared/lib/orderInquiryAck.test.ts` - new tests for
  `bundledHostChangeLines`.
* `app/(protected)/project-sales/order-inquiries/components/orderInquiryWorklistColumns.tsx`
  - `QtyAnnotationButton`'s new tooltip branch.
* `app/(protected)/project-sales/order-inquiries/components/orderInquiryWorklistColumns.test.tsx`
  - new tests for the (i) tooltip.
* `app/(protected)/project-sales/_shared/types/orderInquiry.types.ts` -
  `OrderInquiryBundledHostChange` (new), `OrderInquiryWorklistRow.bundled_host_changes`.
* `documentation/user-guides/supply-chain/` - one sentence on the order inquiries guide.
