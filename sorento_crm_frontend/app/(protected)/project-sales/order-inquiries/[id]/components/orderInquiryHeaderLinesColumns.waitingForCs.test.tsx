/**
 * OI-WHOLE-SO-CANCEL v2 (AC-V2-4b), red: the Lines tab SO Qty cell shows the line's new qty
 * with "Was <previous_so_line_qty>" when the API sends one.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import { foldInquiryLines, toLineRows } from '../../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function SoQtyOnly({ rows }: { rows: ReturnType<typeof toLineRows> }) {
  const columns = useOrderInquiryHeaderLinesColumns();
  const named = columns.find((c) => (c as { id?: string }).id === 'so_qty')!;
  const table = useReactTable({ data: rows, columns: [named], getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} data-testid="so-qty-row">
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function lineRows(over: Partial<OrderInquiryWorklistRow>) {
  const row = {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '6',
    linked_qty: '0',
    bundled_qty: '0',
    so_line_id: 'sol-1',
    so_line_qty: '7',
    ...over,
  } as OrderInquiryWorklistRow;
  return toLineRows(foldInquiryLines([row]));
}

describe('AC-V2-4b: the SO Qty cell', () => {
  it('prints "Was 10" under a line qty of 7 when previous_so_line_qty is 10', () => {
    render(<SoQtyOnly rows={lineRows({ previous_so_line_qty: '10' } as Partial<OrderInquiryWorklistRow>)} />);
    const cell = screen.getByTestId('so-qty-row');
    expect(within(cell).getByText('7')).toBeInTheDocument();
    expect(within(cell).getByText('Was 10')).toBeInTheDocument();
  });

  it('prints no Was when previous_so_line_qty is null', () => {
    render(<SoQtyOnly rows={lineRows({ previous_so_line_qty: null } as Partial<OrderInquiryWorklistRow>)} />);
    expect(within(screen.getByTestId('so-qty-row')).queryByText(/^Was /)).not.toBeInTheDocument();
  });
});
