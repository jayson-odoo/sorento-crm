'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Search, Edit, Trash2, ChevronRight } from 'lucide-react';
import {
  useReactTable,
  getCoreRowModel,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { useComplaintRootCauses } from '../hooks/useComplaintRootCauses';
import ComplaintRootCauseTable from './ComplaintRootCauseTable';
import ComplaintRootCauseFormDialog from './ComplaintRootCauseFormDialog';
import ComplaintRootCauseDeleteDialog from './ComplaintRootCauseDeleteDialog';
import { LinkedComplaintsChip } from '../../_shared/LinkedComplaintsChip';
import type { ComplaintRootCause } from '../types/complaintRootCause.types';

export default function ComplaintRootCausesList() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | undefined>(undefined);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [rowToDelete, setRowToDelete] = useState<ComplaintRootCause | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading } = useComplaintRootCauses({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'name', desc: false }],
    searchQuery: '',
  });
  const rows = useMemo<ComplaintRootCause[]>(() => data?.data ?? [], [data]);

  // Client-side name filter (preserves prior child behavior).
  const filtered = useMemo(
    () => rows.filter((r) => r.name?.toLowerCase().includes(searchQuery.toLowerCase())),
    [rows, searchQuery],
  );

  const handleEdit = (row: ComplaintRootCause) => {
    setEditingId(row.id);
    setFormOpen(true);
  };

  const handleDelete = (row: ComplaintRootCause) => {
    setRowToDelete(row);
    setDeleteDialogOpen(true);
  };

  const handleFormClose = (open: boolean) => {
    setFormOpen(open);
    if (!open) setEditingId(undefined);
  };

  const columns = useMemo<ColumnDef<ComplaintRootCause>[]>(
    () => [
      buildSelectColumn<ComplaintRootCause>(),
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
            {row.original.description ?? '-'}
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
          <LinkedComplaintsChip
            rootCauseId={row.original.id}
            label={row.original.name}
            count={row.original.complaint_count ?? 0}
            detailHref={`/complaint-management/complaint-root-causes/${row.original.id}`}
          />
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
                handleEdit(row.original);
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
                handleDelete(row.original);
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
    [],
  );

  const table = useReactTable({
    columns,
    data: filtered,
    getRowId: (row) => row.id,
    state: { rowSelection },
    columnResizeMode: 'onChange',
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    enableRowSelection: true,
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={filtered.length}
        isLoading={isLoading}
        onRowClick={(row) =>
          router.push(`/complaint-management/complaint-root-causes/${row.id}`)
        }
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search root causes..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="ps-9 w-64"
                  />
                </div>
              }
              exportConfig={{ filename: 'complaint_root_causes_export.xlsx' }}
              primaryAction={
                <Button
                  onClick={() => {
                    setEditingId(undefined);
                    setFormOpen(true);
                  }}
                >
                  <Plus className="size-4" />
                  Add Root Cause
                </Button>
              }
            />
          </CardHeader>
          <CardTable>
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground">
                Loading root causes...
              </div>
            ) : (
              <ScrollArea>
                <ComplaintRootCauseTable isEmpty={filtered.length === 0} />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            )}
          </CardTable>
        </Card>
      </DataGrid>

      <ComplaintRootCauseFormDialog
        open={formOpen}
        onOpenChange={handleFormClose}
        rowId={editingId}
      />

      {rowToDelete && (
        <ComplaintRootCauseDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => {
            setDeleteDialogOpen(false);
            setRowToDelete(null);
          }}
          row={rowToDelete}
        />
      )}
    </>
  );
}
