/**
 * SPARE-PART-OR-B fix round 1 (browser pass), red-first. Item 10: the OR page "OI" column.
 * Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md U3.2, U3.5.
 *
 * The OI number is fully visible: the request-view OI cell renders the number only (no
 * "PO and SPO" documents button beside it, which ate the width and clipped "OI-2611-0001"),
 * the column is at least 100 px wide, and the request view's default visible columns still
 * sum within the 950 px card at 1280 (1280 - 280 sidebar - 48 padding - 2 border).
 *
 * NAMED CONTRACT CHOICE: the default hidden set on the OR page is the Lines tab's own
 * `DEFAULT_HIDDEN_COLUMNS` + `SPARE_PART_REQUEST_HIDDEN_COLUMNS` (OrderInquiryLinesTab).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';

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

const CARD_WIDTH_AT_1280 = 1280 - 280 - 48 - 2;
const HIDDEN = [...DEFAULT_HIDDEN_COLUMNS, ...SPARE_PART_REQUEST_HIDDEN_COLUMNS];

const OR_RAISED = {
  inquiryType: 'spare_part_request',
  sparePartView: 'request',
  headerState: 'raised',
  canDecide: false,
  currency: 'MYR',
};
const OR_PENDING = { ...OR_RAISED, headerState: 'pending_approval', canDecide: true, onEditLine: vi.fn() };

function spareRow(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    order_inquiry_id: 'oi-1',
    inquiry_no: 'OR-2611-0003',
    oi_no: 'OI-2611-0001',
    inquiry_type: 'spare_part_request',
    verb: 'REPLENISH',
    state: 'raised',
    ack_state: 'awaiting',
    item_code: 'ZZX-SEAL-40',
    product_id: 'prod-1',
    stock_location: 'WH-A',
    qty: '10',
    unit_price: '25.0000',
    line_total: '250.0000',
    submitted_qty: '10',
    submitted_unit_price: '25.0000',
    photo_changes: { added: 0, removed: 0 },
    linked_qty: '0',
    bundled_qty: '0',
    links: [],
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

function titleOf(column: unknown): string | undefined {
  return (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;
}

function Grid({ rows, options }: { rows: OrderInquiryWorklistRow[]; options: Record<string, unknown> }) {
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

function ociCell(): HTMLElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Grid rows={[spareRow()]} options={OR_RAISED} />
    </QueryClientProvider>,
  );
  const found = screen.getByTestId('line').querySelector('td[data-title="OI"]');
  expect(found, 'an "OI" cell').not.toBeNull();
  return found as HTMLElement;
}

function widths(options: Record<string, unknown>) {
  const { result } = renderHook(() => {
    const columns = useOrderInquiryHeaderLinesColumns(options as never);
    const table = useReactTable({
      data: [],
      columns,
      getCoreRowModel: getCoreRowModel(),
      initialState: { columnVisibility: Object.fromEntries(HIDDEN.map((id) => [id, false])) },
    });
    return {
      total: table.getTotalSize(),
      sizes: table.getVisibleLeafColumns().map((c) => `${c.id}=${c.getSize()}`),
      oi: table.getVisibleLeafColumns().find((c) => titleOf(c.columnDef) === 'OI')?.getSize(),
    };
  });
  return result.current;
}

describe('item 10: the OR page OI number is fully visible', () => {
  it('the cell renders the OI number only, no "PO and SPO" button', () => {
    const cell = ociCell();
    expect(within(cell).getByRole('link', { name: 'OI-2611-0001' })).toBeInTheDocument();
    expect(within(cell).queryByRole('button', { name: /PO and SPO/i })).toBeNull();
    expect(within(cell).queryAllByRole('button')).toHaveLength(0);
    expect((cell.textContent ?? '').trim()).toBe('OI-2611-0001');
  });

  it.each([
    ['a reader, raised', OR_RAISED],
    ['the approver, pending', OR_PENDING],
  ])('%s: the OI column is at least 100 px and the grid fits 950 px', (_who, options) => {
    const { total, sizes, oi } = widths(options);
    expect(oi, `OI column visible by default (${sizes.join(', ')})`).toBeDefined();
    expect(oi!).toBeGreaterThanOrEqual(100);
    expect(total, `column sizes ${sizes.join(', ')} (sum ${total})`).toBeLessThanOrEqual(CARD_WIDTH_AT_1280);
  });
});
