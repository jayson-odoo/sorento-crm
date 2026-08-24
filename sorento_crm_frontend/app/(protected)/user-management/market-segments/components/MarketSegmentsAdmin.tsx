'use client';

import { useMemo, useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { toast } from 'sonner';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useMarketSegments, useMarketSegmentMutations } from '../hooks/useMarketSegments';
import { deleteMarketSegment, type MarketSegment } from '../services/marketSegmentService';

export default function MarketSegmentsAdmin() {
  const { data: segments = [], isLoading, isError } = useMarketSegments();
  const { create, update } = useMarketSegmentMutations();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<MarketSegment | null>(null);
  const [deleteCode, setDeleteCode] = useState<string | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [form, setForm] = useState({
    code: '',
    name: '',
    description: '',
    is_active: true,
    sort_order: '' as string | number,
    is_requestor_selectable: false,
  });

  function resetForm() {
    setForm({
      code: '',
      name: '',
      description: '',
      is_active: true,
      sort_order: '',
      is_requestor_selectable: false,
    });
    setEditing(null);
  }

  function openCreate() {
    resetForm();
    setDialogOpen(true);
  }

  function openEdit(row: MarketSegment) {
    setEditing(row);
    setForm({
      code: row.code,
      name: row.name,
      description: row.description ?? '',
      is_active: row.is_active,
      sort_order: row.sort_order ?? '',
      is_requestor_selectable: row.is_requestor_selectable,
    });
    setDialogOpen(true);
  }

  function save() {
    const sort = form.sort_order === '' ? undefined : Number(form.sort_order);
    if (form.sort_order !== '' && Number.isNaN(Number(form.sort_order))) return;
    if (editing) {
      update.mutate(
        {
          code: editing.code,
          body: {
            name: form.name.trim(),
            description: form.description.trim() || null,
            is_active: form.is_active,
            sort_order: sort,
            is_requestor_selectable: form.is_requestor_selectable,
          },
        },
        {
          onSuccess: () => {
            setDialogOpen(false);
            resetForm();
          },
        },
      );
    } else {
      if (!form.code.trim() || !form.name.trim()) {
        toast.error('Code and name are required');
        return;
      }
      create.mutate(
        {
          code: form.code.trim(),
          name: form.name.trim(),
          description: form.description.trim() || null,
          is_active: form.is_active,
          sort_order: sort ?? null,
          is_requestor_selectable: form.is_requestor_selectable,
        },
        {
          onSuccess: () => {
            setDialogOpen(false);
            resetForm();
          },
        },
      );
    }
  }

  const columns = useMemo<ColumnDef<MarketSegment>[]>(
    () => [
      buildSelectColumn<MarketSegment>(),
      {
        id: 'code',
        accessorFn: (row) => row.code,
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-4 w-20 font-mono" /> },
        cell: ({ row }) => (
          <span className="font-mono max-w-[140px] truncate block" title={row.original.code}>
            {row.original.code}
          </span>
        ),
      },
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => (
          <span className="max-w-[200px] truncate block" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'description',
        accessorFn: (row) => row.description,
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        size: 280,
        enableSorting: false,
        meta: { headerTitle: 'Description', skeleton: <Skeleton className="h-4 w-44" /> },
        cell: ({ row }) => (
          <span className="max-w-[240px] truncate block" title={row.original.description ?? undefined}>
            {row.original.description ?? '-'}
          </span>
        ),
      },
      {
        id: 'sort_order',
        accessorFn: (row) => row.sort_order ?? null,
        header: ({ column }) => <DataGridColumnHeader title="Sort order" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Sort order', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => <span>{row.original.sort_order ?? '-'}</span>,
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Active', skeleton: <Skeleton className="h-6 w-20" /> },
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="primary">Active</Badge>
          ) : (
            <Badge variant="secondary">Inactive</Badge>
          ),
      },
      {
        id: 'is_requestor_selectable',
        accessorFn: (row) => row.is_requestor_selectable,
        header: ({ column }) => (
          <DataGridColumnHeader title="Requestor picker" column={column} />
        ),
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Requestor picker', skeleton: <Skeleton className="h-6 w-24" /> },
        cell: ({ row }) =>
          row.original.is_requestor_selectable ? (
            <Badge variant="primary" appearance="light">
              Included
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="light">
              Excluded
            </Badge>
          ),
      },
      {
        id: 'actions',
        header: '',
        size: 120,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        cell: ({ row }) => (
          <div className="flex gap-2">
            <Button variant="ghost" size="icon" onClick={() => openEdit(row.original)} aria-label="Edit">
              <Pencil className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setDeleteCode(row.original.code)}
              aria-label="Delete"
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: segments,
    getRowId: (row) => row.code,
    state: {
      pagination: { pageIndex: 0, pageSize: 10 },
      rowSelection,
    },
    onRowSelectionChange: setRowSelection,
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <div className="space-y-6">
      {isError ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-destructive">
            Failed to load market segments. Please try again.
          </CardContent>
        </Card>
      ) : (
        <DataGrid
          table={table}
          recordCount={segments.length}
          isLoading={isLoading}
          emptyMessage="No market segments yet. Add one to get started."
          tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        >
          <Card>
            <CardHeader className="block">
              <DataGridListToolbar
                table={table}
                exportConfig={{ filename: 'market_segments_export.xlsx' }}
                primaryAction={
                  <Button onClick={openCreate}>
                    <Plus className="size-4 mr-2" />
                    Add segment
                  </Button>
                }
              />
            </CardHeader>
            <CardContent>
              <DataGridTable />
            </CardContent>
          </Card>
        </DataGrid>
      )}

      {/* Create / edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit market segment' : 'Add market segment'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="segment-code">Code</Label>
              <Input
                id="segment-code"
                value={form.code}
                onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                placeholder="e.g. retail"
                disabled={!!editing}
              />
              {editing && (
                <p className="text-xs text-muted-foreground">Code cannot be changed after creation.</p>
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="segment-name">Name</Label>
              <Input
                id="segment-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Retail"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="segment-desc">Description (optional)</Label>
              <Input
                id="segment-desc"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="segment-sort">Sort order (optional)</Label>
              <Input
                id="segment-sort"
                type="number"
                value={form.sort_order}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    sort_order: e.target.value === '' ? '' : Number(e.target.value),
                  }))
                }
                placeholder="0"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="segment-active"
                checked={form.is_active}
                onCheckedChange={(v) => setForm((f) => ({ ...f, is_active: v === true }))}
              />
              <Label htmlFor="segment-active">Active</Label>
            </div>
            <div className="flex items-start gap-2">
              <Checkbox
                id="segment-requestor-selectable"
                className="mt-0.5"
                checked={form.is_requestor_selectable}
                onCheckedChange={(v) =>
                  setForm((f) => ({ ...f, is_requestor_selectable: v === true }))
                }
              />
              <div className="grid gap-1">
                <Label htmlFor="segment-requestor-selectable">Include in requestor picker</Label>
                <p className="text-xs text-muted-foreground">
                  Contacts in this segment can be picked as the requester on a purchase
                  request, sponsorship form or stock inquiry.
                </p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={save}
              disabled={
                create.isPending ||
                update.isPending ||
                !form.name.trim() ||
                (!editing && !form.code.trim())
              }
            >
              {editing ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <ConfirmDeleteDialog
        open={!!deleteCode}
        onOpenChange={(open) => !open && setDeleteCode(null)}
        title="Confirm delete"
        description={
          <>
            Delete the market segment &quot;{deleteCode}&quot;? This action cannot be undone. A segment
            still assigned to any contact or team member cannot be deleted.
          </>
        }
        onDelete={async () => {
          if (deleteCode) await deleteMarketSegment(deleteCode);
        }}
        queryKeysToInvalidate={[['market-segments']]}
        successMessage="Market segment deleted"
        onSuccess={() => setDeleteCode(null)}
      />
    </div>
  );
}
