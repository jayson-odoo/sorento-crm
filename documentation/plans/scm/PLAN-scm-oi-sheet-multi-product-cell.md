# PLAN: order inquiry sheet - one item cell naming several products

Status: S1 built, 18/18 pytest green (`tests/test_oi_sheet_multi_product_cell.py`), 15 Sep
2026. Lane `fix/oi-sheet-multi-product-cell`, worktree
`.claude/worktrees/oi-sheet-multi-product`, private test DB `sorento_oimp_ci`.

AC-M-13 evidence (`_plan` + `_pair` called directly against `sorento_ai_automation_0907`,
`JAN - DEC 2026 ORDERabc.xlsx`, 16,057 source rows; `preview()`'s `line_not_found` is capped
at 200 so the plan step was read directly for the true count):

| | before (base `bbd18baec`) | after (this slice) |
|---|---|---|
| rows (expanded) | 16,057 | 16,298 |
| rows_raised | 481 | 630 |
| rows_line_not_found | 433 | 423 |
| entries in line_not_found whose item_code still contains `+` | 91 | 0 |
| links_written | 0 | 6 |

`rows_raised` rose by 149 (the members that now match a line) and every `line_not_found`
entry that used to carry a whole `+` cell (91 of them) is gone, because a split member's own
code never contains `+` (the four real `+`-named products aside, and none of those missed).
`rows` (expanded) grew by 241 over the 16,057 source rows - the member rows the 173 `+`
cells add once split.

UAC: `scm-oi-sheet-multi-product-cell-acceptance-criteria.md`.

Parent plan: `PLAN-scm-oi-sheet-migration.md`; sits beside `PLAN-scm-oi-sheet-pairing-repair.md`
(section 8 shipped in #918) and changes nothing that plan decided.

## 0. What was measured before writing this

Measured on `JAN - DEC 2026 ORDERabc.xlsx` (the customer's own monthly book, 35 tabs) and
the local prod copy `sorento_ai_automation_0907`, 15 Sep 2026:

| | count |
|---|---|
| sheet rows with an item code | 16,060 |
| item cells joining several product codes with `+` | 173 (1.1%) |
| distinct `+` spellings | 30 |
| products whose OWN code contains `+` | 4 (`FUR-GA30T+A66C`, `FUR-GA905T+A908C`, `FUR-GA3131T+A58C`, `P69190C-ENG + D969-ENG`) |

The `+` cells are the customer writing a set that is always sold together - a WC pan, its
cistern and its seat cover - as ONE row: `SRTWCX8608-RL + SRTWCY8608 + SRTWC8608-SC`
(13 rows), `CWCX604-S-RL-NEW + CWCY604 + CWCSC604-QQ` (25), `CKS1050 + CKSW015` (17, also
written `CKS1050+CKSW015` with no spaces, 4), `SRTBT005 + ACC-SRT8003` (13), two-member
variants such as `CWCX605-RL + SRTWC8605-SC-RL` (3, also `CWCX605-RL +SRTWC8605-SC-RL`).

AutoCount holds them as SEPARATE lines, one per member, each at the cell's quantity:
SO375551 row `SRTWCX8608-RL + SRTWCY8608 + SRTWC8608-SC` qty 5 sits on the book as three
codes with 3 + 2 on each. So one sheet row is N sales order lines, every one at the row's
own quantity - not the quantity shared out.

Today (`project_order_inquiry_import_service._match_row`, line 427) the cell is compared
whole against the order's line product codes, so every one of the 173 rows lands in
`line_not_found` as `no_line_for_item` and nothing is raised for them.

Not `+`, and NOT in scope: `CKS1050 C/W WASTE` (14 rows, a remark glued to the code),
`SRTKS2406-O/F` (a real product code), `RPACC- HOLDER & SCREW ONLY FOR SRT86-BL` (free text).
They keep today's outcome. Only `+` joins products in this book.

## 1. The rule

**An item cell that names no product line on the order, and joins several codes with `+`,
is one row per member.** Each member row carries the cell's quantity, delivery date,
location, remark, purchase-order citations, ORDER BACK flag, sheet and source row. A cell
that IS a line's product code, `+` and all, stays one row - the four `FUR-…+…` products
must not split.

Split on `+` only, whitespace either side optional (`A + B`, `A+B`, `A +B` are the same
cell). Empty members from a stray leading or trailing `+` are dropped. No other separator
splits: `&`, `/`, `C/W` stay in the cell (section 0 lists why).

## 2. Where it lives

`app/services/project_order_inquiry_import_service._plan`, after `lines = _lines_of(...)`
and before the match loop: the matches list is built from the EXPANDED rows, not
`parsed.rows`. The reader (`project_order_inquiry_reader.py`) stays pure and unchanged - it
has no products to ask, and the guard in section 1 needs the order's line codes, which
`_plan` already holds per order in `lines[order.id]` (tuple index 1 is the product code).

One helper, `_members(row, line_codes: set[str]) -> list[OrderInquiryRow]`:

* `item_code` in `line_codes` or no `+` in it: `[row]`.
* else: `dataclasses.replace(row, item_code=member)` for each non-empty
  `re.split(r"\s*\+\s*", item_code)` member.

An order not found or not plannable expands the same way (the outcome is per row either way,
and the count of member rows in `line_not_found` is what the operator reads).

Everything downstream is untouched and already right for member rows:

* `_restates` keys on the member `item_code`, so a roll-up tab restating a `+` row raises
  each member once (AC-R-11 kept).
* the `taken` ledger charges each member's line for the cell quantity.
* `_pair` links each member row to its own document.
* `_identity` / `_result` name the member code; `line_not_found` lists the member that has
  no line, while its siblings raise.

`rows` in the result and `on_total_rows` report the EXPANDED count, because
`ImportOutcome` records one outcome per member row and the job page prints processed /
total: 16 of 16, never 18 of 16. The reader's `parsed.rows` is not mutated.

## 3. Out of scope

* No new columns, tables, settings. No frontend change: the worklist and job detail already
  render per row.
* No companion / supplied-with derivation here: `derive_bundles` runs after a row is raised
  and keeps working on member rows as it does on any row.
* No change to the four `+` products or to the `C/W` / `&` cells.

## 4. Slices

S1 (BE, one slice): `_members` + expansion in `_plan`; `rows` / `on_total_rows` on the
expanded count. Tests test-FIRST in `tests/test_oi_sheet_multi_product_cell.py`, seeded via
`tests/test_project_order_inquiry_import_migration.py`'s `World`, `sheet`, `book`, `world`.

Evidence (not a test): `preview` of the real book against the 0907 copy, before and after,
counting `+` rows in `line_not_found` and `rows_raised`. Expected: the 173 rows leave
`line_not_found` except members with no line on the order; `rows_raised` rises by the
members that match.
