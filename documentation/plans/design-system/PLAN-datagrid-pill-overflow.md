# PLAN: DataGrid pill cells fold to one line with a "+N" popover

Status: in progress (small fix track: no migration, no auth change, reuse-only frontend diff)
Lane: PILL-OVERFLOW (crew), branch `claude/datagrid-pill-overflow-31ss4p`
Owner rule (29 Sep 2026, system design principle): every DataGrid row is ONE line. A cell
with several pills shows as many as fit on one line (at least the first), then a "+N" chip;
clicking "+N" opens a popover listing the pills.

## What already exists (read before designing)

- `components/common/PillOverflow.tsx` is the shared pattern: measures the container with a
  `ResizeObserver`, shows as many pills as fit, folds the rest into "+N", opens ONE popover
  (via `PopoverPortal`, so it renders at the document root with `z-50` and collision padding)
  listing every item, keyboard reachable (Enter/Space open, Escape closes). It is already
  adopted by Sales Teams, Sales Targets and the fulfilment board.
- The Order Inquiry detail Lines tab PO/SPO cell (`orderInquiryHeaderLinesColumns.tsx`,
  `LineDocumentsCell`) is a one-off: first document link + a "+N" button with a NON-portalled
  `PopoverContent`. The popover therefore paints inside the table and the next row's own
  chip shows through it (the owner's screenshot). The first pill there is a document link that
  opens the document dialog, so it cannot be folded into `PillOverflow` (whose every pill opens
  the same popover); it keeps its own popover and gains `PopoverPortal`.

## Change

1. Users & Access > People > Administrative Users, Roles column (`user-list.tsx`): the
   wrapping `Badge` row becomes `PillOverflow` (neutral tone) with the popover listing every
   role.
2. Users & Access > People > Internal Users, Access types column (`ContactsList.tsx`): same.
3. OI Lines tab PO/SPO "+N" popover (`orderInquiryHeaderLinesColumns.tsx`): wrap the content
   in `PopoverPortal` and add `collisionPadding`, so it renders on top of the list.
4. Sweep of other DataGrid list pages with wrapping pill/badge cells: fixed where the cell is
   a plain list of labels (same pattern), listed as follow-ups otherwise. The list is in the
   PR body.

## Tests (vitest)

- `PillOverflow.test.tsx` already covers fit math, "+N" count, popover content, Enter/Space
  and Escape. Added: `user-list` Roles cell and `ContactsList` Access types cell render the
  shared row with "+N" and the popover lists every label.

## Hand test

`laneboard/scripts/<PR>.md`, covering both People pages and the OI Lines SPO column.
