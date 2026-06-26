'use client';

import type { ColumnDef, Row, Table } from '@tanstack/react-table';
import { Checkbox } from '@/components/ui/checkbox';

/**
 * Standard row-selection column for DataGrid lists.
 *
 * Every list that supports bulk actions / export-of-selection MUST use this
 * instead of a hand-rolled `useState<Set<string>>` selection. It binds to
 * react-table's built-in `rowSelection` state so the canonical toolbar
 * (`DataGridListToolbar`) can read selection uniformly for the bulk strip,
 * the "select all N records" banner, and selection-gated export.
 *
 * Requires the table to be created with `enableRowSelection: true` and a
 * stable `getRowId`. Read selected ids via `selectedRowIds(table)`.
 */
export function buildSelectColumn<TData>(options?: {
  /** Disable per-row selection for some rows (e.g. locked records). */
  enableRow?: (row: Row<TData>) => boolean;
  size?: number;
}): ColumnDef<TData> {
  const size = options?.size ?? 44;
  return {
    id: 'select',
    header: ({ table }: { table: Table<TData> }) => (
      <Checkbox
        checked={
          table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && 'indeterminate')
        }
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        aria-label="Select all rows on this page"
      />
    ),
    cell: ({ row }: { row: Row<TData> }) => (
      <Checkbox
        checked={row.getIsSelected()}
        disabled={!row.getCanSelect()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label="Select row"
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      />
    ),
    enableSorting: false,
    enableHiding: false,
    enableResizing: false,
    size,
    ...(options?.enableRow ? { enableRowSelection: options.enableRow } : {}),
  };
}

/** Ids of currently-selected rows (page-scope), using the table's `getRowId`. */
export function selectedRowIds<TData>(table: Table<TData>): string[] {
  return table.getSelectedRowModel().rows.map((r) => r.id);
}
