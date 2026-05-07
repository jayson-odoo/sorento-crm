'use client';

import { useMemo } from 'react';
import { Edit, Trash2, ChevronRight, Columns3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';
import type { ComplaintRootCause } from '../types/complaintRootCause.types';

interface Props {
  rows: ComplaintRootCause[];
  searchQuery?: string;
  onEdit?: (row: ComplaintRootCause) => void;
  onDelete?: (row: ComplaintRootCause) => void;
}

export default function ComplaintRootCauseTable({
  rows,
  searchQuery = '',
  onEdit,
  onDelete,
}: Props) {
  const filtered = useMemo(
    () =>
      rows.filter((r) =>
        r.name?.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [rows, searchQuery],
  );

  const columns = useMemo<ColumnDef<ComplaintRootCause>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 300,
        enableSorting: true,
        meta: { headerTitle: 'Name' },
        cell: ({ row }) => (
          <span className="font-medium truncate block">{row.original.name}</span>
        ),
      },
      {
        id: 'description',
        accessorFn: (row) => row.description,
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        size: 360,
        enableSorting: false,
        meta: { headerTitle: 'Description' },
        cell: ({ row }) => (
          <span
            className="text-muted-foreground truncate block"
            title={row.original.description ?? undefined}
          >
            {row.original.description ?? '—'}
          </span>
        ),
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 140,
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
        id: 'complaint_count',
        accessorFn: (row) => row.complaint_count ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Complaints" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Complaints' },
        cell: ({ row }) => (
          <Badge variant="secondary" size="sm" className="shrink-0 w-fit">
            {row.original.complaint_count ?? 0}
          </Badge>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 140,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onEdit?.(row.original);
              }}
              title="Edit"
            >
              <Edit className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onDelete?.(row.original);
              }}
              title="Delete"
            >
              <Trash2 className="size-4" />
            </Button>
            <ChevronRight className="text-muted-foreground/70 size-3.5 shrink-0" />
          </div>
        ),
      },
    ],
    [onEdit, onDelete],
  );

  const table = useReactTable({
    columns,
    data: filtered,
    getRowId: (row) => row.id,
    state: { pagination: { pageIndex: 0, pageSize: 10 } },
    getCoreRowModel: getCoreRowModel(),
  });

  if (filtered.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-4">No root causes found</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <DataGrid
        table={table}
        recordCount={filtered.length}
        isLoading={false}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <div className="mb-3 flex items-center justify-end">
          <DataGridColumnVisibility
            table={table}
            trigger={
              <Button variant="outline" size="sm" className="gap-1">
                <Columns3 className="size-4" />
                Columns
              </Button>
            }
          />
        </div>
        <DataGridTable />
      </DataGrid>
    </div>
  );
}
