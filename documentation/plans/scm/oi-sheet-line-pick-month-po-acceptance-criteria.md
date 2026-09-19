# UAC - order inquiry sheet: line pick by exact date, then same month, then the sheet's PO

Plan: `PLAN-oi-sheet-line-pick-month-po.md`. Owner rulings 19 Sep 2026 (R1 to R6 in the plan).

Fixture shape for every AC below is the measured one, SO324265 / BT012-CR (prod, 19 Sep):

| Book line `required_date` | qty | Book PO (`from_so_line_ref` -> PO) |
| --- | --- | --- |
| 2025-12-01 | 200 | 202508-S0012 |
| 2026-01-02 | 200 | 202510-S0049 |
| 2026-04-02 | 200 | 202510-S0049 |
| 2026-05-01 | 200 | 202510-S0049 |
| 2026-05-02 | 200 | 202510-S0049 |
| 2026-05-04 | 200 | 202603-S0033 |
| 2026-06-01 | 222 | 202603-S0033 |

| Sheet row delivery date | qty | Sheet PO |
| --- | --- | --- |
| 2026-01-02 | 200 | 202510-S0049 |
| 2026-02-02 | 200 | 202510-S0049 |
| 2026-03-02 | 200 | 202510-S0049 |
| 2026-04-01 | 200 | 202510-S0049 |
| 2026-05-04 | 200 | blank on the month tab, 202603-S0033 on the roll-up tab |
| 2026-06-01 | 222 | blank on the month tab, 202603-S0033 on the roll-up tab |

## Line pick

- **AC-LP-1** Clean database, the fixture above: six rows raise, one per 2026 line. 01-02 -> 01-02,
  04-01 -> 04-02, 02-02 -> 05-01, 03-02 -> 05-02, 05-04 -> 05-04, 06-01 -> 06-01. The 2025-12-01
  line carries NO order inquiry row.
- **AC-LP-2** Exact date beats file order: a row with no exact-date line, stated EARLIER in the
  file than a row whose exact-date line it also fits, never takes that line. (Swap the tab order
  in the fixture; the landing in AC-LP-1 does not change.)
- **AC-LP-3** Same month beats file order: the 02-02 row, stated before the 04-01 row, does not
  take the 04-02 line.
- **AC-LP-4** Same month, two lines in the month (add a 2026-04-20 line bought by another PO):
  the 04-01 row lands on the line whose book PO is the sheet's PO; with no PO to tell them apart,
  the nearest date, then the existing tie-break terms.
- **AC-LP-5** Sheet PO pass: rows left after the month pass land on free lines whose book PO is a
  PO the row cites, handed out in date order (earliest row to earliest line).
- **AC-LP-6** A row that cites no PO anywhere in the file, or whose cited PO names no free line,
  falls to today's rank unchanged (bought, open, earliest date, oldest, id).
- **AC-LP-7** The sheet's PO still PAIRS nothing: the link written for every row in AC-LP-1 is the
  book's own (`links_from_autocount`), and a row whose sheet PO differs from the book's PO for
  the line it landed on links to the BOOK's document.
- **AC-LP-8** A cancelled line still ranks behind every live line in every pass, and is still
  taken when it is the only line that fits (D1 kept).
- **AC-LP-9** An ORDER BACK row (no delivery date) takes part in no date pass and no month pass;
  it may land through the PO pass or the fallback.
- **AC-LP-14** (R4, prod C-FH14 / SO324265, 19 Sep 2026) The sheet's own PO outranks the month
  when they disagree: a row whose citation names a DIFFERENT purchase order than the only line
  in its own month does not take that line, even stated first in the file - the citation-alone
  pass settles it (or the fallback, if nothing free cites it), never the month pass.
- **AC-LP-16** (R6, prod CB2805A-DIY / SO324265, 19 Sep 2026) Inside EVERY pass, a line whose
  `qty_ordered` EQUALS the row's own quantity is tried before any bigger line, even one that
  would otherwise win the pass's own tie-break (created-at, or earliest date). Reached through
  the exact-date pass, the citation-alone pass, or the fallback alike. A row that splits a line
  (its own quantity smaller than every candidate) is unaffected and still lands as AC-S1-2 and
  AC-LP-12 describe. The equal-quantity step never offers a CANCELLED line ahead of a bigger
  LIVE one that also fits (D1 holds inside it too, not only the ordinary rank); a lone cancelled
  line still matches through the ordinary step, unchanged. A plannable order that holds NO lines
  at all still reports its row `no_line_for_item`, never an exception that rolls the whole
  upload back.

- **AC-LP-17** (R7, prod comparison workbook, 19 Sep 2026) A cancelled line may only be taken
  by the fallback pass. Passes 1 to 4 never offer a cancelled candidate, even when it is the
  ONLY candidate a narrowed pass would otherwise have found - a cancelled line dated exactly
  the row's own date, or sharing its month, or named by its own citation, is invisible to
  those four passes, not merely ranked last inside them. A live line elsewhere in the order
  that a later pass can reach, through its own citation or the fallback, is landed on instead.
  With no live line anywhere in the order, the fallback still takes the cancelled one rather
  than refusing the row (D1 kept).

## Citation lending

- **AC-LP-10** A restatement that carries a PO lends it to the first statement when that one
  carries none (05-04 and 06-01 in the fixture end up citing 202603-S0033 for the line pick). A
  first statement that already cites a PO keeps its own. Lending never changes the duplicate
  count, the ledger or the note.
- **AC-LP-15** (R5, prod CB1178A-SS-NEW / SO324265, 19 Sep 2026) A restatement is only ever
  ACROSS tabs. Two identical rows inside the SAME tab are two separate instructions, not one
  restated: each raises its own line. On a LATER tab, the n-th row carrying that same key
  restates the n-th instruction by POSITION - not just the first one ever seen - so a roll-up
  that repeats a key fewer times than the month tab did still restates only that many of them,
  and a roll-up that carries a different citation on each repeat lends each one to the
  matching-position instruction, never to the wrong one or to only the first.

## Re-upload

- **AC-LP-11** Re-upload of the same file after AC-LP-1: `rows_raised` 0, `rows_already_raised` 6,
  and every row reports the SAME line it landed on the first time (no two rows on one line).
- **AC-LP-12** Ledger: a row that lands on an already-raised line charges the file's ledger, so
  the next same-item row cannot land on that line again. Two sheet rows that legitimately split
  one line (qty 120 + 80 on a 200 line, AC-S1-2) still both land on it. Two rows equal on all
  five `_restates` terms are one instruction written twice, not a split. A row bumped off a full
  already-raised line lands on the order's next free line, as a first upload would land it.
- **AC-LP-13** Preview and apply land every row on the same line (determinism, as today).

## Not in scope

- Moving rows that an earlier upload already placed on the wrong line (D2 stands). Prod repair is
  rollback + re-upload by the owner after deploy, as after #918.
- Any change to pairing, claims, the worklist or the board.
