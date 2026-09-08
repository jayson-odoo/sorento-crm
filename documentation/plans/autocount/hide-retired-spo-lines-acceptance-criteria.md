# UAC: hide retired SPO allocation lines

Status: DRAFT 2026-09-08. Plan: `PLAN-hide-retired-spo-lines.md`. Depends on PR #740.

Tags: [BE] backend, [T] tester writes it red first, [S] backfill script. Postgres only, seed every
row under a marker.

- **AC-H1 [BE][T]** (R1) A document holding one open line and one line with `retired_at` set
  (received 0) returns only the open line from `get_document`; `total_allocated` counts the open line
  only; Balance is unchanged.

- **AC-H2 [BE][T]** (R1) A line closed with `receipt_status = 'fully_received'` and `retired_at` NULL
  is still returned, and still counts in `total_allocated` and `total_received`.

- **AC-H3 [BE][T]** (R2) A line with `retired_at` set AND `quantity_received > 0` is still returned,
  counts in `total_received`, and reads balance 0.

- **AC-H4 [BE][T]** (R5) Every returned line that is not outstanding reads `balance 0`; the sum of
  the returned lines' balances equals the document's Balance.

- **AC-H5 [BE][T]** (R3) A GRN whose picking line points at a hidden allocation still renders that
  allocation in the GRN detail response; the allocation is reachable by id.

- **AC-H6 [BE][T]** (R6) The grid (`list_allocations`, `list_documents`) and the detail builder all
  read one clause from `spo_supply`; a test asserts the three agree on the same seeded document.

- **AC-H7 [S][T]** (backfill) Given an autocount row closed with receipt 0 and `retired_at` NULL, a
  fully-received closed row, and a closed row with a partial receipt: `--dry-run` writes nothing and
  names one document; `--apply` stamps only the first row; a second `--apply` reports zero.

- **AC-H8 [BE]** SPO-2026/09-0036 after the backfill: 33 lines' worth of open supply, Total qty
  38,777, no C-FHSS14 line of 4412.

## Round 2 (security review, 2026-09-08)

The plan's premise that a line closes for two reasons only is wrong. Four writers close an
`autocount` line without retiring it: the SCM outstanding book's absence sweep
(`outstanding_import_service`, which means the goods ARRIVED and deliberately writes no receipt),
a cancelled document (`force_closed`), the deletion service keeping a referenced row, and a
receipt. So "closed, never received" is not evidence of retirement.

- **AC-H9 [S][T]** (B1, backfill evidence) The backfill stamps a row only when it also carries a
  `source_ref` AND its `(company, spo_number, product_id, upper(location_code))` group holds an OPEN
  row created strictly later. That is the replacement AutoCount wrote when it edited the line.
  Negative cases, none of them stamped: a line closed by the outstanding book's absence sweep (no
  later sibling), every line of a cancelled document (no OPEN sibling exists), a closed line whose
  group has no later row at all, and a row with `source_ref` NULL.

- **AC-H10 [BE][T]** (B2, receipt after retirement) Given a retired allocation (received 0) and a
  goods-received note approved AFTER the retirement whose picking line draws 5 against it: the
  allocation reads `quantity_received 5`, stays visible on the document, and counts in
  `total_received`. It takes no share of its group's receipt and is never reopened. A retired line
  whose stated receipt is 29 and whose goods-received note is then deleted still reads 29 (the D28c
  floor, AC-X40 unchanged).
