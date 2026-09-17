# Order inquiries: one header per SO, hide cancelled, Was/Now after a redirect, cascade skips used rows, raised-by per row - acceptance criteria

Status: draft (owner rulings 17 Sep 2026, in chat)
Plan: `PLAN-oi-worklist-one-header.md`

## Journey

Purchasing (Eling) opens Procurement > Supply Chain > Order Inquiries and searches an SO
number. They need to see, per item, what is still to buy, what is already on a PO or SPO,
what has been received, and what old row was used up. They do not need rows a later
revision cancelled. For a line whose earlier supply was received and released to stock
(`redirected_to_pool`, shown as `used`), the fresh buy row tells them in one place what it
replaces: the (i) Was/Now shows the old quantity, the old date and which document was
received. Every row of one sales order sits under one order inquiry number. The Raised by
column names the person who raised THAT row, never the person who last pressed Confirm on
the order.

CS (Jayson or Eling) confirms a planning change on the fulfilment board. The system raises
ORDER rows and DELAY / ADVANCE rows under the SO's single header. Nothing is asked of CS.

Purchasing is told by the existing handover email, unchanged.

Origin: SO314593 on prod, 17 Sep 2026. The B2154-NL line moved 182 to 220 and 01/06/2026 to
01/03/2027. Prod showed three ORDER rows (one cancelled by the re-confirm after the network
outage, one used, one live), two order inquiry numbers (OI-000477 and OI-000734), Raised by
Eling on a row Jayson migrated, and 24 pcs of SPO-2026/09-0036 auto-linked at 10:11:15 onto
the released 182 row instead of the live 220 row.

## Rulings (owner, 17 Sep 2026)

- R1 One header per SO: planning-change reactions (DELAY / ADVANCE / ORDER) land on the
  order's existing `amendment_id IS NULL` header. OCN amendments on project-authored SOs
  keep their own header (no evidence today; trigger noted in the plan).
- R2 The list hides `cancelled` rows unless the State filter asks for them.
- R3 The fresh ORDER row raised after a received row is released to stock carries Was/Now.
- R4 DELAY rows stay.
- R5 Order inquiry column hidden by default; the number stays on the header, the email and
  the URL.
- R6 Two defects: the auto-link cascade must skip `redirected_to_pool` rows; Raised by reads
  the row's own person before the header's.

## Phase 1 - frontend (mock)

- AC-OH-01 [FE] Given the worklist list view, when it first loads with no saved column
  preference, then the Order inquiry column is hidden and appears in the Columns menu, and
  ticking it shows the column.
- AC-OH-02 [FE] Given a row with `previous_qty` set and `redirected_to_pool` false, when
  the Qty cell renders, then the (i) shows "Was <previous_qty> on <previous date>" and the
  note text (the existing Was/Now affordance, no new component).

## Phase 2 - backend

### Cascade skips used rows

- AC-OH-10 [BE] Given a row with `redirected_to_pool = true`, state `partly_linked`, an
  unlinked remainder, and an open SPO allocation for its product, when
  `auto_place_for_products` runs for that product (any trigger, `include_awaiting` either
  way), then no link is written on that row and its state is unchanged.
- AC-OH-11 [BE] Given the same product with a fresh `raised` row on the same line, when the
  cascade runs, then the open SPO is linked to the fresh row, not the used one.
- AC-OH-12 [BE] Given `link_now` (Link now / Auto link all) on that product, then the used row
  is skipped the same way (same query, one seam).

### Raised by per row

- AC-OH-20 [BE] Given a row with `supply_decision_id` set, when the worklist lists it, then
  `raised_by_name` is the decision's `confirmed_by` (unchanged).
- AC-OH-21 [BE] Given a migrated row (`supply_decision_id` NULL, `acknowledged_by` = the
  migrator) whose header `raised_by` was later re-stamped by another user's Confirm, when
  the worklist lists it, then `raised_by_name` is the migrator.
- AC-OH-22 [BE] Given a row with neither a decision nor `acknowledged_by`, then
  `raised_by_name` falls back to the header `raised_by` (unchanged).
- AC-OH-23 [BE] Given the `raised_by` list filter with the migrator's id, then the migrated
  row is in the result; with the re-confirmer's id, it is not.

### One header per SO

- AC-OH-30 [BE] Given an order with an existing `amendment_id IS NULL` header, when a
  planning-change batch applies with a DELAY reaction, then the DELAY row's
  `order_inquiry_id` is that header, and no new `order_inquiries` row exists for the order.
- AC-OH-31 [BE] Given an order with NO header yet, when a batch applies with only a DELAY
  reaction, then exactly one header is minted (`amendment_id IS NULL`) and the row sits on it.
- AC-OH-32 [BE] Given a batch apply that confirms (raising ORDER rows) and reacts (DELAY),
  then both rows share one `order_inquiry_id`.
- AC-OH-33 [BE] No `so_amendments` row with `from_version_kind = 'planning_change_batch'`
  is written by the apply any more.
- AC-OH-34 [BE] Given existing headers whose amendment is `planning_change_batch` (prod:
  OI-000734 and siblings), when the migration runs, then their rows are moved to the same
  order's `amendment_id IS NULL` header (minted when absent, `raised_by` copied from the
  moved header), the emptied header and its synthetic amendment are deleted, and row ids,
  links, claims and handover records are untouched. Downgrade is a no-op with a comment.
- AC-OH-35 [BE] The handover email for a batch apply still fires once, naming the single
  header.

### Was/Now on the fresh row after a redirect

- AC-OH-40 [BE] Given a line whose only row is linked to a fully received document, when a
  confirm replans the line (new qty and date), then the released row is `redirected_to_pool`
  (unchanged) and the fresh ORDER row carries `previous_qty` = the released row's qty,
  `previous_delivery_date` = the released row's delivery date, and a note
  `Replaces <qty> used; <document> received <date or "in full"> into <location>`.
- AC-OH-41 [BE] Given a later reconfirm of that line with no new redirect, then the next
  fresh row does NOT carry the released row's Was/Now again (stamped only in the decision
  that released it).
- AC-OH-42 [BE] Given two released rows on the line in one decision, then `previous_qty` is
  their sum and the note names each document.
- AC-OH-43 [BE] The handover record for the fresh row (`_record_handover`, kind `raised`) is
  written as today; no new record kind.

### Hide cancelled by default

- AC-OH-50 [BE] Given the worklist list with no `state` param, then `cancelled` rows are
  absent and `total_rows` excludes them.
- AC-OH-51 [BE] Given `state=cancelled`, then only cancelled rows are returned.
- AC-OH-52 [BE] Facets `by_state` still count cancelled rows, so the State filter offers
  the value.
- AC-OH-53 [BE] The three cards (Buy / Purchased / Incoming) are unchanged (they already
  exclude `_NOT_OWED_STATES`).
- AC-OH-54 [BE] The schedule matrix and month strip are unchanged (they never counted
  cancelled).

## Phase 3 - end to end

- AC-OH-60 [E2E] On the lane stack against a copy of SO314593's shape (one sheet row linked
  158 to a received SPO, one open SPO for the product, mirror stale on qty and date): apply
  the planning change, press Confirm. The worklist for that SO shows, for B2154-NL: one
  ORDER 220 with (i) Was 182, one DELAY 220, one 182 `used` greyed. No cancelled row. One
  order inquiry number. Raised by on the migrated row is the migrator. The open SPO is
  linked to the 220 row, not the used one.
- AC-OH-61 [E2E] Filters > State = Cancelled shows the cancelled rows for that SO.
- AC-OH-62 [E2E] Columns menu shows Order inquiry unticked; ticking it shows the column.
- AC-OH-63 [E2E] 375px and 1280px: the list is usable and nothing clips.

## Not in scope (backlog)

- OCN amendment headers on project-authored SOs stay per amendment. Trigger to fold them
  too: a project-authored SO shows two headers on the worklist.
- Removing the order inquiry number altogether. Trigger: nobody quotes it in an email or
  sheet for a month after R5 ships.
- Netting far-dated buys against on-hand stock (ladder v8 rule "stock kept for nearer
  orders"). Owner accepted the rule on 16 Sep.
