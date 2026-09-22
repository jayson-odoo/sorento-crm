# PLAN - Board + OI mechanical fixes (lane B)

Status: planned, round 2 after owner markup (22 Sep 2026); S5 wording choice pending. Track:
normal lane (BE + FE, tests, one PR). UAC: `board-oi-mechanical-22sep-acceptance-criteria.md`.

Owner rulings, 22 Sep 2026 (chat + lavish round 1): grid shows exact delivery date, many
columns fine, "By day" stays as a fourth option; a date move never makes a second row, settle
in place, ack `changed`, same for linked rows, no Ack column on screen; Taken / Remaining
columns with footer sums, notices excluded, Remaining 0 on cancelled; NO default supplier on
unlinked rows; reserve echo DROPPED; cleanup script covers every OI, owner runs it; State pill
gets plain words (new slice S5, wording choice open).

## What exists (measured on the code, 22 Sep)

- Week bucketing is server-side: `bucket_key_for` / `_bucket_label`
  (`app/services/project_fulfilment_board_service.py:175-229`); `day` granularity exists as a
  30-day calendar window (`DAY_WINDOW_COLUMNS`, `:143`, `day_window_start`, `:605`, `:791`,
  `:5033`). FE only pivots on `bucket_key` (`_shared/lib/fulfilmentBoard.ts:919-964`) and
  strips `w/c` (`:42-56`); select options at `FulfilmentBoardPanel.tsx:139-141`.
- Settle in place exists: `_settle_row_in_place`
  (`app/services/project_order_inquiry_service.py:1476-1660`). It declines when the line has
  0 or 2+ live buy rows (`:1518-1527`) or a lone placed row without links (`:1532`).
  `planning_change_service._oi_demand_rows` (`:3843`) raises an `ADVANCE` / `DELAY` demand
  row for every `advanced` / `delayed` change whose line is NOT in `settled_line_ids`. So the
  second row appears exactly when settle declined. B2155-NL-BLUE line 688 on OI-2609-0678 is
  the fresh-line shape (AC-B2-4).
- Row payload already carries `linked_qty` and `links` (`project_order_inquiry_service.py:4350`,
  worklist `order_inquiry_worklist_service.py:2002`); Lines tab footer sums `qty` client-side
  over all loaded rows (`orderInquiryHeaderLinesColumns.tsx:70-75`), cancelled rows included.
- State pill labels: one map in `_shared/components/OrderInquiryVerbPill.tsx:89-98`
  (`raised: 'Raised'`, `placed: 'Linked'`, `partly_linked: 'Partly linked'`,
  `actioned: 'Actioned'`, `cancelled: 'Cancelled'`). The "changed since you looked" tag on the
  worklist reads `ack_state === 'changed'`.

## Design

### S1 - `date` granularity
Backend: granularity `date` in `bucket_key_for` (same key as `day`), `bucket_end` (same as
`day`), `_bucket_label` (`DD/MM/YYYY`). `dateBuckets` for `date` = keys present in `rows`,
sorted, `No date` last, `is_past` as today; the day-window path is not entered. `day` stays
exactly as it is. Frontend: options `By date` (default) / `By day` / `By week` / `By month`;
`bucketKeyFor` in `fulfilmentBoard.ts` learns `date`; header prints the server label.

### S2 - date move settles in place, no notice
Rule: **a line with any buy row (live, placed or done) gets the date stamped on those rows; a
notice row is raised only when the line has no buy row and the confirm raises none.**

Repro first on the 0921 copy: confirm the batch for OI-2609-0678's lines, log which decline
branch fires.

1. `_oi_demand_rows` (`planning_change_service.py:3843-3865`): skip the notice when the line
   has any non-cancelled buy-verb row OR `out` already carries a buy entry for the same
   `line_id` from this confirm (AC-B2-4). The fresh buy row's note gets `Was <old date>`.
2. New `_stamp_date_move(rows, new_date, actor)` beside `_settle_row_in_place`: for every buy
   row of the line in raised / partly_linked / placed / actioned, set `previous_delivery_date`,
   `delivery_date`, `previous_qty=qty`, `changed_at`, note `Was <qty> on <old>`, ack
   `acknowledged`→`changed`, `_record_handover(kind="changed")`. Links untouched. Called from
   the decline branches (2+ live rows; placed with no links) and the actioned-only shape, when
   the entry's `required_date` differs. The single-live-row branch is unchanged.
3. Handover context: date-only changes already print under `changed`
   (`_handover_settle_diff`, `:310`); assert, do not rewrite.
4. Screen: no Ack column. The Lines tab shows the worklist's existing `Changed` tag beside the
   delivery date when `ack_state === 'changed'`, next to the (i).

Script `scripts/fold_oi_date_notices.py`: `--dry-run` default, `--apply`, every OI. Selection =
live `ADVANCE`/`DELAY` with a non-cancelled buy row on the same `so_line_id`. Parses
`Was <date>` from the notice note; where absent, cancels the notice and reports "no Was date".
Idempotent. Owner runs it on prod via `docker cp` + `docker exec`.

### S3 - Taken / Remaining
Frontend only. Shared `inquiryRowTaken(row)` / `inquiryRowRemaining(row)` helpers in
`_shared/lib` (buy verbs only; `-` for notices; `0` and excluded when row or line cancelled),
two `ColumnDef`s used by BOTH `orderInquiryHeaderLinesColumns.tsx` and
`orderInquiryWorklistColumns.tsx`, footers for Qty / Taken / Remaining over buy rows minus
cancelled. Supplier column untouched.

### S5 - plain words on the State pill
One map edit in `OrderInquiryVerbPill.tsx:89-98`, stored values unchanged. Owner's pick
(lavish round 2): raised → **To buy**, partly_linked → **Partly on PO/SPO**, placed →
**On PO/SPO**, actioned → **Done**, cancelled → **Cancelled**. The same map feeds the
worklist, the Lines tab, the board chips and any email template that reads the label; tester
greps for the old words in templates and snapshots.

### S6 - OI row ⇄ SO line deep links (owner ask, lavish round 2)
Both directions land on the exact row, scrolled into view and highlighted for ~2s.
- OI Lines tab + worklist: new column **SO line** = `SO402757 · L5`, link to
  `/scm/sales-orders/<sales_order_id>?tab=lines&line=<core_line_id>`. Ids already on the row
  payload (`so_number`, `so_line_id` mirror id, `project_sales_order_id`,
  `order_inquiry_worklist_service.py:649-676`); the mirror → core line id resolves server-side
  into a new `core_line_id` field on the row.
- SCM sales order detail, Lines tab: the existing **Order inquiry** column
  (`SalesOrderDetail.tsx:1124`) becomes a link to
  `/project-sales/order-inquiries/<inquiry_id>?row=<row_id>`; backend `sales_order_service.py:510`
  adds `row_id` and `inquiry_id` beside `inquiry_no`.
- Fulfilment planning LIST view (`FulfilmentBoardListView.tsx`, round 3): (a) new leftmost
  **Line** column = AutoCount line number, sortable, default sort with Sales order; (b) the
  Sales order cell prints the number only, drops the `(Line N)` suffix (`:287-292`), and its
  href (`:304`) gains `?tab=lines&line=<core_line_id>`; (c) new **OI** column = the live
  row's inquiry number (`contribution.order_inquiry`, already on the payload with `_row_id`
  resolved server-side into `row_id` + `inquiry_id`), href to the OI detail row. Grid view
  untouched. Verdict/Decided cells untouched (they belong to the board-verdict-actions lane).
- Landing across pages: both landing grids page client-side (`getPaginationRowModel`,
  `SalesOrderDetail.tsx:1309`, `OrderInquiryLinesTab.tsx:69`). On landing: clear the grid's
  search box, find the target id in `getPrePaginationRowModel().rows`, `setPageIndex(floor(i /
  pageSize))`, then scroll + glow. Not found: toast "That line is not shown here", no glow.
- Landing: on mount, if `line` / `row` is present, select the Lines tab, `scrollIntoView`
  (the delivery-schedule pattern, `DeliveryScheduleReviewClient.tsx:250`), add a
  `data-highlight` class that fades over 2s (existing motion token, no new preset), then strip
  the param with `router.replace` so a refresh does not re-glow. Ids are URL-only, never
  printed (no-UUID rule holds).

### S4 - reserve echo: DROPPED (owner, lavish round 1).

## Test list (captain's, one line per AC)
- B1: `test_bucket_assignment_for_day_week_and_month` extended for `date`; new
  `test_date_granularity_lists_only_populated_dates`. Vitest: `FulfilmentBoardPanel` options;
  `fulfilmentBoard.test.ts` bucketKeyFor `date`; `FulfilmentBoardMatrix.test.tsx` headers
  `DD/MM/YYYY`.
- B2: `tests/scm/test_oi_confirm_per_so.py` + `tests/test_planning_change_apply_on_board.py`:
  one test per AC-B2-1..9; `tests/test_fold_oi_date_notices_script.py` for AC-B2-11..13;
  vitest: Changed tag beside the date on the Lines tab.
- B3: vitest for both column files (Taken/Remaining values, `-` on notices, footer sums).
- B5: vitest snapshot of the label map; grep test that no template still says "Raised".

- B6: vitest: SO line column renders `SO402757 · L5` with the href; SO detail Order inquiry
  cell href; landing scroll + highlight + param strip on both pages. pytest: `core_line_id`
  on the OI row payload; `row_id` + `inquiry_id` on the SCM SO line payload (response_model
  guard).

## Slices
S1 grid date · S2 settle + script · S3 columns · S5 words · S6 deep links. Phase 1 =
S1/S3/S5/S6 FE against mocks; Phase 2 = S1 BE, S2, S6 BE, tester first. One PR.

## Out of scope
Decision UX, verdict filter, OI number/qty in Decided cell, undo fixes (lane A, on top of the
board-verdict-actions lane); OI row move / edit / linkage view (lane C); worklist perf (lane D);
confirm-all profiling (lane E); reserve echo (dropped).
