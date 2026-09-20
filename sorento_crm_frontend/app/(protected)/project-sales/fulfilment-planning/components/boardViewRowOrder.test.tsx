/**
 * The grid and the list put the products in the SAME order.
 *
 * They are two readings of one payload, and the whole point of the toggle is to look at the
 * same work another way. The grid's vertical axis is the payload's `productRows`; the list was
 * handed `contributions` in the order the demand query happened to return them, so a product
 * sitting third on the grid could sit first in the list and finding a line again meant
 * re-searching for it.
 *
 * One ordering, `orderByProductRows`, consumed by both. Asserted by rendering BOTH views off
 * ONE fixture and comparing the product sequence they print - not by unit-testing the
 * comparator alone, because the defect was that one of the two views did not use it.
 *
 * SUPERSEDED for the LIST view only (owner ruling, S4, PLAN-so-lines-autocount-order.md,
 * fix round #1076): the grid's axis is UNCHANGED (still `orderByProductRows`, still tested
 * above), but the list now sorts by sales order then AutoCount line number instead of
 * following the product axis - see the `orderListRows` describe block at the foot of this
 * file (AC-S4-1). The tests above still hold exactly as written: they exercise the
 * comparator and the list COMPONENT's own "renders whatever order it is given" behaviour,
 * neither of which changed: what changed is which comparator `FulfilmentBoardPanel.tsx`
 * calls before handing the list its `contributions` prop, which this file does not
 * exercise (it builds `listContributions` itself rather than rendering the panel). None of
 * the existing tests needed their own assertions changed for that reason.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { orderByProductRows, orderListRows } from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardContribution,
  BoardDateBucket,
  BoardProductRow,
} from '../../_shared/types/fulfilmentPlanning.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { FulfilmentBoardListView } from './FulfilmentBoardListView';
import { FulfilmentBoardMatrix } from './FulfilmentBoardMatrix';

/** The board's own axis, in the order the server sent it. */
const PRODUCT_ROWS: BoardProductRow[] = [
  { item_code: 'CB2805A-DIY', description: null },
  { item_code: 'A1010-NL', description: null },
  { item_code: 'B2155-NL-BLUE', description: null },
];

const BUCKET: BoardDateBucket = {
  key: '2026-09-01',
  kind: 'dated',
  label: 'Sep 2026',
  start: '2026-09-01',
  is_past: false,
};

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
 * The payload as the server actually sends it: the axis in ITS order, the lines in the demand
 * query's - which is a different one. A fixture where the two already agree could not fail.
 */
const CONTRIBUTIONS: BoardContribution[] = [
  contribution('B2155-NL-BLUE'),
  contribution('CB2805A-DIY'),
  contribution('A1010-NL'),
];

/** The products the grid prints down its first column, top to bottom. */
function matrixProducts(): string[] {
  const table = screen.getByRole('table');
  return within(table)
    .getAllByRole('rowheader')
    .map((cell) => cell.textContent ?? '');
}

/** The products the list prints down its Product column, top to bottom. */
function listProducts(): string[] {
  const table = screen.getByRole('table');
  return within(table)
    .getAllByRole('row')
    .slice(1) // the header row
    .map((row) => within(row).getAllByRole('cell')[PRODUCT_CELL]?.textContent ?? '');
}

/**
 * Select, Sales order, Agent, Customer, PRODUCT, ... - the list's column order. D14 (quick
 * save as suggested) added the select checkbox as the first column, which moved every cell
 * one to the right of what this test used to read.
 */
const PRODUCT_CELL = 4;

describe('the grid and the list agree about the product order', () => {
  it('the list follows the board axis, not the order the lines arrived in', () => {
    const ordered = orderByProductRows(CONTRIBUTIONS, PRODUCT_ROWS);

    expect(ordered.map((row) => row.item_code)).toEqual([
      'CB2805A-DIY',
      'A1010-NL',
      'B2155-NL-BLUE',
    ]);
  });

  it('renders the same sequence in both views off one payload', () => {
    const ordered = orderByProductRows(CONTRIBUTIONS, PRODUCT_ROWS);

    const grid = render(
      <FulfilmentBoardMatrix
        dateBuckets={[BUCKET]}
        rows={PRODUCT_ROWS.map((row) => ({ key: row.item_code, label: row.item_code }))}
        rowHeader="Product"
        cells={[]}
        draft={{}}
        onOpenCell={() => {}}
        onDecideMany={vi.fn()}
        onUndoMany={vi.fn()}
      />,
    );
    const gridSequence = matrixProducts();
    grid.unmount();

    render(
      <FulfilmentBoardListView
        contributions={ordered}
        draft={{}}
        onDecide={vi.fn()}
        onDecideMany={vi.fn()}
      />,
    );
    const listSequence = listProducts();

    expect(gridSequence).toEqual(['CB2805A-DIY', 'A1010-NL', 'B2155-NL-BLUE']);
    expect(listSequence).toEqual(gridSequence);
  });

  it('keeps a product the axis does not name, at the end rather than dropped', () => {
    // The list is the overview of the WHOLE selection and the grid may be windowed, so a line
    // the axis has no row for is a real case - and losing it silently would be the worst
    // possible reading of "one ordering".
    const ordered = orderByProductRows(
      [...CONTRIBUTIONS, contribution('ZZZ-OFF-AXIS')],
      PRODUCT_ROWS,
    );

    expect(ordered.map((row) => row.item_code)).toEqual([
      'CB2805A-DIY',
      'A1010-NL',
      'B2155-NL-BLUE',
      'ZZZ-OFF-AXIS',
    ]);
  });

  it('orders a product own lines by date, then order, then line number', () => {
    const ordered = orderByProductRows(
      [
        contribution('A1010-NL', { key: 'c', required_date: '2026-09-04', so_number: 'SO2', line_no: 1 }),
        contribution('A1010-NL', { key: 'd', required_date: null, so_number: 'SO1', line_no: 1 }),
        contribution('A1010-NL', { key: 'a', required_date: '2026-08-01', so_number: 'SO1', line_no: 2 }),
        contribution('A1010-NL', { key: 'b', required_date: '2026-09-04', so_number: 'SO1', line_no: 3 }),
      ],
      PRODUCT_ROWS,
    );

    // Undated last, the same rule every other listing in this product follows.
    expect(ordered.map((row) => row.key)).toEqual(['a', 'b', 'c', 'd']);
  });
});

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

    // Numeric, never lexicographic (2 before 10, the same trap `orderByProductRows`'s own
    // date/order tie-break avoids elsewhere in this file) - and the two un-numbered lines
    // of SO-A resolve by item_code (A before B) since neither carries a line_no to decide
    // with, THEN by `required_date` only where item_code also ties (not exercised by this
    // fixture: both un-numbered lines here are different products).
    expect(ordered.map((row) => row.key)).toEqual([
      'a-2',
      'a-10',
      'a-null-a',
      'a-null-b',
      'b-1',
    ]);
  });

  it('gives the same order whatever the productRows argument would have been, since there is none', () => {
    // `orderByProductRows` reads a second argument the grid's axis is built from; this
    // function takes none, so a caller cannot accidentally influence it by passing the
    // grid's own row order - the ordering is closed over `contributions` alone.
    expect(orderListRows.length).toBe(1);
  });
});
