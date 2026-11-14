/**
 * SPARE-PART-ORDER-REQUEST F3 (UAC P4, A3): the OI Lines tab columns for a spare part
 * request - Unit price and Total columns; while the header is Pending approval and the
 * viewer can decide, qty and unit price render as inputs; a qty that differs from the
 * requester's submitted qty shows "was 10" (approval screen AND purchasing).
 *
 * TEST-FIRST (Phase 2). NAMED ASSUMPTIONS (the brief fixes the behaviour, not the props):
 * 1. `useOrderInquiryHeaderLinesColumns` takes `inquiryType`, `headerState`, `canDecide` and
 *    `onEditLine(row, { qty?, unit_price? })` alongside its existing options.
 * 2. The worklist row carries `unit_price`, `line_total`, and the requester's values as
 *    `submitted_qty` / `submitted_unit_price`: the worklist row's `requested_qty` is ALREADY
 *    taken (the open reserve request's qty, `OrderInquiryWorklistRow.requested_qty`), so the
 *    spare-part "was" values cannot reuse that wire name on this payload.
 * The sales-order census (`orderInquiryHeaderLinesColumns.test.tsx`) stays the regression
 * guard that a sales-order inquiry's columns are unchanged.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
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
    inquiry_type: 'spare_part_request',
    verb: 'REPLENISH',
    state: 'draft',
    ack_state: 'awaiting',
    item_code: 'SP-SEAL-40',
    product_id: 'prod-1',
    stock_location: 'BRW',
    qty: '8',
    unit_price: '25.0000',
    line_total: '200.0000',
    submitted_qty: '10',
    submitted_unit_price: '25.0000',
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

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

describe('F3 / UAC P4: Unit price and Total columns for a spare part request', () => {
  it('carries Unit price and Total columns for the spare part type', () => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns(PENDING_DECIDER as never));
    const titles = result.current.map(titleOf).filter(Boolean);
    expect(titles).toContain('Unit price');
    expect(titles).toContain('Total');
  });

  it('a sales-order inquiry gets no Unit price or Total column', () => {
    const { result } = renderHook(() =>
      useOrderInquiryHeaderLinesColumns({ inquiryType: 'sales_order' } as never),
    );
    const titles = result.current.map(titleOf).filter(Boolean);
    expect(titles).not.toContain('Unit price');
    expect(titles).not.toContain('Total');
  });

  it('a raised line reads its unit price and total as money, no inputs', () => {
    renderGrid([spareRow({ state: 'raised' })], {
      inquiryType: 'spare_part_request',
      headerState: 'raised',
      canDecide: false,
    });
    expect(cell('Unit price')).toHaveTextContent(/25\.00/);
    expect(cell('Total')).toHaveTextContent(/200\.00/);
    expect(within(screen.getByTestId('line')).queryAllByRole('textbox')).toHaveLength(0);
    expect(within(screen.getByTestId('line')).queryAllByRole('spinbutton')).toHaveLength(0);
  });
});

describe('F3 / UAC A3: the approver edits qty and unit price in place while pending', () => {
  function inputValues(): number[] {
    const line = screen.getByTestId('line');
    return Array.from(line.querySelectorAll('input:not([type="checkbox"])')).map((input) =>
      Number((input as HTMLInputElement).value),
    );
  }

  it('renders qty and unit price as inputs for a decider on a pending request', () => {
    renderGrid([spareRow()], PENDING_DECIDER);
    const values = inputValues();
    expect(values).toContain(8);
    expect(values).toContain(25);
    expect(cell('Unit price').querySelector('input')).not.toBeNull();
  });

  it('renders no inputs for a viewer who cannot decide', () => {
    renderGrid([spareRow()], { ...PENDING_DECIDER, canDecide: false });
    expect(inputValues()).toEqual([]);
  });

  it('shows "was 10" beside a qty the approver changed from the submitted 10', () => {
    renderGrid([spareRow()], PENDING_DECIDER);
    expect(within(screen.getByTestId('line')).getByText(/was 10\b/)).toBeInTheDocument();
  });

  it('purchasing sees the same "was" mark once raised', () => {
    renderGrid([spareRow({ state: 'raised' })], {
      inquiryType: 'spare_part_request',
      headerState: 'raised',
      canDecide: false,
    });
    expect(within(screen.getByTestId('line')).getByText(/was 10\b/)).toBeInTheDocument();
  });

  it('an unchanged qty shows no "was" mark', () => {
    renderGrid([spareRow({ qty: '10', line_total: '250.0000' })], PENDING_DECIDER);
    expect(within(screen.getByTestId('line')).queryByText(/was /)).toBeNull();
  });
});
