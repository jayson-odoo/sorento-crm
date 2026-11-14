/**
 * SPARE-PART-OR-B (slice 2 of #2381), red-first (Phase 2). The spare part Lines columns.
 * Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md
 * U1.1 - U1.6, U3.2, U3.3, U3.5, U4.1, U4.7.
 *
 * NAMED CONTRACT CHOICES (the UAC leaves the prop shape open):
 * 1. `useOrderInquiryHeaderLinesColumns` takes `sparePartView?: 'request' | 'inquiry'` beside
 *    `inquiryType: 'spare_part_request'`. 'request' = the OR page (SparePartRequestRecord),
 *    'inquiry' = the OI page (OrderInquiryDetail). Default 'inquiry' (the OI page's existing
 *    call). `OrderInquiryLinesTab` threads it from `sparePart.view` (see
 *    SparePartRequestRecord.orB.test.tsx).
 * 2. The worklist row carries `oi_no` (its header's OI number, null before final approval)
 *    beside `inquiry_no` (the OR- number) and `order_inquiry_id`.
 * 3. The History button keeps aria-label "History" and carries `data-changed="true|false"`.
 *    OR view: true when qty != submitted_qty, unit_price != submitted_unit_price, or
 *    photo_changes added + removed > 0 (U1.3). OI view: true only when the row has
 *    `previous_qty` (a post-approval change, U4.7).
 * 4. Columns are found by `meta.headerTitle`: "OI" (OR view, after State). Lead ruling 14 Nov
 *    (U3.3 updated): no per-line "Order request" column; the OI page header links back.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, getExpandedRowModel, useReactTable } from '@tanstack/react-table';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return { ...actual, getOrderInquiryPoDetail: vi.fn(), getOrderInquirySpoDetail: vi.fn() };
});
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import { foldInquiryLines, toLineRows } from '../../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

beforeEach(() => vi.clearAllMocks());

type Options = Record<string, unknown>;

function titleOf(column: unknown): string | undefined {
  return (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;
}

function spareRow(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    order_inquiry_id: 'oi-1',
    inquiry_no: 'OR-2611-0003',
    oi_no: 'OI-2611-0009',
    inquiry_type: 'spare_part_request',
    verb: 'REPLENISH',
    state: 'raised',
    ack_state: 'awaiting',
    item_code: 'ZZX-SEAL-40',
    product_id: 'prod-1',
    stock_location: 'WH-A',
    qty: '8',
    unit_price: '25.0000',
    line_total: '200.0000',
    submitted_qty: '10',
    submitted_unit_price: '30.0000',
    photo_changes: { added: 0, removed: 0 },
    previous_qty: null,
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

const UNCHANGED = { qty: '10', submitted_qty: '10', unit_price: '25.0000', submitted_unit_price: '25.0000', line_total: '250.0000' };

const OR_PENDING: Options = {
  inquiryType: 'spare_part_request',
  sparePartView: 'request',
  headerState: 'pending_approval',
  canDecide: true,
  onEditLine: vi.fn(),
  currency: 'MYR',
};
const OR_RAISED: Options = {
  inquiryType: 'spare_part_request',
  sparePartView: 'request',
  headerState: 'raised',
  canDecide: false,
  currency: 'MYR',
};
const OI_RAISED: Options = {
  inquiryType: 'spare_part_request',
  sparePartView: 'inquiry',
  headerState: 'raised',
  canDecide: false,
  currency: 'MYR',
};

const VIEWS: Array<[string, Options, Record<string, unknown>]> = [
  ['OR page, approver, pending', OR_PENDING, { state: 'draft' }],
  ['OR page, reader, raised', OR_RAISED, {}],
  ['OI page, purchasing, raised', OI_RAISED, {}],
];

const rowClick = vi.fn();

function Grid({ rows, options }: { rows: OrderInquiryWorklistRow[]; options: Options }) {
  const columns = useOrderInquiryHeaderLinesColumns(options as never);
  const data = React.useMemo(() => toLineRows(foldInquiryLines(rows)), [rows]);
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowCanExpand: () => true,
    enableRowSelection: true,
  });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr
            key={row.id}
            data-testid="line"
            data-selected={String(row.getIsSelected())}
            data-expanded={String(row.getIsExpanded())}
            onClick={() => {
              rowClick();
              row.toggleSelected();
            }}
          >
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} data-title={titleOf(cell.column.columnDef) ?? cell.column.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderGrid(rows: OrderInquiryWorklistRow[], options: Options) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Grid rows={rows} options={options} />
    </QueryClientProvider>,
  );
}

function cell(title: string): HTMLElement {
  const found = screen.getByTestId('line').querySelector(`td[data-title="${title}"]`);
  expect(found, `a "${title}" cell`).not.toBeNull();
  return found as HTMLElement;
}

function columnsOf(options: Options) {
  const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns(options as never));
  return result.current;
}

// =============================================================================
// U1.1 - no "was" on a spare part line, any state, any viewer
// =============================================================================

describe('U1.1: no "was" text in the Qty or Unit price cell', () => {
  it.each(VIEWS)('%s', (_who, options, over) => {
    renderGrid([spareRow(over)], options);
    for (const title of ['Qty', 'Unit price']) {
      const text = cell(title).textContent ?? '';
      expect(text, `${title} cell reads "${text}"`).not.toMatch(/(^|\s)was /i);
      const marks = within(cell(title)).queryAllByText(/^was /i);
      expect(marks).toHaveLength(0);
    }
  });
});

// =============================================================================
// U1.2 / U1.5 - one History button, inside the Qty cell, on one line
// =============================================================================

describe('U1.2: exactly one History button per spare part line, in the Qty cell', () => {
  it.each(VIEWS)('%s', (_who, options, over) => {
    renderGrid([spareRow(over)], options);
    const line = screen.getByTestId('line');
    expect(within(line).getAllByRole('button', { name: 'History' })).toHaveLength(1);
    expect(within(cell('Qty')).getAllByRole('button', { name: 'History' })).toHaveLength(1);
    expect(within(cell('State')).queryAllByRole('button', { name: 'History' })).toHaveLength(0);
  });

  it('the button sits after the value / input', () => {
    renderGrid([spareRow({ state: 'draft' })], OR_PENDING);
    const qty = cell('Qty');
    const input = qty.querySelector('input');
    const button = within(qty).getByRole('button', { name: 'History' });
    expect(input, 'precondition: the approver input').not.toBeNull();
    expect(input!.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe('U1.5: the Qty cell stays one line', () => {
  it.each(VIEWS)('%s: input/value and icon in one flex items-center row', (_who, options, over) => {
    renderGrid([spareRow(over)], options);
    const qty = cell('Qty');
    const button = within(qty).getByRole('button', { name: 'History' });
    const wrapper = button.parentElement as HTMLElement;
    expect(wrapper.className).toMatch(/\bflex\b/);
    expect(wrapper.className).toMatch(/\bitems-center\b/);
    expect(qty.querySelector('.flex-col'), 'no flex-col in the Qty cell').toBeNull();
  });
});

// =============================================================================
// U1.3 - data-changed on the OR page
// =============================================================================

describe('U1.3: the OR page History button says whether the line changed', () => {
  const historyButton = () => within(cell('Qty')).getByRole('button', { name: 'History' });

  it('qty differs from submitted: changed', () => {
    renderGrid([spareRow({ qty: '8', submitted_qty: '10', unit_price: '25.0000', submitted_unit_price: '25.0000' })], OR_RAISED);
    expect(historyButton()).toHaveAttribute('data-changed', 'true');
  });

  it('unit price differs from submitted: changed', () => {
    renderGrid([spareRow({ ...UNCHANGED, unit_price: '22.0000' })], OR_RAISED);
    expect(historyButton()).toHaveAttribute('data-changed', 'true');
  });

  it('a photo added or removed: changed', () => {
    renderGrid([spareRow({ ...UNCHANGED, photo_changes: { added: 0, removed: 1 } })], OR_RAISED);
    expect(historyButton()).toHaveAttribute('data-changed', 'true');
  });

  it('nothing moved: not changed', () => {
    renderGrid([spareRow(UNCHANGED)], OR_RAISED);
    expect(historyButton()).toHaveAttribute('data-changed', 'false');
  });

  it('the approver view follows the same rule', () => {
    renderGrid([spareRow({ state: 'draft', qty: '8', submitted_qty: '10' })], OR_PENDING);
    expect(historyButton()).toHaveAttribute('data-changed', 'true');
  });
});

// =============================================================================
// U4.7 - data-changed on the OI page: previous_qty only
// =============================================================================

describe('U4.7: the OI page History button is coloured only for a post-approval change', () => {
  const historyButton = () => within(cell('Qty')).getByRole('button', { name: 'History' });

  it('an approver change before approval (qty != submitted) is not a change here', () => {
    renderGrid([spareRow({ qty: '8', submitted_qty: '10', previous_qty: null })], OI_RAISED);
    expect(historyButton()).toHaveAttribute('data-changed', 'false');
  });

  it('a photo change before approval is not a change here', () => {
    renderGrid([spareRow({ ...UNCHANGED, photo_changes: { added: 2, removed: 0 } })], OI_RAISED);
    expect(historyButton()).toHaveAttribute('data-changed', 'false');
  });

  it('a row with previous_qty (restated after approval) is changed', () => {
    renderGrid([spareRow({ ...UNCHANGED, qty: '12', previous_qty: '10' })], OI_RAISED);
    expect(historyButton()).toHaveAttribute('data-changed', 'true');
  });
});

// =============================================================================
// U1.4 - the click opens the line's History, nothing else
// =============================================================================

describe('U1.4: clicking History calls onLineHistoryClick and leaves the row alone', () => {
  it.each(VIEWS)('%s', (_who, options, over) => {
    const onLineHistoryClick = vi.fn();
    renderGrid([spareRow(over)], { ...options, onLineHistoryClick });
    fireEvent.click(within(cell('Qty')).getByRole('button', { name: 'History' }));
    expect(onLineHistoryClick).toHaveBeenCalledTimes(1);
    expect(onLineHistoryClick.mock.calls[0][0].primary.id).toBe('row-1');
    expect(rowClick).not.toHaveBeenCalled();
    const line = screen.getByTestId('line');
    expect(line).toHaveAttribute('data-selected', 'false');
    expect(line).toHaveAttribute('data-expanded', 'false');
  });
});

// =============================================================================
// U1.6 - sales-order inquiry lines unchanged
// =============================================================================

describe('U1.6: a sales-order inquiry line keeps its History button in the State cell', () => {
  it('one History button, in State, none in the quantity cells', () => {
    renderGrid(
      [
        {
          id: 'row-so',
          order_inquiry_id: 'oi-so',
          inquiry_no: 'OI-2611-0001',
          inquiry_type: 'sales_order',
          verb: 'ORDER',
          state: 'raised',
          ack_state: 'awaiting',
          item_code: 'ZZX-SO-1',
          qty: '10',
          linked_qty: '0',
          bundled_qty: '0',
        } as unknown as OrderInquiryWorklistRow,
      ],
      { inquiryType: 'sales_order' },
    );
    const line = screen.getByTestId('line');
    expect(within(line).getAllByRole('button', { name: 'History' })).toHaveLength(1);
    expect(within(cell('State')).getAllByRole('button', { name: 'History' })).toHaveLength(1);
  });
});

// =============================================================================
// U4.1 - the OI page shows the approved figures only
// =============================================================================

describe('U4.1: the OI page shows no submitted qty or submitted price', () => {
  it('Qty and Unit price read the approved values only', () => {
    renderGrid([spareRow({ qty: '8', submitted_qty: '10', unit_price: '25.0000', submitted_unit_price: '30.0000' })], OI_RAISED);
    const qty = cell('Qty').textContent ?? '';
    const price = cell('Unit price').textContent ?? '';
    expect(qty).toMatch(/(^|\D)8(\D|$)/);
    expect(qty).not.toMatch(/\b10\b/);
    expect(price).toMatch(/25\.00/);
    expect(price).not.toMatch(/30\.00/);
  });
});

// =============================================================================
// U3.2 - the OR page "OI" column
// =============================================================================

describe('U3.2: the OR page Lines carry an "OI" column after State', () => {
  it('the column exists on the OR view, right after State', () => {
    const titles = columnsOf(OR_RAISED).map(titleOf);
    const state = titles.indexOf('State');
    expect(state, 'precondition: a State column').toBeGreaterThanOrEqual(0);
    expect(titles[state + 1]).toBe('OI');
  });

  it('is not on the OI page', () => {
    expect(columnsOf(OI_RAISED).map(titleOf)).not.toContain('OI');
  });

  it('a raised line links its OI number to the OI page at that row', () => {
    renderGrid([spareRow()], OR_RAISED);
    const link = within(cell('OI')).getByRole('link', { name: 'OI-2611-0009' });
    expect(link).toHaveAttribute('href', '/project-sales/order-inquiries/oi-1?row=row-1');
  });

  it('a line whose header has no OI number yet reads "-"', () => {
    renderGrid([spareRow({ state: 'draft', oi_no: null })], OR_PENDING);
    expect(within(cell('OI')).queryByRole('link')).toBeNull();
    expect(cell('OI')).toHaveTextContent(/^-$/);
  });

  it('a click on the link does not select the row', () => {
    renderGrid([spareRow()], OR_RAISED);
    fireEvent.click(within(cell('OI')).getByRole('link', { name: 'OI-2611-0009' }));
    expect(rowClick).not.toHaveBeenCalled();
  });
});

// =============================================================================
// U3.3 - the OI page "Order request" column
// =============================================================================

// Lead ruling 14 Nov (UAC U3.3 updated): one OI is one order request, so the way back is ONE
// link in the OI page header (OrderInquiryDetail.orB.test.tsx), never a per-line column.
describe('U3.3: the OI page Lines carry no "Order request" column', () => {
  it('is not on the OI page', () => {
    expect(columnsOf(OI_RAISED).map(titleOf)).not.toContain('Order request');
  });

  it('is not on the OR page either', () => {
    expect(columnsOf(OR_RAISED).map(titleOf)).not.toContain('Order request');
  });
});

// =============================================================================
// U3.5 - both new columns: size, truncate + title, hideable, one line
// =============================================================================

describe('U3.5: the OI column follows the grid rules', () => {
  it.each([['OI', OR_RAISED, 'OI-2611-0009']])('%s', (title, options, text) => {
    const column = columnsOf(options).find((c) => titleOf(c) === title) as
      | { size?: number; enableHiding?: boolean }
      | undefined;
    expect(column, `a "${title}" column`).toBeDefined();
    expect(typeof column!.size).toBe('number');
    expect(column!.enableHiding).not.toBe(false);

    renderGrid([spareRow()], options);
    const node = within(cell(title)).getByText(text);
    const truncated = node.closest('.truncate') ?? (node.classList.contains('truncate') ? node : null);
    expect(truncated, 'the value is truncated').not.toBeNull();
    const titled = node.closest('[title]');
    expect(titled?.getAttribute('title')).toBe(text);
    expect(cell(title).querySelector('.flex-col')).toBeNull();
  });
});
