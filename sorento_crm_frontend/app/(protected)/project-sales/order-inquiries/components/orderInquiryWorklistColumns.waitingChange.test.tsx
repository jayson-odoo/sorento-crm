/**
 * OI-WHOLE-SO-CANCEL v2 (waiting change detail, crew decision 12 Nov), red: the purchasing Lines
 * Status column says WHAT a waiting row is waiting on. A date / qty change reads
 * "Waiting for CS · date 18/12/2026 -> 17/01/2027" / "Waiting for CS · qty 10 -> 7"; any SO-side
 * cancel, delete or line removal renders the EXISTING line-cancelled pill plus a separate
 * "Waiting for CS" marker (no "SO cancelled" text); once CS confirms, only the plain pill.
 * Harness copied from `orderInquiryWorklistColumns.statusColumn.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

type Col = ColumnDef<OrderInquiryWorklistRow> & { id?: string; accessorKey?: string };

function worklistRow(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    ack_state: 'awaiting',
    verb: 'ORDER',
    links: [],
    linked_qty: '0',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

function StatusOnly({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const named = (useOrderInquiryWorklistColumns() as Col[]).find(
    (c) => c.id === 'status' || c.accessorKey === 'status',
  );
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

function renderRow(row: OrderInquiryWorklistRow) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StatusOnly rows={[row]} />
    </QueryClientProvider>,
  );
}

const waitingCancelled = (kind: 'so_cancelled' | 'line_removed') =>
  worklistRow({
    id: 'w',
    line_cancelled: true,
    waiting_for_cs: true,
    waiting_change: { kind, was: null, now: null },
    ...(kind === 'so_cancelled' ? { so_cancelled: true } : {}),
  });

describe('waiting change detail on the Status column', () => {
  it('reads the date change', () => {
    renderRow(
      worklistRow({
        id: 'w',
        waiting_for_cs: true,
        waiting_change: { kind: 'date', was: '18/12/2026', now: '17/01/2027' },
      }),
    );
    expect(screen.getByTestId('row-w')).toHaveTextContent(
      'Waiting for CS · date 18/12/2026 -> 17/01/2027',
    );
  });

  it('reads the qty change', () => {
    renderRow(
      worklistRow({
        id: 'w',
        waiting_for_cs: true,
        waiting_change: { kind: 'qty', was: '10', now: '7' },
      }),
    );
    expect(screen.getByTestId('row-w')).toHaveTextContent('Waiting for CS · qty 10 -> 7');
  });

  it.each(['so_cancelled', 'line_removed'] as const)(
    'a waiting %s change shows the existing line-cancelled pill plus a Waiting for CS marker',
    (kind) => {
      const plain = renderRow(worklistRow({ id: 'p', line_cancelled: true }));
      const plainPill = within(screen.getByTestId('row-p')).getByText('Line cancelled');
      const plainClass = plainPill.className;
      plain.unmount();

      renderRow(waitingCancelled(kind));
      const cell = screen.getByTestId('row-w');
      const pill = within(cell).getByText('Line cancelled');
      expect(pill.className).toBe(plainClass);
      expect(within(cell).getByText('Waiting for CS')).toBeInTheDocument();
      expect(cell).not.toHaveTextContent('SO cancelled');
    },
  );

  it('after CS confirms, only the plain line-cancelled pill remains', () => {
    renderRow(
      worklistRow({ id: 'w', line_cancelled: true, waiting_for_cs: false, waiting_change: null }),
    );
    const cell = screen.getByTestId('row-w');
    expect(within(cell).getByText('Line cancelled')).toBeInTheDocument();
    expect(cell).not.toHaveTextContent('Waiting for CS');
  });
});
