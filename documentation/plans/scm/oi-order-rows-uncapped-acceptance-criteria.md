# UAC: An ORDER inquiry row is owed until linked (23 Sep 2026)

Plan: `PLAN-oi-order-rows-uncapped.md`. AC-OU-n.

- AC-OU-1: `scm.committed_v` counts an ORDER row of qty 493 whose core line is delivered
  493/493 and closed as project demand 493 at the line's warehouse.
- AC-OU-2: An ORDER row of 314 on a line with 12 outstanding counts 314 (the 14 Sep cap is
  retired, owner ruling R1 23 Sep 2026).
- AC-OU-3: Linked and bundled quantities still reduce it (493 with 100 linked and 10 bundled
  counts 383); a fully linked row counts 0.
- AC-OU-4: `horizon_committed_select_sql` returns the same figures as AC-OU-1..3.
- AC-OU-5: The worklist Remaining for the AC-OU-1 row is 493.
- AC-OU-6: `/reorder-runs/candidate-orders` lists an SO whose only rows are ORDER rows on
  delivered lines, `rows_total` equal to the row count.
- AC-OU-7: Uploading an ORDER row against a delivered, closed line RAISES it (state
  `raised`) - the candidate gate widens to `line_status != "cancelled"`, so the row reaches
  `raise_row` directly rather than being refused `order_fully_delivered`.
- AC-OU-8: Uploading an ORDER row against a cancelled line does NOT raise - it is skipped
  with the existing cancelled reason code (`order_fully_delivered` when it is the order's
  only line, `no_line_for_item`-style refusal otherwise) - and nothing is history-closed:
  `_close_history` is retired (R2), a cancelled line is refused before a row is ever raised
  against it.
- AC-OU-9: Migration 527 re-creates `scm.committed_v` in place, same columns and types,
  round-trips with 525, and the drift guard passes.
- AC-OU-10: `scripts/reopen_delivered_order_rows.py` refuses to run without
  `--delivery-from` (exit 2).
- AC-OU-11: With `--delivery-from 2026-09-01 --apply`, an importer-closed ORDER row with
  delivery 15 Sep on a delivered line becomes `raised` with `actioned_by/at` NULL and its
  header `raised`; a row with delivery 15 Aug, a person-actioned row, and a row on a
  cancelled line are untouched; the dry run writes nothing and prints each candidate.
- AC-OU-12 (browser, once a slot frees): Start Plan, Demand = Project, search SO421985: listed
  with 3 rows; the plan buys 493 of each of CB4702, CSH2072, CSA150.
