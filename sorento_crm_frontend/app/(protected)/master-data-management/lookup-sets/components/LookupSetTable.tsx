'use client';

import { useMemo } from 'react';
import { Edit } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';
import type { LookupSet } from '../types/lookup.types';

interface LookupSetTableProps {
  rows: LookupSet[];
  onView: (s: LookupSet) => void;
  onEdit: (s: LookupSet) => void;
}

export default function LookupSetTable({ rows, onView, onEdit }: LookupSetTableProps) {
  const columns = useMemo<ColumnDef<LookupSet>[]>(
    () => [
      {
        id: 'set_key',
        accessorFn: (row) => row.set_key,
        header: ({ column }) => <DataGridColumnHeader title="Set key" column={column} />,
        size: 280,
        enableSorting: true,
        meta: { headerTitle: 'Set key' },
        cell: ({ row }) => (
          <span
            className="font-mono text-xs truncate block"
            title={row.original.set_key}
          >
            {row.original.set_key}
          </span>
        ),
      },
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 320,
        enableSorting: true,
        meta: { headerTitle: 'Name' },
        cell: ({ row }) => (
          <span className="font-medium truncate block" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'option_count',
        accessorFn: (row) => row.option_count,
        header: ({ column }) => <DataGridColumnHeader title="Options" column={column} />,
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Options' },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.option_count}</span>
        ),
      },
      {
        id: 'binding_count',
        accessorFn: (row) => row.binding_count,
        header: ({ column }) => <DataGridColumnHeader title="Bindings" column={column} />,
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Bindings' },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.binding_count}</span>
        ),
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Active' },
        cell: ({ row }) => (
          <Badge
            variant={row.original.is_active ? 'success' : 'secondary'}
            size="sm"
            appearance="ghost"
            className="shrink-0"
          >
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 80,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => (
          <div className="flex items-center justify-end">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onEdit(row.original);
              }}
              title="Edit"
              aria-label="Edit"
            >
              <Edit className="size-4" />
            </Button>
          </div>
        ),
      },
    ],
    [onEdit],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
  });

  if (!rows.length) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        No lookup sets yet. Click &quot;Add lookup set&quot; to create one.
      </div>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      onRowClick={(row) => onView(row as LookupSet)}
    >
      <DataGridTable />
    </DataGrid>
  );
}
