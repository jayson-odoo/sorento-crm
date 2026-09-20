# UAC: Sales order lines in AutoCount order, Source column, Plan CTA

Plan: `PLAN-so-lines-autocount-order.md`. Each AC is one pytest / vitest / browser check.

## S1 backend

- AC-S1-1 Migration adds `sales_order_lines.line_no` INTEGER NULL; single alembic head.
- AC-S1-2 Ingest: a pushed sales-order line with `line_number: 7` is stored with `line_no = 7`
  on create.
- AC-S1-3 Ingest: a re-push of the same `source_ref` with `line_number: 3` updates `line_no`
  to 3 on the same row id.
- AC-S1-4 Ingest: a re-push whose line omits `line_number` leaves `line_no` unchanged; an
  explicit `null` clears it.
- AC-S1-5 Ingest: the D11 adopt path (ref-less pool row claimed by position) stores the
  incoming `line_no` on the claimed row.
- AC-S1-6 Ingest: purchase-order lines still pop `line_number`; no `line_no` attribute is
  set on `purchase_order_lines`.
- AC-S1-7 `GET /sales-orders/{id}` lines carry `line_no` and `source`; both survive
  `response_model` (asserted on the wire, not the dict).
- AC-S1-8 Lines with `line_no` 1, 2, 10, 11, 3 come back ordered 1, 2, 3, 10, 11 (numeric).
- AC-S1-9 A closed line with `line_no` 1 sorts before an open line with `line_no` 2.
- AC-S1-10 Lines with NULL `line_no` come after every numbered line, ordered among
  themselves by today's rule (open first, required_date nulls last, product code).
- AC-S1-11 `source` labels: `autocount` -> `autocount`, `scm_order_inquiry` -> `inquiry`,
  `scm_upload` -> `upload`, `scm_so_history` -> `history`, other -> `manual`.
- AC-S1-12 A line with NULL `source_system` under an `scm_upload` header reports
  `source = "manual"` (R2: the line's own provenance, never the header's).
- AC-S1-13 Header: an `autocount` sales order reports `source = "autocount"` (was `manual`).
- AC-S1-14 List filter `source=autocount` returns AutoCount orders only; `source=manual` no
  longer returns them.

## S2 frontend

- AC-S2-1 Lines tab: first column is **No.**, showing `line_no`; `-` when null.
- AC-S2-2 Clicking No. sorts numerically: 1, 2, 3, 10, 11, 12 (never 1, 10, 11, 12, 2, 3).
- AC-S2-3 Default order is the server order (no client default sort).
- AC-S2-4 **Source** column renders AutoCount / Order inquiry / Upload / Absorbed history /
  Manual as a `Badge`.
- AC-S2-5 A user with a saved column order that predates the two columns still sees No.
  leftmost and Source visible.
- AC-S2-6 Header primary is **Plan**, linking to
  `/project-sales/fulfilment-planning?orders=<so_number>`; hidden without
  `projects.projects.view`.
- AC-S2-7 Gear dropdown holds Edit then Delete; Edit opens the edit session.
- AC-S2-8 In an edit session the header shows only Save / Cancel (unchanged); No. is a
  read-only value; a new session line shows `-`.
- AC-S2-9 Sales orders list source filter offers **AutoCount**; the Source pill on an
  AutoCount order reads AutoCount.
- AC-S2-10 Browser: SO detail reached by sidebar, 1280 and 375, an AutoCount order shows
  No. 1..n in order, Source AutoCount, Plan primary, Edit under the gear. Evidence
  screenshots under `documentation/plans/scm/evidence/so-lines-autocount-order/`.

## S3 fulfilment planning

- AC-S3-1 Board `_line_numbers`: an order whose lines all carry distinct `line_no` reports
  those numbers.
- AC-S3-2 Board `_line_numbers`: an order with one NULL `line_no` falls back to the derived
  rule for the whole order.
- AC-S3-3 Board `_line_numbers`: a fully mirrored order still reports the mirror's numbers.
- AC-S3-4 Adoption `_mirror`: lines with `line_no` 5, 1, 3 get mirror `line_no` 1, 2, 3 in
  the order 1, 3, 5.
- AC-S3-5 Adoption `mirror_missing_lines`: a later core line takes the next number; existing
  mirror lines keep theirs.
- AC-S3-6 Order inquiry sheet lists a freshly adopted order's lines in AutoCount order.

## Lane gate

- AC-G-1 pytest for touched files green locally; vitest touched files green; CI full gate
  green.
- AC-G-2 No `confirm()`, no UUID rendered, `extractApiError` / `buildDataGridParams` reused.
- No guide step for this lane (owner, 21 Sep).
