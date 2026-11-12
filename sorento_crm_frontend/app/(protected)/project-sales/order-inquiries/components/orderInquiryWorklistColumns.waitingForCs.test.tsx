/**
 * OI-WHOLE-SO-CANCEL v2 (AC-V2-4), red: the worklist Qty cell shows "Was <previous_qty>"
 * beside a qty that differs from the confirmed one, the same visual pattern the delivery
 * date cell uses for its Was. Harness copied from
 * `orderInquiryWorklistColumns.cancelledLine.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { describe, expect, it } from 'vitest';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

function worklistRow(over: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    verb: 'ORDER',
    links: [],
    linked_qty: '0',
    ...over,
  } as OrderInquiryWorklistRow;
}

function OneColumnOnly({ rows, columnId }: { rows: OrderInquiryWorklistRow[]; columnId: string }) {
  const allColumns = useOrderInquiryWorklistColumns();
  const named = allColumns.find((column) => {
    const withKeys = column as ColumnDef<OrderInquiryWorklistRow> & {
      id?: string;
      accessorKey?: string;
    };
    return withKeys.id === columnId || withKeys.accessorKey === columnId;
  });
  if (!named) throw new Error(`no column "${columnId}"`);
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

function renderQty(rows: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OneColumnOnly rows={rows} columnId="qty" />
    </QueryClientProvider>,
  );
}

describe('AC-V2-4: the Qty cell shows Was <previous_qty> when it differs', () => {
  it('prints "Was 10" beside a qty of 7', () => {
    renderQty([worklistRow({ id: 'r', qty: '7', previous_qty: '10' })]);
    expect(within(screen.getByTestId('row-r')).getByText('Was 10')).toBeInTheDocument();
  });

  it('prints no Was when previous_qty equals qty', () => {
    renderQty([worklistRow({ id: 'r', qty: '10', previous_qty: '10' })]);
    expect(within(screen.getByTestId('row-r')).queryByText(/^Was /)).not.toBeInTheDocument();
  });

  it('prints no Was when there is no previous_qty', () => {
    renderQty([worklistRow({ id: 'r', qty: '10', previous_qty: null })]);
    expect(within(screen.getByTestId('row-r')).queryByText(/^Was /)).not.toBeInTheDocument();
  });
});
