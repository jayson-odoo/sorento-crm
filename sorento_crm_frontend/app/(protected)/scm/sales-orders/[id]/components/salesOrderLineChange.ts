import type { BoardChangeAnnotation } from '@/app/(protected)/project-sales/_shared/lib/boardChangeAnnotations';
import { whereItWentFrom } from '@/app/(protected)/project-sales/_shared/lib/boardChangeAnnotations';
import type { PlanningChangeKind } from '@/app/(protected)/project-sales/_shared/types/planningChange.types';
import type { SalesOrderLine } from '@/app/(protected)/scm/types/scm.types';

/**
 * The batch row behind one sales-order line, as the board's own What-changed dialog reads it.
 *
 * WHY THIS SCREEN AT ALL: once Apply has run on a CANCELLED line the line is closed, and a
 * closed line has no cell on the fulfilment board - so the dialog that says where its held
 * quantity went (`Reallocate 202607-S0080 3 to pool`) has nowhere left to open. The line is
 * still on this order, and this is where CS looks next, so the same reading is offered here.
 *
 * ITS OWN MODULE, beside `salesOrderLineDraft.ts` and for the same measured reason: a
 * `'use client'` component file that exports a value which is not a component drops out of
 * React Fast Refresh, and every edit to it then full-reloads the page and wipes the edit
 * session (13 September 2026).
 *
 * WHAT IT DOES NOT CLAIM: the line carries the batch row's IDENTITY and its RESULT, not its
 * `from`/`to` sides, so nothing here invents a Was or a Now. A cancelled row says the one
 * word the book actually said - `changedFieldsOf` prints "Cancelled" off `closed` alone - and
 * any other kind shows its result and the dialog's own "nothing moved" sentence rather than a
 * quantity this screen would have had to guess. `lineNo` is 0 because this grid has no line
 * numbers of its own; the dialog titles itself with the item code instead.
 */
export function lineChangeAnnotation(
  line: SalesOrderLine,
  soNumber: string,
): BoardChangeAnnotation | null {
  const change = line.planning_change;
  if (!change) return null;
  return {
    rowId: change.id,
    soNumber,
    lineNo: 0,
    itemCode: line.sku,
    kind: change.kind as PlanningChangeKind,
    closed: change.kind === 'cancelled',
    was: { qty: null, date: null, decision: null },
    now: { qty: null, date: null, decision: null },
    suggestionLines: [],
    lateDays: null,
    shortfallQty: null,
    productChangedFrom: null,
    movedTransfer: null,
    whereItWent: whereItWentFrom(change.result),
    projectLineId: null,
  };
}
