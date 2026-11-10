/**
 * PROPOSAL-FORM-COLLAPSE, owner hand test (10 Nov 2026): "the preview when i drag the heading is
 * not so right". A row the grid draws whole (`renderFullRow`, the quotation's section heading)
 * must float as that same full-width content while dragged, never as the row's ordinary cells.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, render, screen, within } from '@testing-library/react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import type { DragStartEvent } from '@dnd-kit/core';

import { DataGrid } from './data-grid';
import { DataGridTableDndRows } from './data-grid-table-dnd-rows';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  usePathname: () => '/some-listing',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// The row DndContext's drag start, captured, and its overlay drawn inline where a test can read it.
const dnd: { start: ((event: DragStartEvent) => void) | null } = { start: null };
vi.mock('@dnd-kit/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@dnd-kit/core')>();
  return {
    ...actual,
    DndContext: (props: React.ComponentProps<typeof actual.DndContext>) => {
      if (props.onDragStart) dnd.start = props.onDragStart;
      return <actual.DndContext {...props} />;
    },
    DragOverlay: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="drag-overlay">{children}</div>
    ),
  };
});

type Item = { id: string; name: string; heading?: string };
const DATA: Item[] = [
  { id: 'r1', name: 'Alpha' },
  { id: 'h1', name: '', heading: 'PAGE 1' },
];
const COLUMNS: ColumnDef<Item>[] = [
  { id: 'name', accessorKey: 'name', header: 'Name', size: 200, cell: () => 'ORDINARY CELL' },
];

function Harness() {
  const table = useReactTable({
    data: DATA,
    columns: COLUMNS,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={DATA.length}
      isLoading={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      renderFullRow={(row: unknown, options?: { overlay?: boolean }) => {
        const item = row as Item;
        if (!item.heading) return null;
        return options?.overlay ? <span>{`PREVIEW ${item.heading}`}</span> : <span>{item.heading}</span>;
      }}
    >
      <DataGridTableDndRows handleDragEnd={() => {}} dataIds={DATA.map((row) => row.id)} />
    </DataGrid>
  );
}

describe('the drag preview of a full-width row', () => {
  it('floats the full-width content, never the row\'s ordinary cells', () => {
    render(<Harness />);
    act(() => dnd.start?.({ active: { id: 'h1' } } as unknown as DragStartEvent));
    const overlay = screen.getByTestId('drag-overlay');
    expect(within(overlay).getByText('PREVIEW PAGE 1')).toBeInTheDocument();
    expect(within(overlay).queryByText('ORDINARY CELL')).toBeNull();
    expect(overlay.querySelectorAll('td')).toHaveLength(1);
  });

  it('still floats an ordinary row as its cells', () => {
    render(<Harness />);
    act(() => dnd.start?.({ active: { id: 'r1' } } as unknown as DragStartEvent));
    expect(within(screen.getByTestId('drag-overlay')).getByText('ORDINARY CELL')).toBeInTheDocument();
  });
});
