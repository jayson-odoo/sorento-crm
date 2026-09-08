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
