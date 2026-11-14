/**
 * SPARE-PART-ORDER-REQUEST hand-test round 2 (owner 13 Nov), red-first (Phase 2).
 *
 * F3 "1 line per row principle, why the description and code are in 1 cell": in the spare part
 *    (Order Request) Lines grid, the code and the description are two columns.
 *      - "Product code": the cell shows only the code, one truncated line (title = the code).
 *      - "Description": `line_description`, falling back to `product_name`, one truncated line
 *        (title = the text).
 *    The old combined "Product" column is gone. R11 (visible sizes <= 950) and R13 (Location
 *    >= 90) from review2 keep holding with the extra column.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, screen } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return { ...actual, getOrderInquiryPoDetail: vi.fn(), getOrderInquirySpoDetail: vi.fn() };
});
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import {
  SPARE_PART_REQUEST_HIDDEN_COLUMNS,
  useOrderInquiryHeaderLinesColumns,
} from './orderInquiryHeaderLinesColumns';
import { DEFAULT_HIDDEN_COLUMNS } from '../../components/orderInquiryWorklistColumns';
import { foldInquiryLines, toLineRows } from '../../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

beforeEach(() => vi.clearAllMocks());

type Options = Record<string, unknown>;

const titleOf = (column: unknown): string | undefined =>
  (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;

function spareRow(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    order_inquiry_id: 'oi-1',
    inquiry_type: 'spare_part_request',
    verb: 'REPLENISH',
    state: 'raised',
    ack_state: 'awaiting',
    item_code: 'SP-SEAL-40',
    product_id: 'prod-1',
    product_name: 'Pump seal 40mm',
    line_description: 'Seal for the left pump, blue rubber',
    stock_location: 'BRW',
    qty: '8',
    unit_price: '25.0000',
    line_total: '200.0000',
    submitted_qty: '8',
    submitted_unit_price: '25.0000',
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

const READER: Options = { inquiryType: 'spare_part_request', headerState: 'raised', canDecide: false };
const PENDING_DECIDER: Options = {
  inquiryType: 'spare_part_request',
  headerState: 'pending_approval',
  canDecide: true,
  onEditLine: vi.fn(),
};

function Grid({ rows, options }: { rows: OrderInquiryWorklistRow[]; options: Options }) {
  const columns = useOrderInquiryHeaderLinesColumns(options as never);
  const data = React.useMemo(() => toLineRows(foldInquiryLines(rows)), [rows]);
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} data-testid="line">
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

function renderGrid(rows: OrderInquiryWorklistRow[], options: Options = READER) {
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

const text = (el: HTMLElement) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('F3: code and description are separate columns', () => {
  it.each([
    ['a reader', READER],
    ['the approver', PENDING_DECIDER],
  ])('%s: has a "Product code" and a "Description" column, and no combined "Product"', (_who, options) => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns(options as never));
    const titles = result.current.map(titleOf).filter(Boolean);
    expect(titles).toContain('Product code');
    expect(titles).toContain('Description');
    expect(titles).not.toContain('Product');
    expect(titles.indexOf('Description')).toBe(titles.indexOf('Product code') + 1);
  });

  it('the Product code cell shows the code and no description text', () => {
    renderGrid([spareRow()]);
    const code = cell('Product code');
    expect(text(code)).toBe('SP-SEAL-40');
    expect(text(code)).not.toContain('Seal for the left pump');
    expect(text(code)).not.toContain('Pump seal 40mm');
  });

  it('the Product code cell is one truncated line titled with the code', () => {
    renderGrid([spareRow()]);
    const code = cell('Product code');
    expect(code.querySelector('.truncate'), 'a truncate element').not.toBeNull();
    expect(code.querySelector('[title="SP-SEAL-40"]'), 'title = the code').not.toBeNull();
    expect(code.querySelector('br')).toBeNull();
  });

  it('the Description cell shows line_description', () => {
    renderGrid([spareRow()]);
    expect(text(cell('Description'))).toBe('Seal for the left pump, blue rubber');
  });

  it.each([
    ['null', null],
    ['empty', ''],
  ])('the Description cell falls back to product_name when line_description is %s', (_l, value) => {
    renderGrid([spareRow({ line_description: value })]);
    expect(text(cell('Description'))).toBe('Pump seal 40mm');
  });

  it('the Description cell is one truncated line with the full text as its title', () => {
    renderGrid([spareRow()]);
    const description = cell('Description');
    expect(description.querySelector('.truncate'), 'a truncate element').not.toBeNull();
    expect(
      description.querySelector('[title="Seal for the left pump, blue rubber"]'),
      'title = the description',
    ).not.toBeNull();
    expect(description.querySelector('br')).toBeNull();
  });

  it('the Description cell does not repeat the code', () => {
    renderGrid([spareRow()]);
    expect(text(cell('Description'))).not.toContain('SP-SEAL-40');
  });
});

describe('F3: R11 and R13 still hold with the extra column', () => {
  const CARD_WIDTH_AT_1280 = 1280 - 280 - 48 - 2;

  function sizesOf(options: Options) {
    const { result } = renderHook(() => {
      const columns = useOrderInquiryHeaderLinesColumns(options as never);
      const table = useReactTable({
        data: [],
        columns,
        getCoreRowModel: getCoreRowModel(),
        // SPARE-PART-OR-B U3.3b: the view's default visibility (PO hidden on the request view).
        initialState: {
          columnVisibility: Object.fromEntries(
            [
              ...DEFAULT_HIDDEN_COLUMNS,
              ...(options.sparePartView === 'request' ? SPARE_PART_REQUEST_HIDDEN_COLUMNS : []),
            ].map((id) => [id, false]),
          ),
        },
      });
      return {
        total: table.getTotalSize(),
        sizes: table.getVisibleLeafColumns().map((c) => `${c.id}=${c.getSize()}`),
        titles: table.getVisibleLeafColumns().map((c) => titleOf(c.columnDef)),
      };
    });
    return result.current;
  }

  // SPARE-PART-OR-B (lead ruling 14 Nov): on both views, the order request page and the OI.
  it.each(
    (['request', 'inquiry'] as const).flatMap((view): Array<[string, Options]> => [
      [`${view} view, a reader`, { ...READER, sparePartView: view }],
      [`${view} view, the approver`, { ...PENDING_DECIDER, sparePartView: view }],
    ]),
  )('%s: both columns are visible by default and the sizes fit the 950 card', (_who, options) => {
    const { total, sizes, titles } = sizesOf(options);
    expect(titles, `visible: ${sizes.join(', ')}`).toEqual(
      expect.arrayContaining(['Product code', 'Description']),
    );
    expect(total, `sum ${total}: ${sizes.join(', ')}`).toBeLessThanOrEqual(CARD_WIDTH_AT_1280);
  });

  it.each([
    ['a reader', READER],
    ['the approver', PENDING_DECIDER],
  ])('%s: Location stays at least 90 px', (_who, options) => {
    const { sizes } = sizesOf(options);
    const location = sizes.find((s) => /^location[^=]*=/.test(s));
    expect(location, sizes.join(', ')).toBeDefined();
    expect(Number(location!.split('=')[1])).toBeGreaterThanOrEqual(90);
  });
});

describe('crew pass 0f6da244: the "Product code" header is not clipped at 1280', () => {
  it.each([
    ['a reader, raised', READER],
    ['the approver, pending', PENDING_DECIDER],
  ])('%s: Product code is at least 124 px wide (the header text measured 124 px)', (_who, options) => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns(options as never));
    const code = result.current.find((c) => titleOf(c) === 'Product code') as { size?: number } | undefined;
    expect(code, 'precondition: a Product code column').toBeDefined();
    expect(code!.size ?? 0).toBeGreaterThanOrEqual(124);
  });
});
