/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:35; crew answer (a)): every Stock Debt view names the
 * customer and project of each sales order it shows.
 * - Demand grids (live + snapshot drill) carry Customer and Project columns right after Sales
 *   order, like the SO list (`SalesOrdersGrid`).
 * - Compact places (the supply grid's "Assigned to" list, a snapshot OI group's heading) print
 *   one line `CUSTOMER / project` through the shared `SoCustomerProject`.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/stock-debt',
  useSearchParams: () => new URLSearchParams(''),
}));

import { AssignedToList, buildDemandColumns, sumDemand } from './stockDebtDemandColumns';
import { groupByOi } from '../components/SnapshotDrillDialog';
import type { StockDebtDemandLine } from '../types/stockDebt.types';
import type { SnapshotLine } from '../types/stockDebtSnapshot.types';

function demandLine(over: Partial<StockDebtDemandLine> = {}): StockDebtDemandLine {
  return {
    so_number: 'SO100',
    agent_code: 'A1',
    warehouse_code: 'BRW-BB',
    required_date: '2026-12-01',
    open_qty: 10,
    qty_ordered: 10,
    qty_delivered: 0,
    assigned_qty: 0,
    status: 'short',
    short_qty: 10,
    sales_order_id: 'so-100',
    assigned_from: [],
    customer_name: 'ACME SDN BHD (PROJECT)',
    project_label: 'TAMAN JAYA',
    ...over,
  } as StockDebtDemandLine;
}

function Grid({ rows }: { rows: StockDebtDemandLine[] }) {
  const columns = React.useMemo(() => buildDemandColumns(sumDemand(rows)), [rows]);
  const table = useReactTable({ columns: columns as ColumnDef<StockDebtDemandLine>[], data: rows, getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <thead>
        <tr>
          {table.getFlatHeaders().map((h) => (
            <th key={h.id} data-col={h.id}>{h.column.id}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.getRowModel().rows.map((r) => (
          <tr key={r.id}>
            {r.getVisibleCells().map((c) => (
              <td key={c.id} data-col={c.column.id}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

describe('demand grid columns', () => {
  it('Customer and Project sit right after Sales order', () => {
    const columns = buildDemandColumns(sumDemand([]));
    const ids = columns.map((c) => c.id);
    expect(ids.slice(0, 3)).toEqual(['so_number', 'customer_name', 'project_label']);
  });

  it('render the order customer and project', () => {
    render(<Grid rows={[demandLine()]} />);
    expect(document.querySelector('td[data-col="customer_name"]')?.textContent).toBe('ACME SDN BHD (PROJECT)');
    expect(document.querySelector('td[data-col="project_label"]')?.textContent).toBe('TAMAN JAYA');
    expect(screen.getByTitle('ACME SDN BHD (PROJECT)')).toBeInTheDocument();
  });

  it('a missing customer or project prints a dash, never an id', () => {
    render(<Grid rows={[demandLine({ customer_name: null, project_label: null })]} />);
    expect(document.querySelector('td[data-col="customer_name"]')?.textContent).toBe('-');
    expect(document.querySelector('td[data-col="project_label"]')?.textContent).toBe('-');
  });

  it('both columns sort by their value', () => {
    const columns = buildDemandColumns(sumDemand([]));
    for (const id of ['customer_name', 'project_label']) {
      const col = columns.find((c) => c.id === id) as { accessorKey?: string };
      expect(col.accessorKey).toBe(id);
    }
  });
});

describe('Covered by names the orders it points at', () => {
  it('a "Lent to" receiver and an on-hand lender print CUSTOMER / project', () => {
    render(
      <Grid
        rows={[
          demandLine({
            assigned_from: [
              { kind: 'lent', ref: 'Lent to SO2 (32)', qty: 32, so_number: 'SO2', sales_order_id: 'so-2', customer_name: 'NEAR CO', project_label: 'NEAR SITE' },
              { kind: 'on_hand', ref: 'On hand BRW-BB (from SO3)', qty: 5, spo_number: null, spo_line_number: null, lent_from_so_number: 'SO3', customer_name: 'FAR CO', project_label: 'FAR SITE' },
            ],
          } as Partial<StockDebtDemandLine>),
        ]}
      />,
    );
    const cell = document.querySelector('td[data-col="covered_by"]') as HTMLElement;
    expect(cell.textContent).toContain('Lent to SO2 (32)');
    expect(cell.textContent).toContain('NEAR CO / NEAR SITE');
    expect(cell.textContent).toContain('FAR CO / FAR SITE');
  });
});

describe('<AssignedToList> (supply grid "Assigned to")', () => {
  it('names each receiving order with its customer / project', () => {
    render(
      <AssignedToList
        entries={[
          { so_number: 'SO1', line_no: 2, qty: 100, customer_name: 'ACME', project_label: 'TAMAN JAYA' },
          { so_number: 'SO2', line_no: null, qty: 5, customer_name: null, project_label: null },
        ]}
      />,
    );
    expect(screen.getByText('SO1 line 2 (100)')).toBeInTheDocument();
    expect(screen.getByText('ACME / TAMAN JAYA')).toBeInTheDocument();
    expect(screen.getByText('SO2 (5)')).toBeInTheDocument();
  });

  it('reads Free when nothing took it', () => {
    render(<AssignedToList entries={[]} />);
    expect(screen.getByText('Free')).toBeInTheDocument();
  });
});

describe('snapshot drill OI groups', () => {
  const base = demandLine() as unknown as SnapshotLine;
  const oiRow = (oi_id: string, inquiry_no: string) => ({
    oi_id, inquiry_no, row_id: `${oi_id}-r`, qty: 1, delivery_date: null, stock_location: null, verb: 'ORDER', state: 'raised',
  });

  it('each group carries its order customer and project', () => {
    const groups = groupByOi([
      { ...base, bucket: '2026-12', sales_order_line_id: 'l1', now: { so_status: 'open', open_qty: 1 }, oi_rows: [oiRow('oi1', 'OI-1')] },
      { ...base, customer_name: null, project_label: null, bucket: '2026-12', sales_order_line_id: 'l2', now: { so_status: 'open', open_qty: 1 }, oi_rows: [] },
    ]);
    expect(groups[0]).toMatchObject({ inquiryNo: 'OI-1', customerName: 'ACME SDN BHD (PROJECT)', projectLabel: 'TAMAN JAYA' });
    expect(groups[1]).toMatchObject({ oiId: null, customerName: null, projectLabel: null });
  });
});
