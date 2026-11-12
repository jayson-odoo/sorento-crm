/**
 * OI-WHOLE-SO-CANCEL v2 (H2), red: the purchasing Lines worklist has a "Status" column that
 * prints `ackStatusText` for the row ("Waiting for CS", "SO cancelled", "To order", ...),
 * sortable and hideable like the others, one value per column. Harness copied from
 * `orderInquiryWorklistColumns.cancelledLine.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

type Col = ColumnDef<OrderInquiryWorklistRow> & { id?: string; accessorKey?: string };

function worklistRow(over: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    ack_state: 'awaiting',
    verb: 'ORDER',
    links: [],
    linked_qty: '0',
    ...over,
  } as OrderInquiryWorklistRow;
}

function statusColumn(columns: Col[]): Col | undefined {
  return columns.find((c) => c.id === 'status' || c.accessorKey === 'status');
}

function StatusOnly({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const named = statusColumn(useOrderInquiryWorklistColumns() as Col[]);
  if (!named) throw new Error('the worklist has no Status column');
  const table = useReactTable({ data: rows, columns: [named], getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} data-testid={`row-${row.original.id}`}>
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderStatus(rows: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StatusOnly rows={rows} />
    </QueryClientProvider>,
  );
}

describe('H2: the Lines worklist Status column', () => {
  it('exists, titled Status, sortable and hideable', () => {
    const client = new QueryClient();
    const { result } = renderHook(() => useOrderInquiryWorklistColumns(), {
      wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    });
    const column = statusColumn(result.current as Col[]);
    expect(column, 'the worklist has no Status column').toBeDefined();
    expect((column as { meta?: { headerTitle?: string } }).meta?.headerTitle).toBe('Status');
    expect((column as { enableSorting?: boolean }).enableSorting).not.toBe(false);
    expect((column as { enableHiding?: boolean }).enableHiding).not.toBe(false);
  });

  it('prints "Waiting for CS" for a waiting row, whatever its ack state', () => {
    renderStatus([worklistRow({ id: 'w', ack_state: 'acknowledged', waiting_for_cs: true } as Partial<OrderInquiryWorklistRow>)]);
    expect(within(screen.getByTestId('row-w')).getByText('Waiting for CS')).toBeInTheDocument();
  });

  it('prints "SO cancelled" for a cancelled-SO row that is not waiting', () => {
    renderStatus([worklistRow({ id: 'c', so_cancelled: true, waiting_for_cs: false } as Partial<OrderInquiryWorklistRow>)]);
    expect(within(screen.getByTestId('row-c')).getByText('SO cancelled')).toBeInTheDocument();
  });

  it('prints today\'s words for an ordinary row', () => {
    renderStatus([
      worklistRow({ id: 'a', ack_state: 'awaiting' }),
      worklistRow({ id: 'd', ack_state: 'acknowledged' }),
    ]);
    expect(within(screen.getByTestId('row-a')).getByText('To order')).toBeInTheDocument();
    expect(within(screen.getByTestId('row-d')).getByText('Done')).toBeInTheDocument();
  });
});
