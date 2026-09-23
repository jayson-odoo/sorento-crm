/**
 * `PLAN-oi-request-cs-reserve.md` section 6d G3, `oi-request-cs-reserve-acceptance-
 * criteria.md` AC-RS-69 (round 3).
 *
 * TEST-FIRST (Phase 2): today `DataGridTableDndHeader` renders a `GripVertical` and the
 * `aria-label="Drag column to reorder"` wrapper for EVERY leaf header, unconditionally -
 * `meta.draggable` does not exist on `ColumnMeta` yet, and `useSortable` is never handed
 * `disabled` off anything but a group header. A red here is "the grip still shows on a
 * column that asked not to have one" - the plan's own stated behaviour not existing yet -
 * never an import typo or a fixture bug.
 *
 * `columnsDraggable` defaults to `true` (`data-grid.tsx`), so `DataGridTable` renders
 * through `DataGridTableDnd`/`DataGridTableDndHeader` by default - the same component
 * every real listing actually mounts, per `data-grid-table.column-drag.test.tsx`'s own
 * doc comment.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { DataGrid } from './data-grid';
import { DataGridTable } from './data-grid-table';
import { buildSelectColumn } from './data-grid-select-column';

vi.mock('next/navigation', () => ({
  usePathname: () => '/some-listing',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

type Row = { id: string; name: string };

const ROWS: Row[] = [{ id: '1', name: 'Alpha' }];

/**
 * The OI Lines grid's own `expand` column carries `meta.expandedContent`
 * (`orderInquiryHeaderLinesColumns.tsx`) and never asks to be dragged; a plain data
 * column ("Name") carries neither and keeps its grip.
 */
const COLUMNS: ColumnDef<Row>[] = [
  {
    id: 'fixed',
    header: 'Fixed',
    size: 52,
    meta: { draggable: false } as never,
    cell: () => null,
  },
  {
    id: 'expand',
    header: 'Expand',
    size: 44,
    meta: { expandedContent: () => null } as never,
    cell: () => null,
  },
  { id: 'name', accessorKey: 'name', header: 'Name', size: 200 },
];

function Harness() {
  const table = useReactTable({
    data: ROWS,
    columns: COLUMNS,
    getRowId: (r) => r.id,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <DataGrid
      table={table}
      recordCount={ROWS.length}
      isLoading={false}
      tableLayout={{ width: 'fixed', columnsDraggable: true }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

function headerCell(label: string): HTMLTableCellElement {
  return screen.getByText(label).closest('th') as HTMLTableCellElement;
}

function hasGrip(th: HTMLTableCellElement): boolean {
  return Boolean(th.querySelector('svg.lucide-grip-vertical'));
}

function hasDragWrapper(th: HTMLTableCellElement): boolean {
  return Boolean(th.querySelector('[aria-label="Drag column to reorder"]'));
}

/** The ONE body row (`ROWS` carries one), by its own visible "Alpha" cell - its
 * siblings are the Fixed / Expand / Name cells in column-definition order. */
function bodyCells(): HTMLTableCellElement[] {
  const row = screen.getByText('Alpha').closest('tr') as HTMLTableRowElement;
  return Array.from(row.children) as HTMLTableCellElement[];
}

describe('AC-RS-69: no grip on a fixed-utility or expanded-content header', () => {
  it('meta.draggable === false renders no grip and no drag wrapper', () => {
    render(<Harness />);

    const th = headerCell('Fixed');
    expect(hasGrip(th)).toBe(false);
    expect(hasDragWrapper(th)).toBe(false);
  });

  it('a column carrying meta.expandedContent renders no grip and no drag wrapper', () => {
    render(<Harness />);

    const th = headerCell('Expand');
    expect(hasGrip(th)).toBe(false);
    expect(hasDragWrapper(th)).toBe(false);
  });
});

describe('AC-RS-69: the shared select column opts itself out of dragging', () => {
  it('buildSelectColumn sets meta.draggable = false', () => {
    const column = buildSelectColumn<Row>();

    expect((column.meta as { draggable?: boolean } | undefined)?.draggable).toBe(false);
  });
});

/**
 * S1 (fix round 2 review finding): `DataGridTableDndCell` called `useSortable` with no
 * `disabled` at all, unconditionally - the same fixed-utility / expanded-content columns
 * whose HEADER opts out of dragging above still had their own BODY cell register as an
 * ordinary sortable participant, which could drift the moment either predicate changed on
 * one side only. The fix hoists both checks onto one exported `isFixedUtilityColumn` and
 * hands its result to the cell's own `useSortable({ disabled })` too - surfaced here as
 * `aria-disabled` on the `<td>` (the attribute dnd-kit's own `useDraggable` sets from that
 * same `disabled` flag), so a fixed cell and a plain one are told apart in the DOM the
 * way the header's own grip already is.
 *
 * TEST-FIRST (fix round 2): before this fix EVERY body cell - fixed-utility, expanded-
 * content or plain - carried no `aria-disabled` at all, so a red here is "the Fixed/Expand
 * cell's own `aria-disabled` is missing", never a fixture bug.
 */
describe('S1: the body cell honours the SAME fixed-utility predicate as its header', () => {
  it('a draggable: false column\'s body cell carries aria-disabled, no sortable listeners', () => {
    render(<Harness />);

    const [fixedCell] = bodyCells();
    expect(fixedCell.getAttribute('aria-disabled')).toBe('true');
  });

  it('a column carrying meta.expandedContent also carries aria-disabled on its body cell', () => {
    render(<Harness />);

    const [, expandCell] = bodyCells();
    expect(expandCell.getAttribute('aria-disabled')).toBe('true');
  });

  it('a plain column\'s body cell keeps no aria-disabled - sorting stays enabled', () => {
    render(<Harness />);

    const [, , nameCell] = bodyCells();
    expect(nameCell.getAttribute('aria-disabled')).toBeNull();
  });
});
