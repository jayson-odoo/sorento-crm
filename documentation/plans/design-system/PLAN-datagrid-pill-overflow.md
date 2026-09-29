# PLAN: DataGrid pill cells fold to one line with a "+N" popover

Status: PR #1377 merged (29 Sep 2026); follow-up lane PILL-OVERFLOW-2 in review (small fix track:
no migration, no auth change, reuse-only frontend diff). Archive on merge of the follow-up PR.
Lane: PILL-OVERFLOW (crew), branch `claude/datagrid-pill-overflow-31ss4p`, PR #1377
Follow-up lane: PILL-OVERFLOW-2 (crew), branch `crew/pill-overflow-2`
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
4. Sweep of other DataGrid list pages with wrapping pill/badge cells. Adopted `PillOverflow`
   (plain label lists): Users & Access > Roles, Permissions column (`role-list.tsx`);
   SCM > Simulation, Changed groups (`ScenariosGrid.tsx`); Dealer Kit > Tile designs, Shows
   (`TileDesignsList.tsx`). Portalled an existing one-off "+N" popover (same bug as the OI
   Lines cell): Drive access levels (`AccessLevelsCell.tsx`), SPO allocations containers
   (`SPOAllocationsList.tsx`), SCM sales orders delivery dates (`SalesOrdersGrid.tsx`).
   Follow-ups (cells that mix pills with icons, tooltips, links or remove buttons, so not the
   plain-label pattern): OI worklist Instruction cell (`orderInquiryWorklistColumns.tsx`),
   SCM product perspective Status (`ProductPerspectiveGrid.tsx`), PO intake Flag column
   (`POIntakeLinesGrid.tsx`), import field aliases (`ImportFieldAliasesList.tsx`).

## Follow-up lane PILL-OVERFLOW-2 (29 Sep 2026): the five spots #1377 listed, verified in code

Rule of the lane: REUSE `PillOverflow` only; a spot is skipped when it is not a label-only
pill list or when folding it would change behaviour beyond layout.

5. **Applied.** Sales > Sales Teams, Agents column (`SalesTeamsView.tsx`): the popover body
   was this list's own `<ul>` copy of the same markup; it now renders `PillOverflowList`, and
   the cell carries a `testId` so the fold is testable. No visual change.

Skipped, each with the reason read off the code:

1. OI worklist Instruction (`orderInquiryWorklistColumns.tsx`, the `verb` column): the verb
   pill (`OrderInquiryVerbPill`) and `ReservePill` paint `lib/status-pill.ts` palettes, not
   the six `PillTone`s; `ReservePill` carries a tick icon; the cell also holds the
   "Why this instruction" tooltip button and `DecisionTrailButton` (its own popover). Folding
   the two pills into `PillOverflow` would recolour them, drop the tick and make both pills
   open a popover they do not open today. At most two pills, so the fold buys nothing.
2. SCM product perspective Status (`ProductPerspectiveGrid.tsx`): `StateChip` is icon + label
   in the health palette (colour is never the sole signal there), `CommittedStockoutPill` is
   outlined with an icon and a title, the imbalance pill has an icon and a tooltip. None of
   the three is a plain label; `PillOverflow` pills have no icon slot.
3. PO intake Flag (`POIntakeLinesGrid.tsx`, `check` column): design-system `Badge` variants
   carry the meaning (`destructive` = does not multiply out, `secondary` = cancelled,
   `outline` = product state), the arithmetic badge carries the expected amount as a title,
   and `LineNotesIndicator` beside them is its own controlled popover with accept/reject.
   `PillOverflow` has no destructive or outline tone, so the fold would lose the variant
   semantics. If the owner wants this cell folded, the trigger is a `destructive` tone on
   `PillOverflow` (second case pays for the generalisation), not a lane-local copy.
4. Import field aliases (`ImportFieldAliasesList.tsx`): every badge carries its own remove
   (x) button that parks a deferred `import_field_alias.forget`, plus an optional supplier
   badge beside it. Every `PillOverflow` pill opens the shared popover, so a remove button
   cannot live on a pill; moving removal into the popover changes how a mapping is removed.

Known edge (from #1377), assessed and left: when pill 0 alone is wider than the column,
"+N" wraps under it. Inside the shared component the only fixes are to truncate pill 0
(breaks the fulfilment board rule "a quantity is never cut", the reason `flex-wrap` exists)
or to clip "+N" (hides the count). Neither is layout-only, so it stays as documented.

## Tests (vitest)

- `PillOverflow.test.tsx` already covers fit math, "+N" count, popover content, Enter/Space
  and Escape. Added: `user-list` Roles cell and `ContactsList` Access types cell render the
  shared row with "+N" and the popover lists every label.
- PILL-OVERFLOW-2: `SalesTeamsView.test.tsx` gains the "+N" case: the popover lists every
  agent one per line, leader first, and Escape closes it (AC-PO-7).

## Hand test

`laneboard/scripts/<PR>.md`, covering both People pages and the OI Lines SPO column.
