# PLAN: OI-SPLIT-CONFIRM-POLISH

Status: in review, PR #1820 (small fix track: UI polish, no migration, no auth/RBAC change)

Owner feedback (21 Oct 2026) on the guided Confirm dialog, step 1 "Review split":

1. Remove the row drag handle and drag-to-reorder (and the "Moved ... Undo" toast it raised).
2. Rename CHANGE QUANTITY -> BREAKDOWN QTY and CHANGE DATE -> BREAKDOWN DATE. QTY / NEW QTY /
   DELIVERY DATE / NEW DATE stay (they mirror the OI email).
3. The dialog opens clean: no Save/Undo, Next: Confirm enabled, no "Save or undo" warning until a
   real edit. Fix the dirty-on-open cause at the source.
4. Table columns resizable by dragging the header edge, reusing the app's existing pattern.

Tests (red first): no drag handle; renamed headers; opens clean; warning only after an edit;
columns resizable.

## Outcome

- Drag: `canDrag` prop on `LineSplitEditor` / `LineSplitSheet` (default on); the guide passes
  false. The board gear's "Split delivery" keeps drag.
- Headers: shared `COLUMNS` in `LineSplitSheet.tsx`, so the gear dialog and the read-only split
  popups read "Breakdown qty" / "Breakdown date" too.
- Dirty on open: the page already opened clean on SO426513-shaped data (vitest and browser); the
  owner's dirty state came from an accidental drag (5px mouse sensor) dropping 20 on the other
  C-FH14 line. Removing drag removes it; tests pin opens-clean and warning-only-after-an-edit.
- Resize: TanStack column sizing + `DataGridTableHeadRowCellResize`
  (`components/ui/data-grid-table.tsx`). REMARK is the flex column (min 100px once resized).

## Round 2 (owner, 21 Oct ~22:55, SO427002)

- SO DATE blank on first open: the guide's second, read-only sheet (covered lines the split read
  does not list) was drawn with no payload, so its rows had no SO date while the read had one.
  It now takes the order's read (`ConfirmGuideDialog.tsx`). The editor's own rows already follow
  the read, refetch included (vitest).
- Footer: Cancel far left; the step's action at the right (Next on Review split, "Confirm N
  orders" on Confirm) with Back immediately left of it. The Confirm button left the body.

## Round 3 (owner, 21 Oct ~23:25 to ~23:45, SO426939)

- Review split is ALWAYS the editable sheet (owner: "can I split for this scenario?"). When the
  guide opens, the board adopts every guide order that has no planning record through the
  existing idempotent `POST /fulfilment-planning/adopt` (a silent `ensure` mutation beside the
  board's `adopt`), every order tried, errors kept per order, then re-reads the board once for
  the mirror line ids; the adopt's own record id wins over the re-read, as the press already
  does. One run at a time (a reopened guide or a Retry joins the running one). While it runs a
  page is a skeleton with Next off; a failed order shows its own error and Retry above its
  read-only lines, and Next stays on so it never holds up the other orders (the press names
  it, as before).
- **Changed criterion (guide UAC A2):** "Cancel, Escape or close writes nothing" now reads
  "confirms and sends nothing". Opening the guide may write a planning record (one
  `project_sales_orders` row, its mirror lines and the usual audit row), which stays after
  Cancel. Adoption sends nothing: no email, no AutoCount write, no queue job.
- SO date: the board's `orders[]` carries `so_date` (core `sales_orders.order_date`, the same
  value as the split read's `so_date`). One helper in `ConfirmGuideDialog` (read's date, else
  the board's) feeds every sheet on the page.
- Owner ruling (~23:45): the phone (375) page header shows the same SO date, DD/MM/YYYY.
