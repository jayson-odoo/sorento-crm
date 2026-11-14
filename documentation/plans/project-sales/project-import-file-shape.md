# TOTAL SALES ORDER SUMMARY 2026: masked shape of the owner's workbook (the format the project import reads)

Masked by crew from the owner's file (12 Nov 2026); the real file never enters this repo. All names, PO numbers, SO
numbers and amounts below are FAKE but keep the real shape. Counts and dates are the real file's.

## 1. Workbook

9 sheets, all visible, no hidden sheets, no data validation, no macros, no merged cells on the monthly sheets:

| # | Sheet name (verbatim, note trailing spaces) | Used range | PS-numbered rows | Role |
|---|---|---|---|---|
| 1 | `JAN'26` | A1:AK195 | 170 (PS26-0001..0170) | monthly register |
| 2 | `FEB'26` | A1:AK153 | 128 (0171..0298) | monthly register |
| 3 | `MAC'26 ` (trailing space; Malay "Mac" = March) | A1:AK198 | 173 (0299..0471) | monthly register |
| 4 | `APR'26` | A1:AK241 | 216 (0472..0687) | monthly register |
| 5 | `MAY'26` | A1:AK179 | 155 (0688..0842) | monthly register |
| 6 | `JUN'26 ` (trailing space) | A1:AK194 | 169 (0843..1011) | monthly register |
| 7 | `SUMMARY JAN-JUN` | B2:P26 | n/a | half-year roll-up + a list of big POs "without schedule" (merged cells F3:G4, F5:G5.., H3:H4, I3:I4, J3:J4, K3:K4, L3:L4, F24:G24, F25:G25) |
| 8 | `JUL'26 ` (trailing space) | A1:AK218 | 193 (1012..1204) | monthly register |
| 9 | `AUG'26` | A1:AK219 | 194 numbers allocated (1205..1398), only 78 filled in | monthly register (month in progress) |

Columns P..AK are empty except `Q8`, which holds a ~300-character string of spaces in every monthly sheet.
1398 PS numbers, all unique, `PS26-NNNN`, contiguous across the year. 1282 rows carry data (116 AUG rows are PS number only).
One PS number = one row = one customer PO (not one project).

## 2. Monthly sheet layout (all 8 identical)

Row 1 = header. Rows 2..N = data, ordered by PS number. After the last data row:
- Row N+1: a blank-labelled total of column H, formula `=SUM(H2:H<N>)`.
- 6-7 blank rows.
- A salesperson roll-up block in B:D: title `SALES ORDER SUMMARY <MONTH> 2026` (B), header `SALESPERSON | TOTAL PO | TOTAL AMOUNT`,
  one row per salesperson (13-14, alphabetical; `-` in C when none), then a `Total` row with `=SUM(...)` in C and D. No PS number in A.

### Columns A..O, headers verbatim (`\n` = a line break inside the cell)

| Col | Header (verbatim) | Type seen | Fill (1282 data rows) | Pattern / values (masked) |
|---|---|---|---|---|
| A | `RUNNING \nPS NUMBER` | text | 100% | `PS26-NNNN`, unique |
| B | `SALES\nPERSON` | text | 100% | 17 distinct after trim; short names (`ALVIN`, `BELLA`); some with a trailing space (34 rows on the most frequent, 5-6 on two others); the summary sheet uses `<FIRST> <SURNAME>` (`ALVIN WONG`) |
| C | `CUSTOMER SERVICE` | text | 100% | 12 distinct first names (`KATE`, `LUNA`) |
| D | `CUSTOMER ` (trailing space) | text | 100% | company name in capitals, 202 distinct after trim/upper; 28 rows with leading/trailing spaces; `SDN BHD` / `SENDIRIAN BERHAD`. The dealer / trading house that places the PO |
| E | `PROJECT NAME                              REF: ` (padded) | text | 73% (937 rows) | free text; 577 distinct, 643 distinct (customer, project) pairs; 50 rows with stray spaces; "replacement", "additional order PO ..." |
| F | `DEVELOPER                                 REMARK 1 : ` (padded) | text | 41% (524 rows) | developer / end user or a remark such as `END USER`; 204 distinct |
| G | `PO \nNUMBER` | text 88% / integer 12% | 100% (AUG placeholders excepted) | `AA-NNNNN`, `AA/NN/NN/NNN`, `NNNNNN`, `AANN/NNNN`, ...; 3 repeated (customer, PO) pairs |
| H | `TOTAL \nVALUE` | number (int 55%, float 45%), text `-` on 7 cancelled rows | 100% | MYR |
| I | `DATE` | date | 100% | 1266 in 2026, 16 in 2025 (JAN sheet first three rows dated 02/01/2025: year typo); 10 rows in another month than their sheet |
| J | `AMENDED \nDATE` | ~85% empty; text (`amend 9/4/2026`, `AMEND 14/5/2026`, `revised 3/4/2026`, `REVISED`, `amend`, a single space), 6 real dates | ~12% | typos (`AMEND 8/4/202`) |
| K | `SCHEDULE     YES/NO` (padded) | text | 90% | `YES` 1064, `O/C` 207, `NO` 1, `YS` 1, `CBD` 1, blank 124 |
| L | `DELIVERY DATE` | date 25% / text 62% / blank 12% | 88% | `IMMEDIATE` 485, `SCHEDULE` 140, `URGENT` 59, `NEXTWEEK`, `COURIER`, `LALAMOVE`, `AFTER CNY`, `1Q 2027`, `END JUL`, `TBA/ FEB 2027`, typos `IMMDIATE`, `URGNT`; 326 real dates |
| M | `OUTSTANDING` | text | 5 rows | `CANCELLED`, `CANCELLED 12/6/2026`, `on hold 23/4/2026` |
| N | `SO NUMBER` | text | 91% (1167 rows) | `SO` + 6 digits; 18 rows with several SOs separated by `,` or `, ` (up to 6); `CANCELLED`, `CANCELLED 11/5/2026`, `refer PS26-0022`; 227 blank |
| O | `REMARKS` | text | ~60 rows | `WAIVE TRANSPORT CHARGE` + spellings `TRASNPORT`, `TRASPORT`, `TRANPORT`, plural; `CANCELLED`, `CANCELLED BY CASH`, `CANCEL PS NO`, `HOLD`, an SO number |

## 3. Masked example rows

| PS | Sales | CS | Customer | Project | Developer | PO | Total | Date | Amended | Sched | Delivery | Outst. | SO | Remarks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PS26-0100 | ALVIN | KATE | CUSTOMER 001 SDN BHD | PROJECT 001 SAMPLE NAME | | JV/PO/7430/75 | 25487 | 02/01/2025 | | YES | 1Q 2027 | | SO498152 | |
| PS26-0113 | BELLA | LUNA | CUSTOMER 002 SDN BHD | PROJECT 002 SAMPLE NAME | DEVELOPER 001 | HQ/75/30/303 | 49.68 | 05/01/2026 | | YES | 06/01/2026 | | SO498686 | |
| PS26-0126 | CARL | KATE | CUSTOMER 003 SDN BHD | PROJECT 003 SAMPLE NAME | DEVELOPER 002 | 012119 (integer in file) | 10090 | 03/02/2026 | | YES | 01/07/2026 | | SO463179 | |
| PS26-0139 | DIANA | MIKE | CUSTOMER 004 SDN BHD | | | OT35/7855 | - | 04/05/2026 | | YES | IMMEDIATE | | CANCELLED 11/5/2026 | |
| PS26-0152 | CARL | NORA | CUSTOMER 005 SDN BHD | | | 63481090/B7B | 2240.99 | 03/03/2026 | amend 9/9/9999 | YES | IMMEDIATE | | SO464169 | |
| PS26-0165 | ALVIN | KATE | CUSTOMER 006 SDN BHD | | | UT-PO301883 | 80286.66 | 14/04/2026 | | YES | SCHEDULE | | SO466355,SO466352, SO466351 | |
| PS26-0178 | BELLA | LUNA | CUSTOMER 007 SDN BHD | PROJECT 004 SAMPLE NAME | DEVELOPER 003 | EM/PO/7534320 | 581.15 | 01/04/2026 | | YES | 02/04/2026 | | SO462360 | WAIVE TRANSPORT CHARGE |

## 4. `SUMMARY JAN-JUN` sheet

Not a register; no PS numbers. `B2 WITH SCHEDULE`, `F2 WITHOUT SCHEDULE`. Left block B3:D20: title
`SALES ORDER SUMMARY JANUARY -  JUNE 2026`, header row 4 `SALESPERSON | TOTAL PO | TOTAL AMOUNT`, 15 salesperson rows, `Total`
row 20. Right block F3:L22: header `SALES PERSON (F:G merged) | CUSTOMER NAME | PROJECT NAME | PO NO | PO DATE | VALUE`, 18 rows of
large POs without schedule, dates 2025-06 to 2026-08. `REVENUE TOTALS` in row 25. A stray `.` in L24.
