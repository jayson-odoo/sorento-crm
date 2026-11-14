/**
 * SPARE-PART-OR-B C fix round 1, red-first. R3: the spare part OI view has a Delivery date
 * column that IS the SO line's `DeliveryDateCell`; the Changed pill lives there, not in Qty.
 * Harness copied from orderInquiryHeaderLinesColumns.orC.test.tsx.
 * Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md.
 *
 * NAMED CONTRACT CHOICES (the UAC leaves them open):
 * 1. The OI page (`sparePartView: 'inquiry'`) Qty cell IS the SO-line `QtyCell`
 *    (`orderInquiryWorklistColumns.tsx`): the value, "Was N" while `waiting_for_cs` and
 *    `previous_qty` are set, and `QtyAnnotationButton` (testid `qty-annotation-trigger-<id>`)
 *    only when `previous_qty` is set. No "History" button in that cell.
 * 2. The OR page (`sparePartView: 'request'`) keeps the History clock in the Qty cell.
 * 3. During a revision the OR page has no inline Qty input (`canEditRevision` no longer turns
 *    the cell into an input): Revise opens the edit form instead (C4.1).
 * 4. "Waiting for CS" on a spare part OI row is the shared `OrderInquiryLineStatusPill`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, getExpandedRowModel, useReactTable } from '@tanstack/react-table';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return { ...actual, getOrderInquiryPoDetail: vi.fn(), getOrderInquirySpoDetail: vi.fn() };
});
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import { DeliveryDateCell } from '../../components/orderInquiryWorklistColumns';
import { foldInquiryLines, toLineRows } from '../../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

afterEach(cleanup);

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
    qty: '12',
    unit_price: '25.0000',
    line_total: '300.0000',
    submitted_qty: '12',
    submitted_unit_price: '25.0000',
    photo_changes: { added: 0, removed: 0 },
    previous_qty: null,
    waiting_for_cs: false,
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

const OI_VIEW: Options = {
  inquiryType: 'spare_part_request',
  sparePartView: 'inquiry',
  headerState: 'raised',
  canDecide: false,
  currency: 'MYR',
};
const OR_VIEW: Options = { ...OI_VIEW, sparePartView: 'request' };

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
  if (!found) throw new Error(`no ${title} cell`);
  return found as HTMLElement;
}

function qtyCellOrNull(): HTMLElement | null {
  return screen.getByTestId('line').querySelector('td[data-title="Qty"]');
}

describe('R3: the OI view Delivery date column is the SO line DeliveryDateCell', () => {
  it('has a Delivery date column on the OI view', () => {
    renderGrid([spareRow({ delivery_date: '2026-12-15' })], OI_VIEW);
    expect(cell('Delivery date')).toBeInTheDocument();
  });

  it('prints what DeliveryDateCell prints for the same row', () => {
    const row = spareRow({ delivery_date: '2027-01-20', previous_delivery_date: '2026-12-15' });
    const alone = render(<DeliveryDateCell row={row} />);
    const expected = alone.container.textContent;
    alone.unmount();
    renderGrid([row], OI_VIEW);
    expect(cell('Delivery date').textContent).toBe(expected);
    expect(cell('Delivery date').textContent).toContain('20/01/2027');
  });

  it('a settled change shows Changed on the date, not in the Qty cell', () => {
    renderGrid([spareRow({ ack_state: 'changed', previous_qty: '10' })], OI_VIEW);
    expect(within(cell('Delivery date')).getByTestId('delivery-date-changed-row-1')).toBeInTheDocument();
    const qty = qtyCellOrNull();
    expect(qty && within(qty).queryByText('Changed')).toBeFalsy();
  });

  it('a date-only settled change shows on the date', () => {
    renderGrid(
      [spareRow({ ack_state: 'changed', delivery_date: '2027-01-20', previous_delivery_date: '2026-12-15' })],
      OI_VIEW,
    );
    const date = cell('Delivery date');
    expect(date.textContent).toContain('20/01/2027');
    expect(within(date).getByTestId('delivery-date-changed-row-1')).toBeInTheDocument();
  });
});
