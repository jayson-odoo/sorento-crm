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
