/**
 * QUOTE-CUSTOMER-AMEND, staff side: the Lines grid's review mode (AC-QCA-26 to AC-QCA-29).
 *
 * Written BEFORE the `review` prop exists (Phase 2, test-first). The customer's suggestions are
 * decided on the quotation's own line grid: each one sits in the cell it concerns (Qty, Rate), the
 * issued value struck through, the suggested value, and Accept / Reject right there. No Decision
 * column, no new tab.
 *
 * The grid is rendered in view mode (editing=false) with invented lines, because review is a read
 * of what the customer holds. The row ids and the `QuotationAmendmentRow` shape come from the
 * plan's API contract.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  QuotationAmendmentRow,
  QuotationLine,
  StagedQuotationLine,
} from '../../_shared/types/project.types';
import { serverToDraft } from './quotationLineDraft';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

// The cells that fetch on their own (photos, stock) are not what is under test.
vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/hooks/useProjects')>();
  return {
    ...actual,
    useQuotationLineImages: () => ({ data: undefined, isLoading: false, isError: false }),
    useProductSetLineRef: () => ({ data: undefined, isLoading: false, isError: false }),
  };
});
vi.mock('./QuotationStockChip', () => ({
  QuotationStockChip: () => null,
  SetStockChip: () => null,
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { QuotationLinesGrid } from './QuotationLinesGrid';

// ------------------------------------------------------------------ fixtures (all invented)

function line(overrides: Partial<QuotationLine>): QuotationLine {
  return {
    id: 'l1',
    version_id: 'v1',
    // A catalogue line: the grid prints the code in view mode only for a line with a product.
    product_id: 'p-fake',
    product_code: 'ZZT-WC-1001',
    description: 'One-piece WC',
    unit_price: '400.00',
    quantity: '120.00',
    uom: 'PCS',
    line_total: '48000.00',
    is_non_standard: false,
    is_below_floor: false,
    sort_order: 0,
    ...overrides,
  };
}

const LINES: QuotationLine[] = [
  line({ id: 'l1', product_code: 'ZZT-WC-1001', sort_order: 0 }),
  line({
    id: 'l2',
    product_code: 'ZZT-BSN-4004',
    description: 'Basin',
    unit_price: '160.00',
    line_total: '19200.00',
    sort_order: 1,
  }),
  line({
    id: 'l3',
    product_code: 'ZZT-SHW-5005',
    description: 'Shower head',
    unit_price: '25.00',
    quantity: '10.00',
    line_total: '250.00',
    sort_order: 2,
  }),
  line({
    id: 'l4',
    product_code: 'ZZT-CON-0001',
    description: 'Connector',
    unit_price: '0.00',
    line_total: '0.00',
    sort_order: 3,
  }),
];

function staged(source: QuotationLine): StagedQuotationLine {
  return { id: source.id, key: source.id, line: source, draft: serverToDraft(source), removed: false };
}

function row(overrides: Partial<QuotationAmendmentRow>): QuotationAmendmentRow {
  return {
    id: 'r?',
    line_id: 'l1',
    field: 'quantity',
    value_from: '120.00',
    value_to: '110.00',
    decision: 'pending',
    decision_reason: null,
    ...overrides,
  };
}

const ROWS: QuotationAmendmentRow[] = [
  row({ id: 'r-wc-qty', line_id: 'l1', field: 'quantity', value_from: '120.00', value_to: '110.00' }),
  row({
    id: 'r-wc-price',
    line_id: 'l1',
    field: 'unit_price',
    value_from: '400.00',
    value_to: '380.00',
    below_floor: true,
    floor_value: '390.00',
  }),
  row({
    id: 'r-bsn-price',
    line_id: 'l2',
    field: 'unit_price',
    value_from: '160.00',
    value_to: '150.00',
    below_floor: false,
    floor_value: '130.00',
  }),
  row({ id: 'r-shw-remove', line_id: 'l3', field: 'remove', value_from: null, value_to: null }),
];

const onDecide = vi.fn();

function renderGrid(review?: { rows: QuotationAmendmentRow[]; disabled?: boolean }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationLinesGrid
        lines={LINES.map(staged)}
        editing={false}
        quotationId="q1"
        emptyHint="No lines yet."
        filterEmptyHint="No line matches."
        fetchProducts={async () => []}
        resolveProduct={() => undefined}
        productCodeOf={() => null}
        fillFromProduct={() => ({})}
        uomOptions={[]}
        uomError={null}
        onUomRetry={() => {}}
        brandOptions={[]}
        review={review ? { ...review, onDecide } : undefined}
      />
    </QueryClientProvider>,
  );
}

/** The table row that shows this line (the Product cell prints the stored code). */
function rowOf(code: string): HTMLElement {
  const cell = screen.getAllByText(code)[0];
  const tr = cell.closest('tr');
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr as HTMLElement;
}

/** The cell a labelled control sits in. */
function cellOf(name: string): HTMLElement {
  const td = screen.getByRole('button', { name }).closest('td');
  if (!td) throw new Error(`"${name}" is not inside a table cell`);
  return td as HTMLElement;
}

function struckTexts(cell: HTMLElement): string[] {
  return Array.from(cell.querySelectorAll('s, del, strike, .line-through')).map(
    (el) => el.textContent ?? '',
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

// ------------------------------------------------------------------ AC-QCA-26

describe('AC-QCA-26: the grid keeps its own columns', () => {
  it('shows the ten columns, no Decision column, no tabs, and the review controls', () => {
    renderGrid({ rows: ROWS });

    const headers = screen.getAllByRole('columnheader').map((h) => (h.textContent ?? '').trim());
    for (const wanted of [
      /^#/,
      /Photo/,
      /Drawing/,
      /Product/,
      /Description/,
      /Brand/,
      /Qty/,
      /UOM/,
      /Rate \(RM\)/,
      /Total \(RM\)/,
    ]) {
      expect(headers.some((text) => wanted.test(text)), `column ${wanted}`).toBe(true);
    }
    expect(headers.some((text) => /decision|suggest/i.test(text))).toBe(false);
    expect(screen.queryByRole('tablist')).toBeNull();

    // And the review really is on (otherwise the assertions above would hold with no feature).
    expect(
      screen.getByRole('button', { name: 'Accept suggested quantity on ZZT-WC-1001' }),
    ).toBeTruthy();
  });

  it('draws nothing extra when no review is passed', () => {
    renderGrid(undefined);
    expect(screen.queryByRole('button', { name: /^Accept /i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Reject /i })).toBeNull();
  });
});

// ------------------------------------------------------------------ AC-QCA-27

describe('AC-QCA-27: a suggestion sits in the cell it concerns', () => {
  it('puts a quantity suggestion in the Qty cell: issued struck through, suggested, Accept, Reject', () => {
    renderGrid({ rows: ROWS });

    const accept = 'Accept suggested quantity on ZZT-WC-1001';
    const reject = 'Reject suggested quantity on ZZT-WC-1001';
    const qtyCell = cellOf(accept);
    expect(within(qtyCell).getByRole('button', { name: reject })).toBeTruthy();
    expect(struckTexts(qtyCell).join(' ')).toMatch(/120/);
    expect(qtyCell.textContent).toMatch(/110/);

    // The same row's Rate suggestion lives in a different cell.
    const rateCell = cellOf('Accept suggested unit price on ZZT-WC-1001');
    expect(rateCell).not.toBe(qtyCell);
    expect(rowOf('ZZT-WC-1001').contains(qtyCell)).toBe(true);
    expect(rowOf('ZZT-WC-1001').contains(rateCell)).toBe(true);
  });

  it('puts a price suggestion in the Rate cell: issued struck through, suggested, Accept, Reject', () => {
    renderGrid({ rows: ROWS });

    const rateCell = cellOf('Accept suggested unit price on ZZT-BSN-4004');
    expect(
      within(rateCell).getByRole('button', { name: 'Reject suggested unit price on ZZT-BSN-4004' }),
    ).toBeTruthy();
    expect(struckTexts(rateCell).join(' ')).toMatch(/160\.00/);
    expect(rateCell.textContent).toMatch(/150\.00/);
  });

  it('puts a removal in the row-actions cell, the last one of its row', () => {
    renderGrid({ rows: ROWS });

    const actions = cellOf('Accept removal of ZZT-SHW-5005');
    expect(
      within(actions).getByRole('button', { name: 'Reject removal of ZZT-SHW-5005' }),
    ).toBeTruthy();
    const cells = Array.from(rowOf('ZZT-SHW-5005').querySelectorAll('td'));
    expect(cells[cells.length - 1]).toBe(actions);
  });

  it('offers nothing on a line the customer did not touch', () => {
    renderGrid({ rows: ROWS });
    for (const name of [
      /on ZZT-CON-0001/,
      /removal of ZZT-CON-0001/,
    ]) {
      expect(screen.queryByRole('button', { name: new RegExp(`^(Accept|Reject) .*${name.source}`) })).toBeNull();
    }
    // The quantity of the basin and the price of the shower head were not suggested either.
    expect(screen.queryByRole('button', { name: /suggested quantity on ZZT-BSN-4004/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /suggested unit price on ZZT-SHW-5005/ })).toBeNull();
  });

  it('turns the controls off while a decision is being saved', () => {
    renderGrid({ rows: ROWS, disabled: true });
    const accept = screen.getByRole('button', {
      name: 'Accept suggested quantity on ZZT-WC-1001',
    }) as HTMLButtonElement;
    expect(accept.disabled).toBe(true);
  });
});

// ------------------------------------------------------------------ AC-QCA-28

describe('AC-QCA-28: a below-floor price says so in its Rate cell', () => {
  it('shows "Minimum price RM {floor}" for a suggestion under the floor only', () => {
    renderGrid({ rows: ROWS });

    const below = cellOf('Accept suggested unit price on ZZT-WC-1001');
    expect(below.textContent).toMatch(/Minimum price\s*RM\s*390\.00/);

    const clear = cellOf('Accept suggested unit price on ZZT-BSN-4004');
    expect(clear.textContent).not.toMatch(/Minimum price/);
  });
});

// ------------------------------------------------------------------ AC-QCA-29

describe('AC-QCA-29: Accept and Reject send the decision', () => {
  it('Accept calls the handler with the row id and "accepted"', async () => {
    renderGrid({ rows: ROWS });
    await userEvent.click(
      screen.getByRole('button', { name: 'Accept suggested quantity on ZZT-WC-1001' }),
    );

    expect(onDecide).toHaveBeenCalledTimes(1);
    const [rowId, decision, reason] = onDecide.mock.calls[0];
    expect([rowId, decision]).toEqual(['r-wc-qty', 'accepted']);
    expect(reason ?? undefined).toBeUndefined();
  });

  it('Accept works the same on a removal', async () => {
    renderGrid({ rows: ROWS });
    await userEvent.click(screen.getByRole('button', { name: 'Accept removal of ZZT-SHW-5005' }));
    expect(onDecide.mock.calls[0].slice(0, 2)).toEqual(['r-shw-remove', 'accepted']);
  });

  it('Reject opens a reason input in the same cell and sends "rejected" with the typed reason', async () => {
    renderGrid({ rows: ROWS });
    const name = 'Reject suggested unit price on ZZT-BSN-4004';
    const cell = cellOf(name);

    expect(within(cell).queryByRole('textbox')).toBeNull();
    await userEvent.click(within(cell).getByRole('button', { name }));

    const input = within(cell).getByRole('textbox');
    expect(onDecide).not.toHaveBeenCalled();

    await userEvent.type(input, 'Already at project price');
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(onDecide.mock.calls[0]).toEqual([
      'r-bsn-price',
      'rejected',
      'Already at project price',
    ]);
  });
});
