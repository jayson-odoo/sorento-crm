/**
 * The list's own "Linked to" column (AC-I14): the SAME `SupplyBar` the schedule matrix
 * draws, off the same three kinds, under the coverage headline. Rendered here as a bare
 * `<table>` off `useOrderInquiryWorklistColumns()` directly - just the one column, so a
 * DataGrid's own chrome (which needs `useListingColumnPreferences` mocked under jsdom,
 * see `OrderInquiriesClient.test.tsx`) never has to enter this test at all.
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

/** Just the "Linked to" column - the actions column pulls in dialogs this test is not
 * about, and the bar lives entirely in this one cell. */
function LinkedToOnly({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const allColumns = useOrderInquiryWorklistColumns();
  const linkedColumn = allColumns.find(
    (column) => (column as ColumnDef<OrderInquiryWorklistRow> & { id?: string }).id === 'po_number',
  )!;
  const table = useReactTable({
    data: rows,
    columns: [linkedColumn],
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} data-testid={`row-${row.original.id}`}>
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderRows(rows: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LinkedToOnly rows={rows} />
    </QueryClientProvider>,
  );
}

describe('the "Linked to" column (AC-I14)', () => {
  it('draws the bar on a row wholly linked to a purchase order', () => {
    renderRows([
      worklistRow({
        id: 'row-linked',
        qty: '35',
        linked_qty: '35',
        po_number: '202601-S0015',
        links: [{ id: 'l1', kind: 'po', document: '202601-S0015', qty: '35', po_id: 'po-1' }],
      }),
    ]);

    const row = screen.getByTestId('row-row-linked');
    const bar = within(row).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'true');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('po');
  });

  it('says "Not linked" AND still draws the bar - a solid rose Buy segment', () => {
    renderRows([worklistRow({ id: 'row-unlinked', qty: '85', linked_qty: '0', links: [] })]);

    const row = screen.getByTestId('row-row-unlinked');
    expect(within(row).getByText('Not linked')).toBeInTheDocument();
    const bar = within(row).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('buy');
  });

  it('draws a split sky/rose bar for a row linked 5 of 8 to a purchase order', () => {
    renderRows([
      worklistRow({
        id: 'row-split',
        qty: '8',
        linked_qty: '5',
        po_number: '202601-S0044',
        links: [
          { id: 'l1', kind: 'po', document: '202601-S0044', qty: '5', po_id: 'po-2' },
        ],
      }),
    ]);

    const row = screen.getByTestId('row-row-split');
    const bar = within(row).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    const kinds = [...bar.querySelectorAll('span[data-kind]')].map((el) =>
      el.getAttribute('data-kind'),
    );
    expect(kinds).toEqual(['po', 'buy']);
  });

  it('draws no bar at all for a cancelled row - it owes nothing', () => {
    renderRows([
      worklistRow({ id: 'row-cancelled', qty: '6', linked_qty: '0', links: [], state: 'cancelled' }),
    ]);

    const row = screen.getByTestId('row-row-cancelled');
    expect(within(row).queryByTestId('supply-bar')).not.toBeInTheDocument();
  });
});
