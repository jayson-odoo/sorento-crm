# UAC - SPO planner feedback, 3 Sep 2026

Plan: `PLAN-scm-spo-planner-feedback-3sep.md`. Tags: `[FE]` vitest, `[BE]` pytest, `[E2E]`
agent-browser evidence on :3160 via the sidebar.

## A. Planner chrome (S1)

- **AC-A1** `[FE]` No text renders under the "SPO planner" title, on a draft or a real
  shipment.
- **AC-A2** `[FE]` No "ticked, ... on this container ... partly covered" text renders. The
  red "nothing left for it" and "split does not add up" texts still render when their
  condition holds, and Create SPO stays disabled while they do.
- **AC-A3** `[FE]` The Product cell renders the item code (and the reason icon when there
  is a reason) and nothing else.
- **AC-A4** `[FE]` The PO covers cell renders the covered figure and no "of N POs" text.
- **AC-A5** `[FE]` Expand all / Collapse all sit in the same group as the Table / Schedule
  toggle; their position does not change when a red condition text appears or disappears.
- **AC-A6** `[FE]` In schedule view the control is labelled **View** with options
  **Purchase order** and **Sales order**, right-aligned, and the selected label renders on
  one line at 1280 and at 375.
- **AC-A7** `[FE]` Schedule row headers render the item code only.

## B. Lightbox description (S2)

- **AC-B1** `[FE]` `PlanRowDialog` with `productName` equal to `productCode` (or empty)
  renders no visible description; the description element is still present for assistive
  tech (`sr-only`).
- **AC-B2** `[FE]` With a `productName` different from the code, the description renders
  as before.

## C. Pickers (S3)

- **AC-C1** `[FE]` SO covered picker headers: Sales order, Customer, Class, Delivery date,
  Outstanding, Take, Location. PO covers picker headers: PO, Supplier, Doc date, Delivery
  date, Outstanding, Taken.
- **AC-C2** `[FE]` Both pickers render as a DataGrid with a sticky header and resizable
  columns.
- **AC-C3** `[FE]` Typing in the search and pressing Enter narrows the rows to those whose
  Sales order or Customer (PO or Supplier) contains the text; the clear X restores every row.
- **AC-C4** `[FE]` The Filters popover offers condition rows (SO picker: Sales order,
  Customer, Class, Location; PO picker: PO, Supplier); Apply narrows the rows; Clear filters
  restores them; the toolbar shows the active count.
- **AC-C5** `[FE]` A row ticked before a filter hides it is still ticked after the filter is
  cleared, and the footer's ticked / covered figures never change with the filter.
- **AC-C6** `[E2E]` Filter by Customer in the SO covered dialog on :3160; rows narrow;
  the SO covered figure on the planner row is unchanged.

## D. Schedule cells (S4)

- **AC-D1** `[FE]` A cell holding a take of this SPO has the `bg-primary/10` tint; an
  empty cell has none.
- **AC-D2** `[FE]` Clicking a cell in the Purchase order view opens `PO covers · <code>`
  for that line; in the Sales order view it opens `SO covered · <code>`. No popover renders.
- **AC-D3** `[FE]` In the opened picker, rows whose date falls in the clicked week carry
  `data-bucket-hit` and the row tint.
- **AC-D5** `[FE]` In schedule view a legend renders under the matrix with a blue swatch
  labelled "This SPO" and a grey swatch labelled "Another SPO"; it does not render in table
  view.
- **AC-D4** `[E2E]` Click a schedule cell on :3160; the dialog opens; ticking a row in it
  changes the cell figure behind it once closed.

## E. Occupied by another SPO (S5)

- **AC-E1** `[BE]` After container 1 creates an SPO covering a retail SO line in full, the
  suggestion for container 2 (same product) returns that line with `qty: 0`,
  `default_ticked: false`, `taken_qty` = the covered figure, `taken_by` = [SPO-1's number].
- **AC-E2** `[BE]` A retail line half covered returns `qty` = the rest and `taken_qty` =
  the covered half.
- **AC-E3** `[BE]` A project row linked to an SPO allocation elsewhere carries `taken_by`
  naming that SPO.
- **AC-E4** `[BE]` A PO line fully pulled by SPO-1 is returned in `po_takes` for a second
  shipment's planner with `qty: 0`, `open_qty: 0`, `taken_qty` = the pull, `taken_by` =
  [SPO-1's number]; `suggested_qty` for that line does not count it.
- **AC-E5** `[BE]` After `unwind` of SPO-1, the same rows return with `taken_qty: 0` and
  their full `qty`.
- **AC-E6** `[BE]` The route response carries `taken_qty` and `taken_by` on both lists
  (schema declared, asserted through the API).
- **AC-E7** `[FE]` A taken row renders grey, its checkbox disabled and unticked, a Taken
  column with the figure and the SPO number(s) under it; ticked / covered figures exclude it.
- **AC-E8** `[FE]` A schedule cell whose only quantity is taken renders `bg-muted` and
  `text-muted-foreground`; a mixed cell shows our tinted figure and a muted `+N on SPO-…`
  line.
- **AC-E9** `[E2E]` Create an SPO from a ZZT- draft shipment on :3160, open a second ZZT-
  draft for the same product, see the grey rows in the SO covered dialog and the grey cell
  in the schedule; delete the first SPO; the rows return.

## G. PO and SO after Create SPO (S7)

- **AC-G1** `[E2E]` After Create SPO on :3160, the source PO's detail shows the line with
  Outstanding reduced by the pull and a placement `SPO-… <qty>` naming the packing list.
- **AC-G2** `[BE]` A retail SO line covered by one SPO returns `linked_to` = one link with
  `kind: 'spo'`, `document` = the SPO number, `qty` = the covered quantity.
- **AC-G3** `[BE]` Covered by two containers = two links, in SPO number order.
- **AC-G4** `[BE]` After `unwind` of the SPO, the same line returns `linked_to: None`.
- **AC-G5** `[BE]` A line with an inquiry row keeps its OI links first and the SPO
  coverage entries after them.
- **AC-G6** `[BE]` The sales-order route carries the links (asserted through the API).
- **AC-G7** `[E2E]` The SCM sales order detail's Linked to cell prints `SPO-… <qty>` for
  the covered retail line.

## F. Regression (S6)

- **AC-F1** `[FE]` Full `npm run test` green; `npx tsc --noEmit` shows only the known
  pre-existing test-file errors.
- **AC-F2** `[BE]` `pytest tests/scm/test_spo_planner_selection.py tests/scm/test_spo_conversion.py tests/scm/test_container_request_drill.py` green.
- **AC-F3** `[E2E]` Evidence screenshots for AC-C6, AC-D4, AC-E9 attached to the PR.
