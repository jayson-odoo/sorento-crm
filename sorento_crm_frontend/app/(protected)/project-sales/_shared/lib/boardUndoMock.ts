/**
 * PHASE 1 MOCK (S0, #977) for the board's `undo` field on `BoardOrderStanding`.
 *
 * S1 (#978) makes the server send, on every order:
 *   undo: { revision_no: number, confirmed_at: string, confirmed_by_name: string,
 *           refusal: 'manual_link' | 'actioned' | null } | null
 * null when the order has no active decision, or its active decision's `undo_journal` is
 * NULL (a pre-lane revision, or one minted by `uncover_lines` rather than the board's own
 * confirm routes - PLAN-board-undo-last-confirm.md, "Undoable"). `refusal` is set when
 * purchasing has already linked a PO line by hand or marked a row actioned since the confirm
 * (R1); the gear still lists the entry, disabled, with the reason as its `title`.
 *
 * That field does not exist on the server yet, so this file overlays a deterministic `undo`
 * onto whatever orders the REAL board query returns - cycling undoable / refused / nothing to
 * undo across the board's own order list, so the gear menu (AC-UC-01..04) can be built and
 * verified in a browser against a live board everywhere else. `committedOrderIds` takes an
 * order back to "nothing to undo" once `useMockUndoAction`'s local countdown has lapsed for
 * it - the closest a Phase 1 mock gets to AC-UC-07's "the gear entry for that order is gone"
 * without a real replay, which is S2's (#979) job.
 *
 * Delete this file and its one call site in `FulfilmentBoardPanel.tsx` once S1 lands; the
 * panel then reads `order.undo` straight off the board response.
 */

import type { BoardOrderStanding, BoardUndo, BoardUndoRefusal } from '../types/fulfilmentPlanning.types';

const REFUSAL_TITLES: Record<NonNullable<BoardUndoRefusal>, string> = {
  manual_link: 'Purchasing linked a PO line',
  actioned: 'Purchasing marked a row actioned',
};

/** The tooltip a disabled gear entry carries (AC-UC-03). Undefined when nothing blocks it. */
export function undoRefusalTitle(refusal: BoardUndoRefusal | undefined): string | undefined {
  return refusal ? REFUSAL_TITLES[refusal] : undefined;
}

/**
 * Overlay a mocked `undo` onto the board's own orders, in the board's own order.
 *
 * Cycles every three orders: undoable, refused, nothing to undo - so a board of three or more
 * orders demonstrates every gear state (AC-UC-02, AC-UC-03, AC-UC-04) without inventing rows
 * the real board did not return. An order with no `project_sales_order_id` (not yet adopted)
 * carries no mocked `undo` either: the real endpoint has no decision to look up without one.
 */
export function withMockUndo(
  orders: BoardOrderStanding[],
  committedOrderIds: ReadonlySet<string>,
): BoardOrderStanding[] {
  // Counted over ADOPTED orders only, not the array position: a board most often carries
  // one or two orders with a planning record among several without one yet, and cycling by
  // raw index left the states bunched on whichever position happened to be adopted rather
  // than demonstrating undoable / refused / nothing across the orders that could plausibly
  // carry a mocked `undo` at all.
  let adoptedIndex = 0;
  return orders.map((order) => {
    if (!order.project_sales_order_id || committedOrderIds.has(order.project_sales_order_id)) {
      return { ...order, undo: null };
    }
    const pattern = adoptedIndex % 3;
    adoptedIndex += 1;
    if (pattern === 2) return { ...order, undo: null };
    const undo: BoardUndo = {
      revision_no: 1,
      confirmed_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      confirmed_by_name: 'CS Planner',
      refusal: pattern === 1 ? 'manual_link' : null,
    };
    return { ...order, undo };
  });
}
