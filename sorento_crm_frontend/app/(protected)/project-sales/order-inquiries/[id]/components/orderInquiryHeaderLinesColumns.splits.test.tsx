/**
 * OI-LINE-SPLIT (UAC D3): the order inquiries Lines tab shows a split line as "Split N" and
 * its expanded content lists the splits read-only: Qty, Date (dd/mm/yyyy), Change, and the
 * line number it sits on (never an id). A sibling file to
 * `orderInquiryHeaderLinesColumns.test.tsx`, so that suite is untouched.
 *
 * The chip may live in any column; every cell is rendered and the text pooled.
 *
 * OI-SPLIT-VIEW (UAC B1) changes the rule: the chip is the shared `LineSplitInfo`, read off the
 * row's `split_view`, in its own "Split" column right after Product, and the Product cell no
 * longer carries it. The chip tests below are updated to that rule; the expand tests (the OI
 * chevron keeps what it shows today) are untouched.
 */
import React from 'react';
import { renderHook, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../../_shared/components/OrderInquiryStockGrid', () => ({
  OrderInquiryStockGrid: () => <div data-testid="stock-grid" />,
}));
vi.mock('@/app/(protected)/project-sales/_shared/components/SoLineAttachmentsButton', () => ({
  SoLineAttachmentsButton: () => null,
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

const SPLIT_VIEW = {
  status: 'confirmed',
  revision_no: 3,
  confirmed_on: '2026-10-19',
  base_qty: '10',
  base_date: '2026-11-02',
  now_qty: '10',
  now_date: '2026-11-02',
  total_qty: '10',
  rows: [
    { qty: '4', delivery_date: '2026-11-02', change: 'REMAIN', sits_on: 'own', sits_on_line_no: 10, remark: '', is_cancel: false, changed: false, was_qty: null, was_date: null },
    { qty: '4', delivery_date: '2026-11-09', change: 'DELAY', sits_on: 'line', sits_on_line_no: 20, remark: 'site not ready', is_cancel: false, changed: false, was_qty: null, was_date: null },
    { qty: '2', delivery_date: null, change: 'CANCEL BALANCE', sits_on: 'own', sits_on_line_no: 10, remark: '', is_cancel: true, changed: false, was_qty: null, was_date: null },
  ],
};

const SPLITS = [
  { id: 's1', qty: '4', delivery_date: '2026-11-02', is_cancel: false, change: 'REMAIN',
    sits_on_line_id: 'l10', sits_on_line_no: 10, remark: '' },
  { id: 's2', qty: '4', delivery_date: '2026-11-09', is_cancel: false, change: 'DELAY',
    sits_on_line_id: 'l20', sits_on_line_no: 20, remark: 'site not ready' },
  { id: 's3', qty: '2', delivery_date: null, is_cancel: true, change: 'CANCEL BALANCE',
    sits_on_line_id: 'l10', sits_on_line_no: 10, remark: '' },
];

function linesRow(overrides: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    item_code: 'CSK14B',
    product_id: 'p1',
    linked_qty: '0',
    bundled_qty: '0',
    splits: [],
    ...overrides,
  } as unknown as OrderInquiryWorklistRow;
}

function cellsText(row: OrderInquiryWorklistRow): string {
  const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
  let pooled = '';
  for (const column of result.current as unknown as Array<{
    cell?: (ctx: unknown) => React.ReactNode;
  }>) {
    if (typeof column.cell !== 'function') continue;
    try {
      const ctx = {
        row: { original: row, getIsExpanded: () => false, toggleExpanded() {} },
        getValue: () => undefined,
        column: {},
        table: {},
      };
      const { container, unmount } = render(<>{column.cell(ctx)}</>);
      pooled += ` ${container.textContent ?? ''}`;
      unmount();
    } catch {
      /* a cell that needs a fuller table context is not the one carrying the chip */
    }
  }
  return pooled;
}

function expandedFor(row: OrderInquiryWorklistRow) {
  const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
  const expand = (result.current as unknown as Array<{
    id?: string;
    meta?: { expandedContent?: (line: unknown) => React.ReactNode };
  }>).find((c) => typeof c.meta?.expandedContent === 'function');
  expect(expand).toBeDefined();
  return expand!.meta!.expandedContent!(row);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('OI Lines tab: splits (UAC D3)', () => {
  it('a split line carries a "Split 3" chip (from split_view, UAC B1)', () => {
    expect(
      cellsText(linesRow({ splits: SPLITS, split_view: SPLIT_VIEW, so_line_no: 10 })),
    ).toContain('Split 3');
  });

  it('an unsplit line carries no Split chip', () => {
    expect(cellsText(linesRow({ splits: [] }))).not.toMatch(/Split \d/);
  });

  it('the expanded content lists each split: qty, dd/mm/yyyy date, change word, and the line it sits on', () => {
    render(<>{expandedFor(linesRow({ splits: SPLITS }))}</>);
    const text = document.body.textContent ?? '';
    expect(text).toContain('02/11/2026');
    expect(text).toContain('09/11/2026');
    expect(text).toContain('REMAIN');
    expect(text).toContain('DELAY');
    expect(text).toContain('CANCEL BALANCE');
    expect(text).toMatch(/line 20/i);
    expect(text).toMatch(/line 10/i);
    expect(text).toContain('site not ready');
    expect(text).not.toMatch(/\bl10\b|\bl20\b/); // no ids on screen
    expect(text).not.toMatch(/tranche/i);
  });

  it('the expanded content of an unsplit line lists no splits', () => {
    render(<>{expandedFor(linesRow({ splits: [] }))}</>);
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/REMAIN|DELAY|CANCEL BALANCE/);
    expect(text).not.toMatch(/line \d+/i);
  });
});

/**
 * OI-SPLIT-VIEW (UAC B1): the "Split" column. Red until the column exists.
 */
type Col = {
  id?: string;
  accessorKey?: string;
  enableHiding?: boolean;
  meta?: { headerTitle?: string };
  cell?: (ctx: unknown) => React.ReactNode;
};

function columnsNow(): Col[] {
  const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
  return result.current as unknown as Col[];
}

function cellOf(column: Col, row: OrderInquiryWorklistRow) {
  const ctx = {
    row: { original: row, getIsExpanded: () => false, toggleExpanded() {} },
    getValue: () => undefined,
    column: {},
    table: {},
  };
  return render(<>{column.cell!(ctx)}</>);
}

describe('OI Lines tab: the Split column (UAC B1)', () => {
  it('is a column "Split" right after Product, on the Columns menu like the others', () => {
    const cols = columnsNow();
    const product = cols.findIndex((c) => c.accessorKey === 'item_code');
    expect(product).toBeGreaterThan(-1);
    const next = cols[product + 1];
    expect(next.id).toBe('split');
    expect(next.meta?.headerTitle).toBe('Split');
    expect(next.enableHiding).not.toBe(false);
  });

  it('its cell reads "Split 3" and offers "Show the splits of line 10"; an unsplit line shows nothing', () => {
    const split = columnsNow().find((c) => c.id === 'split')!;
    expect(split).toBeDefined();
    const first = cellOf(split, linesRow({ split_view: SPLIT_VIEW, splits: SPLITS, so_line_no: 10 }));
    expect(first.container.textContent).toContain('Split 3');
    expect(
      first.getByRole('button', { name: 'Show the splits of line 10' }),
    ).toBeInTheDocument();
    first.unmount();
    const plain = cellOf(split, linesRow({ split_view: null, splits: [] }));
    expect(plain.container.textContent ?? '').not.toMatch(/Split \d/);
    expect(plain.queryByRole('button', { name: /Show the splits/ })).toBeNull();
  });

  it('the Product cell shows the product only, never "Split N"', () => {
    const product = columnsNow().find((c) => c.accessorKey === 'item_code')!;
    const { container } = cellOf(
      product,
      linesRow({ split_view: SPLIT_VIEW, splits: SPLITS, so_line_no: 10 }),
    );
    expect(container.textContent).toContain('CSK14B');
    expect(container.textContent).not.toMatch(/Split \d/);
  });
});

describe('OI Split column sort value (review round 1, UAC B7a)', () => {
  it('is the chip N: the AutoCount extra row is not counted (752-like: 2, not 3)', () => {
    const split = columnsNow().find((c) => c.id === 'split') as unknown as {
      accessorFn?: (row: unknown, index: number) => unknown;
      enableSorting?: boolean;
    };
    const view = {
      ...SPLIT_VIEW,
      rows: [
        { ...SPLIT_VIEW.rows[0], sits_on: 'own' },
        { ...SPLIT_VIEW.rows[1], sits_on: 'new', sits_on_line_no: null },
        { ...SPLIT_VIEW.rows[0], qty: '145', change: 'ORDER 145', sits_on: 'extra' },
      ],
    };
    expect(split.accessorFn?.(linesRow({ split_view: view }), 0)).toBe(2);
    expect(split.enableSorting).not.toBe(false);
  });
});
