/**
 * `orderListRows`: the LIST view's own row order (S4, PLAN-so-lines-autocount-order.md, fix
 * round #1076, owner ruling 21 Sep 2026) - sales order, then the line number AutoCount
 * itself sent.
 *
 * This file used to also exercise `orderByProductRows` (the grid's product-axis ordering
 * that the list borrowed before S4) both as a bare comparator and by rendering the grid and
 * the list off one fixture and comparing the sequences they printed. That coverage is
 * retired along with the function itself (S4 fix round review: `orderByProductRows` had no
 * production caller left once the list moved to `orderListRows` below - the grid's own axis
 * is `boardAxis` over `board.data.productRows` directly, and was never built from it
 * either). The guard that coverage gave - a panel that regressed to the product axis would
 * be caught - now lives at the PANEL level instead of the unit level:
 * `FulfilmentBoardPanel.test.tsx`'s "AC-S4-1 (panel)" describe block renders the real panel
 * in List view against a product axis that disagrees with (so_number, line_no), which is
 * exactly the shape a reversion to `orderByProductRows` would get wrong.
 */
import { describe, expect, it } from 'vitest';
import { orderListRows } from '../../_shared/lib/fulfilmentBoard';
import type { BoardContribution } from '../../_shared/types/fulfilmentPlanning.types';

function contribution(
  itemCode: string,
  overrides: Partial<BoardContribution> = {},
): BoardContribution {
  return {
    key: `${itemCode}:10`,
    sales_order_id: 'so-1',
    line_id: `core-${itemCode}`,
    product_id: `prod-${itemCode}`,
    so_number: 'SO397450',
    customer_name: 'Tuju Residences Sdn Bhd',
    agent_code: 'JEREMY',
    agent_label: 'Jeremy Lee',
    project_label: 'Tuju Residences',
    line_no: 10,
    item_code: itemCode,
    qty: '5',
    qty_outstanding: '5',
    required_date: '2026-09-04',
    unplannable: false,
    rank_score: 0.5,
    rank_factors: [],
    sources: [{ kind: 'buy', qty: '5', reason: 'Nothing free at any location.' }],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...overrides,
  };
}

/**
 * S4 (owner ruling, fix round #1076): the LIST view reads AutoCount order - sales order,
 * then the line number AutoCount itself sent - not the grid's product axis. The two views
 * now legitimately disagree about sequence, the same way the grid and the Lines tab on a
 * sales order detail page already do (PLAN-so-lines-autocount-order.md 3.5): a planner
 * comparing the list against the source document reads it top to bottom the way AutoCount
 * does, and the grid keeps its own product-by-product axis for the cross-order view.
 *
 * `orderListRows` takes contributions ALONE - no `productRows` argument - because the
 * product axis plays no part in this ordering at all; note for the coder implementing
 * this: if the extracted function ends up named or shaped differently, this test's import
 * is the one line that needs to move with it.
 */
describe('orderListRows (S4): the list sorts by sales order then AutoCount line number', () => {
  it('AC-S4-1: so_number asc, then line_no asc (null/undefined LAST), then item_code', () => {
    const ordered = orderListRows([
      contribution('Z', { key: 'b-1', so_number: 'SO-B', line_no: 1 }),
      contribution('A', { key: 'a-10', so_number: 'SO-A', line_no: 10 }),
      contribution('Q', { key: 'a-2', so_number: 'SO-A', line_no: 2 }),
      contribution('B', {
        key: 'a-null-b',
        so_number: 'SO-A',
        line_no: undefined as unknown as number,
      }),
      contribution('A', {
        key: 'a-null-a',
        so_number: 'SO-A',
        line_no: undefined as unknown as number,
      }),
    ]);

    // Numeric, never lexicographic (2 before 10) - and the two un-numbered lines of SO-A
    // resolve by item_code (A before B) since neither carries a line_no to decide with,
    // THEN by `required_date` only where item_code also ties (not exercised by this
    // fixture: both un-numbered lines here are different products).
    expect(ordered.map((row) => row.key)).toEqual([
      'a-2',
      'a-10',
      'a-null-a',
      'a-null-b',
      'b-1',
    ]);
  });
});
