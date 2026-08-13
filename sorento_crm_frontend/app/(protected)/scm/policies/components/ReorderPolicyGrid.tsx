'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Info, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardHeading, CardTable, CardToolbar } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { EM_DASH } from '../../lib/format';
import {
  useCreatePolicy,
  useDeletePolicy,
  useReorderPolicies,
  useUpdatePolicy,
} from '../hooks/usePolicies';
import {
  POLICY_TYPE_LABEL,
  SCOPE_TYPE_LABEL,
  safetyStockSummary,
} from '../lib/labels';
import type { ReorderPolicyRow, ReorderPolicyWrite } from '../types/policy.types';
import { AddEditPolicyModal } from './AddEditPolicyModal';

const SCOPE_BADGE: Record<ReorderPolicyRow['scope_type'], 'primary' | 'info' | 'secondary' | 'warning'> = {
  global: 'secondary',
  product_class: 'info',
  abc_xyz_cell: 'warning',
  sku: 'primary',
};

/** Trigger-threshold summary per policy type (novice-friendly). */
function triggerSummary(row: ReorderPolicyRow): string {
  if (row.policy_type === 'min_max') {
    const min = row.min_override != null ? row.min_override : '-';
    const max = row.max_override != null ? row.max_override : '-';
    return `Min ${min} / Max ${max}`;
  }
  if (row.policy_type === 'periodic_review') {
    return row.review_period_days != null ? `Every ${row.review_period_days}d` : '-';
  }
  return 'Reorder point';
}

export function ReorderPolicyGrid() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ReorderPolicyRow | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ReorderPolicyRow | null>(null);

  // Debounce the search input - server-side query (backend covers scope label +
  // product_code / name / category, not just the readable columns).
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  // Server-side paging / sorting / search - the backend GET /policies honours
  // page/limit/sort/dir/query, so nothing is truncated and search reaches fields
  // the grid never renders (product_code, name, category).
  const { data, isLoading, isError, error } = useReorderPolicies({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: debouncedSearch,
  });
  const createPolicy = useCreatePolicy();
  const updatePolicy = useUpdatePolicy();
  const deletePolicy = useDeletePolicy();

  const rows = useMemo<ReorderPolicyRow[]>(() => data?.data ?? [], [data]);
  const total = data?.total ?? 0;

  // Search / sort changes reset to the first page.
  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [debouncedSearch, sorting]);

  // Global-default empty hint (AC-LIST-4): the ONLY configured policy is global.
  const onlyGlobal = total === 1 && rows[0]?.scope_type === 'global';

  const columns = useMemo<ColumnDef<ReorderPolicyRow>[]>(
    () => [
      {
        accessorKey: 'scope_type',
        header: ({ column }) => <DataGridColumnHeader title="Scope" column={column} />,
        cell: ({ row }) => (
          <Badge variant={SCOPE_BADGE[row.original.scope_type]} appearance="light" size="md">
            {SCOPE_TYPE_LABEL[row.original.scope_type]}
          </Badge>
        ),
        size: 150,
        meta: { headerTitle: 'Scope', skeleton: <Skeleton className="h-6 w-24" /> },
      },
      {
        accessorKey: 'scope_label',
        header: ({ column }) => <DataGridColumnHeader title="Scope target" column={column} />,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.scope_label}>
            {row.original.scope_label}
          </span>
        ),
        size: 240,
        meta: { headerTitle: 'Scope target' },
      },
      {
        accessorKey: 'policy_type',
        header: ({ column }) => <DataGridColumnHeader title="Policy type" column={column} />,
        cell: ({ row }) => POLICY_TYPE_LABEL[row.original.policy_type],
        size: 150,
        meta: { headerTitle: 'Policy type' },
      },
      {
        id: 'safety_stock',
        header: ({ column }) => <DataGridColumnHeader title="Safety stock" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={safetyStockSummary(row.original.safety_stock_method, row.original.safety_days, row.original.service_level)}>
            {safetyStockSummary(row.original.safety_stock_method, row.original.safety_days, row.original.service_level)}
          </span>
        ),
        enableSorting: false,
        size: 160,
        meta: { headerTitle: 'Safety stock' },
      },
      {
        accessorKey: 'lead_time_default_days',
        header: ({ column }) => <DataGridColumnHeader title="Lead default" column={column} />,
        cell: ({ row }) =>
          row.original.lead_time_default_days != null ? (
            <span className="tabular-nums">{row.original.lead_time_default_days}d</span>
          ) : (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ),
        size: 120,
        meta: { headerTitle: 'Lead default', headerClassName: 'text-right', cellClassName: 'text-right' },
      },
      {
        id: 'triggers',
        header: ({ column }) => <DataGridColumnHeader title="Triggers" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm text-muted-foreground" title={triggerSummary(row.original)}>
            {triggerSummary(row.original)}
          </span>
        ),
        enableSorting: false,
        size: 160,
        meta: { headerTitle: 'Triggers' },
      },
      {
        accessorKey: 'priority',
        header: ({ column }) => <DataGridColumnHeader title="Priority" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.priority}</span>,
        size: 100,
        meta: { headerTitle: 'Priority', headerClassName: 'text-right', cellClassName: 'text-right' },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="success" appearance="light" size="md">
              Active
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="light" size="md">
              Inactive
            </Badge>
          ),
        size: 110,
        meta: { headerTitle: 'Active' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const isGlobal = row.original.scope_type === 'global';
          return (
            <div className="flex justify-end gap-1">
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                aria-label="Edit policy"
                title="Edit policy"
                onClick={() => {
                  setEditing(row.original);
                  setModalOpen(true);
                }}
              >
                <Pencil className="size-4" />
              </Button>
              {/* Global default is never deletable (AC-DEL-2). */}
              {!isGlobal ? (
                <Button
                  mode="icon"
                  variant="ghost"
                  size="sm"
                  aria-label="Delete policy"
                  title="Delete policy"
                  onClick={() => setDeleteTarget(row.original)}
                >
                  <Trash2 className="size-4 text-destructive" />
                </Button>
              ) : null}
            </div>
          );
        },
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    rowCount: total,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const submitPolicy = async (body: ReorderPolicyWrite) => {
    if (editing) {
      await updatePolicy.mutateAsync({ id: editing.id, body });
    } else {
      await createPolicy.mutateAsync(body);
    }
    setModalOpen(false);
    setEditing(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>
          Policies resolve most-specific-first: a SKU override beats an ABC-XYZ cell, which beats a
          product class, which beats the global default. <strong>Changes take effect on the next
          reorder run.</strong>
        </span>
      </div>

      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load reorder policies.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No reorder policies configured."
      >
        <Card>
          <CardHeader className="flex items-center justify-between gap-3">
            <CardHeading>
              <div className="relative">
                <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search scope or type..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-64 ps-9"
                />
                {searchQuery ? (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                    onClick={() => setSearchQuery('')}
                    aria-label="Clear search"
                  >
                    <X />
                  </Button>
                ) : null}
              </div>
            </CardHeading>
            <CardToolbar>
              <Button
                onClick={() => {
                  setEditing(null);
                  setModalOpen(true);
                }}
              >
                <Plus className="size-4" />
                Add policy
              </Button>
            </CardToolbar>
          </CardHeader>

          {onlyGlobal ? (
            <div className="border-b bg-muted/20 px-5 py-2.5 text-xs text-muted-foreground">
              Only the global default policy is configured. Add an override to tune specific SKUs,
              classes, or ABC-XYZ cells.
            </div>
          ) : null}

          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <AddEditPolicyModal
        open={modalOpen}
        onOpenChange={(o) => {
          setModalOpen(o);
          if (!o) setEditing(null);
        }}
        mode={editing ? 'edit' : 'create'}
        initial={editing}
        onSubmit={submitPolicy}
        isSubmitting={createPolicy.isPending || updatePolicy.isPending}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Confirm delete"
        description={
          <>
            This action cannot be undone. The{' '}
            <strong>{deleteTarget ? SCOPE_TYPE_LABEL[deleteTarget.scope_type] : ''}</strong> policy
            for <strong>{deleteTarget?.scope_label}</strong> will be permanently removed.
          </>
        }
        successMessage="Policy deleted"
        onDelete={async () => {
          if (deleteTarget) await deletePolicy.mutateAsync(deleteTarget.id);
        }}
        onSuccess={() => setDeleteTarget(null)}
      />
    </div>
  );
}
