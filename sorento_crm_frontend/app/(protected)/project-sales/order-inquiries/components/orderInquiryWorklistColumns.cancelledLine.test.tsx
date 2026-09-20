/**
 * RED tests for `PLAN-oi-cancelled-line-used-confirm.md`, section 3.6 / AC-CL-2, 3
 * (`oi-cancelled-line-used-confirm-acceptance-criteria.md`).
 *
 * A NEW file (not an addition to `orderInquiryWorklistColumns.test.tsx`) - AC-CL-20 keeps
 * that file, and every other existing vitest file beside `OrderInquiriesClient.tsx`, green
 * and UNCHANGED.
 *
 * No FE implementation exists yet for `line_cancelled` at the time this file is written:
 * every test here is expected to fail for the right reason - either
 * `OrderInquiryWorklistRow` has no `line_cancelled` field yet (a TypeScript error the
 * `as OrderInquiryWorklistRow` cast in `worklistRow()` below papers over on purpose, so the
 * RUNTIME assertion is what actually reds) or the Qty cell renders no `cancelled` pill at
 * all.
 *
 * Harness copied verbatim from `orderInquiryWorklistColumns.test.tsx` (bare `<table>` off
 * `useOrderInquiryWorklistColumns()`, one column at a time - a DataGrid's own chrome never
 * has to enter this test).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

// AC-D6 precedent: Radix Tooltip only mounts TooltipContent's portal on hover, which a
// plain render+query cannot see.
vi.mock('@/components/ui/tooltip', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui/tooltip')>(
    '@/components/ui/tooltip',
  );
  return {
    ...actual,
    TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});
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

function OneColumnOnly({
  rows,
  columnId,
}: {
  rows: OrderInquiryWorklistRow[];
  columnId: string;
}) {
  const allColumns = useOrderInquiryWorklistColumns();
  const named = allColumns.find((column) => {
    const withKeys = column as ColumnDef<OrderInquiryWorklistRow> & {
      id?: string;
      accessorKey?: string;
    };
    return withKeys.id === columnId || withKeys.accessorKey === columnId;
  });
  if (!named) throw new Error(`no column with id or accessorKey "${columnId}"`);
  const table = useReactTable({
    data: rows,
    columns: [named],
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

function renderQtyCell(rows: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OneColumnOnly rows={rows} columnId="qty" />
    </QueryClientProvider>,
  );
}

describe('AC-CL-2a: the Qty cell shows a "cancelled" pill for a line_cancelled row', () => {
  it('renders the word "cancelled" in the Qty cell when line_cancelled is true', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-line-cancelled',
        qty: '90',
        item_code: 'CB2828-DIY',
        line_cancelled: true,
      } as Partial<OrderInquiryWorklistRow>),
    ]);
    const row = screen.getByTestId('row-row-line-cancelled');
    expect(within(row).getByText('cancelled')).toBeInTheDocument();
  });

  it('renders no "cancelled" pill when line_cancelled is false', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-not-cancelled',
        qty: '90',
        item_code: 'CB2828-DIY',
        line_cancelled: false,
      } as Partial<OrderInquiryWorklistRow>),
    ]);
    const row = screen.getByTestId('row-row-not-cancelled');
    expect(within(row).queryByText('cancelled')).not.toBeInTheDocument();
  });

  it('renders no "cancelled" pill when line_cancelled is undefined (every row today)', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-undefined-cancelled',
        qty: '90',
        item_code: 'CB2828-DIY',
      }),
    ]);
    const row = screen.getByTestId('row-row-undefined-cancelled');
    expect(within(row).queryByText('cancelled')).not.toBeInTheDocument();
  });
});

describe('AC-CL-2b: a row that is both used and on a cancelled line shows BOTH pills', () => {
  it('shows "used" and "cancelled" together in the Qty cell', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-both',
        qty: '364',
        item_code: 'C-FH12',
        redirected_to_pool: true,
        line_cancelled: true,
      } as Partial<OrderInquiryWorklistRow>),
    ]);
    const row = screen.getByTestId('row-row-both');
    expect(within(row).getByText('used')).toBeInTheDocument();
    expect(within(row).getByText('cancelled')).toBeInTheDocument();
  });
});

describe('AC-CL-2c: the "cancelled" pill is a plain mark, not a button, and adds no explanatory text', () => {
  it('carries no role=button and is not focusable (no tabIndex)', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-plain-pill',
        qty: '90',
        item_code: 'CB2828-DIY',
        line_cancelled: true,
      } as Partial<OrderInquiryWorklistRow>),
    ]);
    const row = screen.getByTestId('row-row-plain-pill');
    expect(within(row).queryByRole('button', { name: /cancelled/i })).not.toBeInTheDocument();
    const pill = within(row).getByText('cancelled');
    expect(pill.tagName).not.toBe('BUTTON');
    expect(pill).not.toHaveAttribute('tabindex');
  });

  it('adds no explanatory text beyond the word "cancelled" (no on-screen sentence)', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-no-explanation',
        qty: '90',
        item_code: 'CB2828-DIY',
        line_cancelled: true,
      } as Partial<OrderInquiryWorklistRow>),
    ]);
    const row = screen.getByTestId('row-row-no-explanation');
    // Anything beyond the quantity and the bare pill word reads as an on-screen
    // explanation this dense, high-frequency grid does not carry (17 Sep ruling: words,
    // never icons or sentences).
    expect(row.textContent).toMatch(/^90cancelled$/);
  });
});

describe('AC-CL-3: the Qty column keeps an explicit numeric size', () => {
  it('the qty column def carries a numeric `size`', () => {
    function ColumnsProbe({ onColumns }: { onColumns: (cols: unknown[]) => void }) {
      const cols = useOrderInquiryWorklistColumns();
      onColumns(cols as unknown[]);
      return null;
    }
    let captured: (ColumnDef<OrderInquiryWorklistRow> & { accessorKey?: string })[] = [];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ColumnsProbe
          onColumns={(cols) => {
            captured = cols as typeof captured;
          }}
        />
      </QueryClientProvider>,
    );
    const qty = captured.find((column) => column.accessorKey === 'qty');
    expect(qty).toBeDefined();
    expect(typeof qty?.size).toBe('number');
  });
});
