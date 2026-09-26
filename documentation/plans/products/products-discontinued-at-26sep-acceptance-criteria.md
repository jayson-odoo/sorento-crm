# UAC - Products list: "Discontinued at" column, sort and date-range filter

**Status:** in review, PR #1292 (Track: full - carries a data-only list-query catalog seed migration, so
not small-fix). Plan created 2026-09-26.
Companion plan: `PLAN-products-discontinued-at-26sep.md`. Issue: #1287.

> "The thing in our product is we need to have a filter to filter the date range of discontinued at because our system do store the discontinued at and discontinued batch. I think the discontinued batch is not so useful, but the discontinued at is very important. So we need to have the column of discontinued at beside the discontinued column. We should be able to sort by that, to filter by that in a date range. So we need to use a very nice date range picker, which can be typed and also select a from and to in one single calendar. So try to find some existing calendar component in our system."
>
> - Owner, 26 Sep 2026 ~14:00Z, issue #1287

## Journey

**Actor:** a purchasing / product admin reviewing which products went discontinued and when.

1. **First screen:** sidebar Products > All Products. The grid already shows the Discontinued
   pill; a new "Discontinued at" column sits right after it (blank for available products).
2. **Open Filters:** the Filters popover gains one control, "Discontinued between".
3. **Type or pick a range:** single decision - which days. They type `01/09/2026 - 26/09/2026`
   and press Enter, or open the one calendar and click a start then an end day.
4. **See the result:** the list reloads at page 1, a chip reads
   "Discontinued: 1 Sep 26 - 26 Sep 26", and only products discontinued in those Malaysia days
   remain. The chip's x (or Clear Filters) removes the range.
5. **Sort:** they click the "Discontinued at" header to see newest or oldest first.
6. **Export:** they export; the file carries only the filtered rows and can include a
   "Discontinued at" column with the Malaysia date.
7. **What they hold at the end:** a dated list (on screen or in a file) of the products
   discontinued in the window they care about.

Data caveat (not an AC): products discontinued before the notify feature shipped show the first
scheduler tick's date, not the true historical date; a just-discontinued product stays blank
for up to 15 minutes. See the plan.

## Acceptance criteria

### Column (journey step 1)

- **AC-COL-1 [FE]** Given a product with `discontinued_at` set, when the list renders, then the
  "Discontinued at" column immediately after "Discontinued" shows its Malaysia date as
  DD/MM/YYYY; given `discontinued_at` null, the cell is blank.
- **AC-COL-2 [FE]** Given the grid Columns control, when opened, then "Discontinued at" is
  listed, visible by default, and can be hidden and shown again.
- **AC-COL-3 [BE]** Given GET `/api/v1/master-data/products`, when rows return, then every row
  carries `discontinued_at` (ISO timestamp or null) sourced from `discontinued_notified_at`.

### Sort (journey step 5)

- **AC-SORT-1 [BE]** Given products with mixed and null `discontinued_notified_at`, when
  `sort=discontinued_at&dir=asc` and `dir=desc` are requested, then rows order by that column,
  nulls last in both directions, ties broken by id.
- **AC-SORT-2 [FE]** Given the list, when the "Discontinued at" header is clicked, then the
  request carries `sort=discontinued_at` with the chosen direction.

### Filter (journey steps 2-4)

- **AC-FLT-1 [BE]** Given `discontinued_from=2026-09-26&discontinued_to=2026-09-26`, when the
  list is requested, then both ends are inclusive by Malaysia day: a row stamped
  2026-09-25 16:30 UTC (26 Sep MYT) is included, a row stamped 2026-09-25 15:59 UTC (25 Sep MYT)
  and one stamped 2026-09-26 16:00 UTC (27 Sep MYT) are excluded.
- **AC-FLT-2 [BE]** Given only `discontinued_from` (or only `discontinued_to`), when requested,
  then the open end is unbounded; given any bound set, rows with a null date are excluded.
- **AC-FLT-3 [BE]** Given `discontinued_from=26-09-2026` (or any non YYYY-MM-DD value), when
  requested, then the response is 422.
- **AC-FLT-4 [BE]** Given POST `/api/v1/list-query/search` for products with
  `discontinued_from` / `discontinued_to` in the body, when executed, then the same inclusive
  Malaysia-day semantics as AC-FLT-1/2 apply.
- **AC-FLT-5 [FE]** Given the Filters popover, when a range is picked, then the request sends
  `discontinued_from` / `discontinued_to` as YYYY-MM-DD, the page resets to 1, and moving to
  page 2 keeps both params.
- **AC-FLT-6 [FE]** Given an applied range, when the toolbar renders, then the Filters count
  includes it and one chip shows "Discontinued: <from> - <to>" (or "Discontinued: from X" /
  "Discontinued: to Y"); when its x or Clear Filters is clicked, both params are removed.
- **AC-TYPE-1 [FE]** Given the "Discontinued between" input, when `01/09/2026 - 26/09/2026` is
  typed and Enter pressed, then the filter applies with 2026-09-01..2026-09-26; and when the
  calendar is opened, one calendar selects both the start and the end.

### Layout (all steps)

- **AC-MOB-1 [E2E]** Given a 375 px viewport, when Filters is opened and a range picked, then
  the popover and picker are fully usable and the page has no horizontal scroll; the grid
  scrolls sideways inside its own container. The same flow works at 1280 px.

### Export (journey step 6)

- **AC-EXP-1 [BE]** Given the products export catalog, when fields are listed, then
  `discontinued_at` appears with label "Discontinued at", and an exported row's value is the
  Malaysia calendar date (YYYY-MM-DD), blank when null.
- **AC-EXP-2 [BE]** Given POST `/api/v1/list-query/export` with `discontinued_from` /
  `discontinued_to`, when executed, then only rows inside the range are exported.
- **AC-EXP-3 [FE]** Given an applied range, when the user exports, then the export request
  payload carries `discontinued_from` / `discontinued_to`.
