/**
 * SPARE-PART-OR-B C, red-first (Phase 2). C3.2, C4.1, C4.2: the spare part Lines columns.
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

describe('C3.2: the OI page spare part Qty cell is the SO-line Qty cell', () => {
  it('has no History clock in the Qty cell', () => {
    renderGrid([spareRow()], OI_VIEW);
    expect(within(cell('Qty')).queryByRole('button', { name: 'History' })).toBeNull();
  });

  it('shows the value only when the row has no post-raise change', () => {
    renderGrid([spareRow()], OI_VIEW);
    const qty = cell('Qty');
    expect(within(qty).getByText('12')).toBeInTheDocument();
    expect(within(qty).queryByText(/^Was /)).toBeNull();
    expect(within(qty).queryByTestId('qty-annotation-trigger-row-1')).toBeNull();
  });

  it('shows the annotation button when previous_qty is set (a settled change)', () => {
    renderGrid([spareRow({ previous_qty: '10' })], OI_VIEW);
    expect(within(cell('Qty')).getByTestId('qty-annotation-trigger-row-1')).toBeInTheDocument();
  });

  it('shows "Was 10" while the change waits for CS, as on an SO line', () => {
    renderGrid([spareRow({ previous_qty: '10', waiting_for_cs: true })], OI_VIEW);
    const qty = cell('Qty');
    expect(within(qty).getByText('Was 10')).toBeInTheDocument();
    expect(within(qty).getByTestId('qty-annotation-trigger-row-1')).toBeInTheDocument();
  });

  it('never reads the revised or submitted figures, only qty', () => {
    renderGrid(
      [spareRow({ qty: '10', revised_qty: '14', submitted_qty: '15', requested_qty: '16' })],
      OI_VIEW,
    );
    const qty = cell('Qty');
    expect(within(qty).getByText('10')).toBeInTheDocument();
    expect(within(qty).queryByText(/^1[456]$/)).toBeNull();
  });
});

describe('C3.3 (OR page): the clock stays on the order request page', () => {
  it('keeps the History button in the Qty cell', () => {
    renderGrid([spareRow()], OR_VIEW);
    expect(within(cell('Qty')).getByRole('button', { name: 'History' })).toBeInTheDocument();
  });
});

describe('C4.1: Revise uses the edit form, not inline Qty inputs', () => {
  it('a revision draft on the OR page shows no Qty input', () => {
    renderGrid([spareRow()], {
      ...OR_VIEW,
      canEditRevision: true,
      revisionState: 'draft',
      onEditLine: vi.fn(),
    });
    const qty = cell('Qty');
    expect(within(qty).queryByRole('textbox')).toBeNull();
    expect(within(qty).queryByRole('spinbutton')).toBeNull();
  });
});

describe('C4.2: Waiting for CS on a spare part OI row', () => {
  it('a waiting row reads the shared Waiting for CS pill', () => {
    renderGrid([spareRow({ waiting_for_cs: true, previous_qty: null })], OI_VIEW);
    expect(within(cell('State')).getByText('Waiting for CS')).toBeInTheDocument();
  });

  it('an unmoved row does not', () => {
    renderGrid([spareRow({ waiting_for_cs: false })], OI_VIEW);
    expect(within(cell('State')).queryByText('Waiting for CS')).toBeNull();
  });
});
