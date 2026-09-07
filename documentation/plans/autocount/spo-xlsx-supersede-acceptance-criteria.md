# UAC: SPO first-push supersede (xlsx-era rows vs the AutoCount line-set)

Status: APPROVED 2026-09-07 (captain, production incident). Plan: `PLAN-spo-xlsx-supersede.md`.

Tags: [BE] backend, [T] tester writes it red first, [S] dedupe script. All tests on Postgres via
`tests/_pg_fixture.py`; seed every row under a marker; never borrow existing data.

Fixture vocabulary used below: "xlsx row" = an `spo_allocations` row with `source_ref IS NULL`,
`source_doc_ref IS NULL`, `source_system = 'scm_upload'`; "push" = `POST /api/v1/external/ingest/
shipping_orders` with one record whose lines carry `source_ref` (DtlKey), `product_code`,
`warehouse_code`, `qty_ordered`, `qty_received`, `line_number`.

- **AC-X1 [BE][T]** (D25, D26) Given one xlsx row for SPO N, product P, location L, allocated 47,
  received 47, closed; when the first push of N arrives with two lines for P at L (line 1 qty 29,
  line 2 qty 18, both qty_received 0), then N holds exactly two rows, both `source_ref` set, line 1
  received 29 closed, line 2 received 18 closed, `receipt_status` fully_received on both, the xlsx
  row is gone, and the verdict says `outcome created`, `lines.created 2`, `lines.superseded 1`.

- **AC-X2 [BE][T]** (D27) Given AC-X1's xlsx row is referenced by one `picking_lines` row, one
  `scm.order_link_claim` row and one `projects.order_inquiry_links` row; after the push all three
  point at the row for line 1 (the first line of the group by `line_number`), none is NULL, none
  points at a deleted id.

- **AC-X3 [BE][T]** (D26) Given the xlsx row received 30 of 47 (open); after the same push line 1
  is received 29 closed, line 2 received 1 open, `receipt_status` fully_received / pending.

- **AC-X4 [BE][T]** (D25) Given SPO N already holds ONE ref row (any DtlKey) and one closed
  ref-less row for product P; when a push arrives with a new DtlKey for P, then the closed ref-less
  row is untouched (still closed, still ref-less, same id) and a fresh row is created for the new
  DtlKey. This revises `tests/test_ingest_review_fixes.py::test_a_closed_ref_less_spo_row_is_not_adopted_by_a_new_dtlkey`
  so its seed includes the ref row; the pure xlsx-era shape it used to seed is AC-X1 now.

- **AC-X5 [BE][T]** (D27) Given xlsx rows for products P and Q on SPO N and a first push naming
  only P; after the push the Q row still exists, is closed, keeps its links; the verdict counts
  `lines.superseded 1` (P only).

- **AC-X6 [BE][T]** (D26) Given an xlsx row with `inbound_shipment_id` set and a push whose
  `container_number` resolves to no shipment; after the push every line of that group carries
  the xlsx row's `inbound_shipment_id`.

- **AC-X7 [BE][T]** (D25) Given an OPEN xlsx row (received 0) and a first push for the same
  product + location; the xlsx row is superseded (deleted), the lines carry received 0 open.

- **AC-X8 [BE][T]** (D28) Given an allocation with `quantity_received 29` and no picking line,
  and a sibling allocation of the same SPO with one approved picking line of 5; when
  `sync_received_for_spo_number(N)` runs, the sibling reads 5 and the first still reads 29.

- **AC-X9 [BE][T]** (D25) A second push of the same DocKey after AC-X1 (same lines, qty_received
  still 0) answers `updated` and leaves both rows received 29 / 18 closed (received never
  shrinks); `lines.superseded` absent.

- **AC-X10 [S][T]** (D29) Given a company holding SPO N with the AC-X1 xlsx row AND two ref rows
  already appended (line 17 qty 29, line 18 qty 18, both received 0 open, `created_at` later than
  the xlsx row), `scripts/dedupe_spo_xlsx_superseded.py --company <code> --dry-run` prints the
  plan and writes nothing; `--apply` leaves two rows received 29 / 18 closed with the xlsx row's
  links moved to line 17 and the xlsx row deleted; a second `--apply` reports zero documents.

- **AC-X11 [BE][T]** Parity: the AC-X1 outcome (two rows, 29 / 18, closed) is identical whether
  reached by (xlsx upload -> GRN -> first push) or by (first push -> GRN) for the same fixture,
  compared on `allocated_quantity`, `quantity_received`, `line_status`, `inbound_shipment_id`.

- **AC-X12 [BE]** `GET /api/v1/external/contract` warning/verdict note lists `lines.superseded`.

## Security-review round (captain rulings 2026-09-07, PLAN D25a / D26a / D28a / D30)

- **AC-X13 [BE][T]** (D25a) Given a ref-less row for product P on SPO N written with
  `source_system` NULL (CRM UI / n8n packing-list shape) and a first push naming P; the row is
  NOT deleted: it is adopted or left per the pre-existing rules, and `lines.superseded` is absent.
  Only `source_system = 'scm_upload'` rows are ever superseded.

- **AC-X14 [BE][T]** (D25a, per-group) Given xlsx rows for products P and Q on SPO N; push 1
  names P only (Q kept, closed); push 2 names Q at qty 20 / received 0 while Q's xlsx row carried
  received 20; after push 2 the Q group holds exactly one row, ref set, received 20, closed, and
  the xlsx Q row is gone (`lines.superseded 1` on push 2). No open Q row exists.

- **AC-X15 [BE][T]** (D26a guard) Given the AC-X1 xlsx row (allocated 47, received 47) and a
  first push with one line for P at L, `qty_ordered 1`, `qty_received 0`; the xlsx row is NOT
  deleted (still present, closed), a new open row of 1 is created, the record warns
  `received_locked`, and no row on N has a lower receipt than before.

- **AC-X16 [BE][T]** (D26a shipments) Given two xlsx rows for P at L on SPO N linked to two
  different inbound shipments A and B; after a first push naming P at L with two lines, every
  new line carries shipment A, the record warns `shipment_merged`, and the INFO log names B.

- **AC-X17 [BE][T]** (D30) Given the calling principal holds `scm.shipping_orders.edit` but not
  `scm.shipping_orders.delete`; the AC-X1 push carries receipts and moves links exactly as AC-X1
  and AC-X2, but the xlsx row is CLOSED not deleted, its `allocation_notes` reads
  `superseded by <DocKey>`, and the record warns `superseded_closed_only`. With `.delete` held,
  AC-X1 behaviour (deleted). Both pushes log at INFO the affected row ids with allocated / received.

- **AC-X18 [BE][T]** (D28a) After the AC-X1 supersede (line 1 = 29, line 2 = 18, one picking line
  of 47 repointed to line 1), running `sync_received_for_spo_number(N)` and
  `sync_grn_received_to_spo(<that header>)` leaves line 1 at 29 and line 2 at 18 (group total 47
  distributed in Seq order), never 47 on line 1. A `scm_upload` or NULL-source sibling with its own
  picking line of 5 still recomputes to 5.

- **AC-X19 [BE][T]** (S4) Given the xlsx row's `order_link_claim` and `order_inquiry_links`
  dependants carry `company_id` NULL; after the supersede both point at line 1 (not NULL).

- **AC-X20 [S][T]** (D29 amended) Given SPO N holds an old DocKey's closed ref rows (retired) and
  a newer DocKey's ref rows plus one xlsx row; the dedupe repoints and carries onto the NEWER
  DocKey's first row only; the retired rows are untouched. `--since '2026-09-07 05:15'` (naive) is
  accepted; `--since '2026-09-07T05:15:00Z'` is rejected with a clear message before any write.

- **AC-X21 [S][T]** (S10) The dedupe test seeds a picking line, an order_link_claim and an
  order_inquiry_link on the xlsx row and asserts all three point at the first ref row after
  `--apply`, and that a company-B xlsx row on the same `spo_number` is untouched.

- **AC-X22 [BE][T]** (S9) `sync_received_for_spo_number(N)` called under company A's scope never
  writes a company-B allocation sharing `spo_number` N.

## Reviewer round (kill-test gaps, 2026-09-07)

- **AC-X23 [BE][T]** (D26 Seq order) The AC-X1 push with its two lines sent in REVERSE payload
  order (line_number 2 first, then 1) still yields line 1 = 29 and line 2 = 18; distribution
  follows `line_number`, not payload position.

- **AC-X24 [BE][T]** (D26 max rule, AutoCount side) Given the xlsx row received 10 of 47 and a
  first push whose line 1 states `qty_received 25` and line 2 `qty_received 0`; line 1 reads 25
  (AutoCount above the carry wins), line 2 reads 0, nothing reads below 10 in total.

- **AC-X25 [BE][T]** (D28 release list) After a GRN with one approved picking line of 5 against an
  allocation is deleted via `delete_grn`, and separately via `bulk_delete_grns`, that allocation's
  `quantity_received` drops to 0; a sibling allocation with no picking line keeps its stored value.

- **AC-X26 [BE][T]** (D27a) After the AC-X1 supersede, `inbound_shipment_lines.line_status` for the
  linked shipment is refreshed (same as every other writer of allocations does through
  `InboundShipmentService.refresh_shipment_line_statuses`); the dedupe refreshes each touched
  shipment once per document.

- **AC-X27 [S][T]** The dedupe's operator report prints ref-less GROUPS kept (not rows), and a dry
  run ends with a rollback so no transaction stays open across the sweep.

## Delta round (security re-review, 2026-09-07)

- **AC-X28 [BE][T]** (D28a floor) Given two `autocount` lines for P at L on SPO N with ESB-stated
  receipts (line 1 allocated 29 / received 25, line 2 allocated 18 / received 18) and no picking
  line; when a Sorento GRN approves one picking line of 5 against line 1 and
  `sync_grn_received_to_spo` runs, line 1 still reads 25 and line 2 still reads 18 (the group
  total is the max of the picking sum and the stored sum of non-released members). A released
  member (GRN deleted) still drops to what its remaining picking lines prove.

- **AC-X29 [BE][T]** (pass 3 gated) Given SPO N holds an xlsx row for P at L (open, 10) and a
  NULL-source (n8n / CRM) row for Q at M (open, 5, with a `storage_zone_id` and an
  `order_inquiry_links` placement); a push names (P, L) qty 10 and an unrelated (R, S) qty 5.
  After the push the Q row still describes product Q at M with its zone and placement, the (R, S)
  line is a new row, and `lines.adopted` is absent or 0 (the verdict keeps the fixed key set the
  sales / purchase order verdict has). Positional adoption never runs in a push that superseded a
  group.

- **AC-X30 [BE][T]** `ShippingOrderIngestService(may_delete=...)` defaults to False: constructing
  the service without the flag and pushing AC-X1's shape closes the xlsx row (`superseded_closed_only`)
  rather than deleting it; the route passes the resolved permission, the dedupe passes True.

- **AC-X31 [BE][T]** `repoint_allocation_dependants` requires `company_id` (a call without it is a
  TypeError); `scripts/backfill_grn_spo_allocation_links.py` registers the company-scope listeners
  and pins one company so its closing recompute reads rows again.

- **AC-X32 [BE][T]** (D26 remainder) Given an xlsx row received 50 against AutoCount lines
  allocated 29 and 18 (group total above the sum); after the supersede line 1 reads 29 and line 2
  reads 21 (remainder on the LAST line), both closed. The same shape through the D28a group
  recompute (picking total 50 on two `autocount` lines 29 / 18) yields 29 / 21.

- **AC-X23 (seed fix)** the reverse-payload-order test seeds received 30, not 47, so Seq order
  (29 / 1) and payload order (12 / 18) differ.

- **AC-X33 [BE][T]** (D28a status) The group recompute writes `line_status` consistently with
  `quantity_received`: a line whose receipt reaches its allocation reads closed, a line whose
  receipt is below it and was open stays open; a line already closed by the leftover sweep is
  never reopened. No row ends `closed` with `receipt_status pending`.

- **AC-X34 [BE]** `_autocount_group_members` filters `spo_number` in SQL (the query carries
  company, spo_number, product); a product present on many SPOs does not load them all.

## Round 4 (reviewer MB1 / MB2, 2026-09-07, PLAN D28c)

Fixture vocabulary: "stated" = `spo_allocations.stated_received`, the receipt the ESB (TransferedQty)
or a supersede / dedupe carry declared for an `autocount` line; NULL reads as 0.

- **AC-X28 (amended) [BE][T]** (D28c, MB1) The release case ends with line 1 back at its STATED 25,
  not 0: deleting the only GRN against an `autocount` line whose ESB-stated receipt is 25 returns
  the line to 25 (the seed sets `stated_received` 25 / 18). Line 2 keeps 18.

- **AC-X35 [BE][T]** (D28c, MB2) Two `autocount` lines allocated 29 / 18, stated 0 / 0, stored 0,
  one approved GRN of 47 against line 1: after `sync_grn_received_to_spo` the lines read 29 / 18
  closed. After `delete_grn` BOTH read 0, `line_status open`, `receipt_status pending`: the share
  that landed on line 2 leaves with the GRN that produced it, and a line closed by a receipt that
  is gone reopens. The same through `bulk_delete_grns`.

- **AC-X36 [BE][T]** (D28c) A line whose stated receipt is 29 (closed) never drops below 29 and never
  reopens when a sibling's GRN is deleted; `_write_received` reopens ONLY a line closed by a
  receipt (`receipt_status fully_received`) whose new receipt is below its allocation, never a
  `cancelled` line, and the per-allocation (`scm_upload` / NULL source) path is unchanged.

- **AC-X37 [BE][T]** (D28b draft gate, reviewer KB) With the AC-X28 seed and the picking line on a
  DRAFT `goods_received` header, neither `sync_grn_received_to_spo` nor
  `sync_received_for_spo_number` writes either line (25 / 18 unchanged, `updated_at` unchanged).
  Approving the header is what makes the recompute run.

- **AC-X38 [BE][T]** (D28c writers) `stated_received` is written by every declarer of an AutoCount
  line's receipt: the ESB push (`qty_received` of each line, max rule like `quantity_received`),
  the first-push supersede carry (each line's carried share) and the dedupe carry; the GRN
  recompute never writes it. After AC-X1 the two lines carry stated 29 / 18; after AC-X9's
  second push with `qty_received 0` they still carry 29 / 18.

- **AC-X39 [BE]** Migration `488_spo_alloc_stated_received` adds the nullable integer column and
  backfills `stated_received = quantity_received` for `source_system = 'autocount'` rows only;
  `alembic heads` stays single; the migration id is under 32 characters.

- **AC-X40 [BE][T]** (D28c retirement freeze, reviewer F2) An `autocount` line closed by a GRN
  (allocated 29, received 29 via one approved picking line, stated 0) that a later push of the same
  DocKey no longer names (leftover sweep closes it) carries `stated_received 29` after that push;
  deleting the GRN afterwards leaves it closed at 29, never reopened: a line AutoCount retired is
  not demand again because the CRM receipt that closed it went away. A sibling still named by the
  push behaves per AC-X35 (drops and reopens).
