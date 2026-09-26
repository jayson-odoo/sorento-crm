/**
 * Owner hand test, PR #1264 note 2: "why reorder lines need toggling, just straight away drag
 * and reorder". Every row carries its handle whenever the order may be reordered, and a drop
 * saves at once: no mode to press into first, no Done to press after.
 *
 * dnd-kit measures real layout, which jsdom has none of, so the drop itself is simulated: the
 * shared rows component is replaced by one that hands back the ids it was given and fires the
 * table's own `handleDragEnd` with an `active` / `over` pair, exactly as dnd-kit would.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ProjectSalesOrderLine } from '../../_shared/types/projectSalesOrder.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/components/ui/data-grid-table-dnd-rows', () => ({
  DataGridTableDndRowHandle: ({ rowId }: { rowId: string }) => (
    <span data-testid={`handle-${rowId}`} />
  ),
  DataGridTableDndRows: ({
    handleDragEnd,
    dataIds,
  }: {
    handleDragEnd: (event: { active: { id: string }; over: { id: string } | null }) => void;
    dataIds: string[];
  }) => (
    <div>
      <p data-testid="drag-ids">{dataIds.join(',')}</p>
      {dataIds.map((id) => (
        <span key={id} data-testid={`handle-${id}`} />
      ))}
      <button
        type="button"
        onClick={() => handleDragEnd({ active: { id: 'c' }, over: { id: 'a' } })}
      >
        drop c on a
      </button>
    </div>
  ),
}));

import { SalesOrderLinesTable } from './SalesOrderLinesTable';

function line(id: string, line_no: number, code: string): ProjectSalesOrderLine {
  return {
    id,
    line_no,
    product_code: code,
    description: `${code} description`,
    qty: '1',
    uom: 'UNIT',
    unit_price: '10.00000',
    amount: '10.00',
    delivery_date: null,
    phase_label: null,
    explosion_source: 'direct',
    source_po_line_no: line_no,
    stock_location: null,
  };
}

const LINES = [line('b', 2, 'BBB'), line('a', 1, 'AAA'), line('c', 3, 'CCC')];

function renderTable(props: Partial<React.ComponentProps<typeof SalesOrderLinesTable>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderLinesTable lines={LINES} {...props} />
    </QueryClientProvider>,
  );
}

describe('drag to reorder, with no toggle (PR #1264 note 2)', () => {
  it('draws a handle on every row as soon as the order may be reordered', () => {
    renderTable({ reorder: { enabled: true, onReorder: vi.fn() } });

    expect(screen.getByTestId('drag-ids')).toHaveTextContent('a,b,c');
    expect(screen.queryByRole('button', { name: /Reorder lines/ })).not.toBeInTheDocument();
  });

  it('saves a drop straight away, with the whole order in its new sequence', () => {
    const onReorder = vi.fn();
    renderTable({ reorder: { enabled: true, onReorder } });

    fireEvent.click(screen.getByRole('button', { name: 'drop c on a' }));

    expect(onReorder).toHaveBeenCalledTimes(1);
    expect(onReorder).toHaveBeenCalledWith(['c', 'a', 'b']);
  });

  it('draws no handle where the order may not be reordered', () => {
    renderTable();

    expect(screen.queryByTestId('drag-ids')).not.toBeInTheDocument();
    expect(screen.getByText('AAA')).toBeInTheDocument();
  });
});
