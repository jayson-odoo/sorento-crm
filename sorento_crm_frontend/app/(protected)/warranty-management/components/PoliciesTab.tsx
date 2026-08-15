'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { Layers, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardFooter,
  CardHeader,
  CardTable,
} from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useCompany } from '@/app/providers/CompanyProvider';
import {
  useCreatePolicy,
  useDeletePolicy,
  usePolicies,
  useSupersedePolicy,
  useUpdatePolicy,
} from '../hooks/useWarrantyConfig';
import {
  POLICY_LIFECYCLE_BADGE,
  POLICY_LIFECYCLE_LABEL,
  formatCivilDate,
  policyLifecycle,
} from '../lib/warrantyLabels';
import type { WarrantyPolicyRow, WarrantyPolicyWrite } from '../types/warranty-config.types';
import { PolicyFormDialog, type PolicyDialogMode } from './PolicyFormDialog';
import { ScopeBadge } from './ScopeBadge';

export function PoliciesTab() {
  const router = useRouter();
  const { activeCompany } = useCompany();

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  const [dialogMode, setDialogMode] = useState<PolicyDialogMode | null>(null);
  const [target, setTarget] = useState<WarrantyPolicyRow | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WarrantyPolicyRow | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [debouncedSearch]);

  const { data, isLoading, isError, error, refetch, isFetching } = usePolicies({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: debouncedSearch,
  });

  const createPolicy = useCreatePolicy();
  const updatePolicy = useUpdatePolicy();
  const supersede = useSupersedePolicy();
  const deletePolicy = useDeletePolicy();

  const rows = useMemo<WarrantyPolicyRow[]>(() => data?.data ?? [], [data]);
  // AC-P14: `ListResponse[T]` puts the count under `pagination`, not at the root.
  const total = data?.pagination.total ?? 0;

  const openDialog = (mode: PolicyDialogMode, row: WarrantyPolicyRow | null) => {
    setFormError(null);
    setTarget(row);
    setDialogMode(mode);
  };

  const submit = async (body: WarrantyPolicyWrite) => {
    setFormError(null);
    try {
      if (dialogMode === 'edit' && target) {
        await updatePolicy.mutateAsync({ id: target.id, body });
      } else if (dialogMode === 'supersede' && target) {
        await supersede.mutateAsync({ id: target.id, body });
      } else {
        await createPolicy.mutateAsync(body);
      }
      setDialogMode(null);
      setTarget(null);
    } catch (e) {
      // AC-P2 / AC-P2b: the overlap refusal names the other version and its range,
      // and it belongs beside the dates the admin must change, not in a toast that
      // has already gone by the time they look.
      setFormError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const columns = useMemo<ColumnDef<WarrantyPolicyRow>[]>(
    () => [
      {
        id: 'version',
        accessorFn: (row) => row.version,
        header: ({ column }) => <DataGridColumnHeader title="Version" column={column} />,
        size: 140,
        meta: { headerTitle: 'Version' },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.version}>
            {row.original.version}
          </span>
        ),
      },
      {
        id: 'effective_from',
        accessorFn: (row) => row.effective_from,
        header: ({ column }) => <DataGridColumnHeader title="Effective from" column={column} />,
        size: 150,
        meta: { headerTitle: 'Effective from' },
        cell: ({ row }) => (
          <span className="tabular-nums">{formatCivilDate(row.original.effective_from)}</span>
        ),
      },
      {
        id: 'effective_to',
        accessorFn: (row) => row.effective_to,
        header: ({ column }) => <DataGridColumnHeader title="Effective to" column={column} />,
        size: 150,
        meta: { headerTitle: 'Effective to' },
        cell: ({ row }) =>
          row.original.effective_to ? (
            <span className="tabular-nums">{formatCivilDate(row.original.effective_to)}</span>
          ) : (
            <span className="text-muted-foreground">Open ended</span>
          ),
      },
      {
        id: 'lifecycle',
        accessorFn: (row) => policyLifecycle(row),
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Status' },
        cell: ({ row }) => {
          const state = policyLifecycle(row.original);
          return (
            <Badge variant={POLICY_LIFECYCLE_BADGE[state]} appearance="light" size="md">
              {POLICY_LIFECYCLE_LABEL[state]}
            </Badge>
          );
        },
      },
      {
        id: 'term_count',
        accessorFn: (row) => row.term_count,
        header: ({ column }) => <DataGridColumnHeader title="Terms" column={column} />,
        size: 110,
        // The backend sorts by `{version, effective_from, effective_to,
        // created_at}` only; anything else falls back to `effective_from DESC`.
        // A header that looks sortable and silently reorders nothing is worse
        // than no header control at all.
        enableSorting: false,
        meta: { headerTitle: 'Terms', headerClassName: 'text-right', cellClassName: 'text-right' },
        cell: ({ row }) =>
          row.original.term_count === 0 ? (
            <Badge variant="warning" appearance="light" size="md">
              None
            </Badge>
          ) : (
            <span className="tabular-nums">{row.original.term_count}</span>
          ),
      },
      {
        id: 'source_document',
        accessorFn: (row) => row.source_attachment_name,
        header: ({ column }) => <DataGridColumnHeader title="Source document" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Source document' },
        cell: ({ row }) =>
          row.original.source_attachment_name ? (
            <span className="block truncate" title={row.original.source_attachment_name}>
              {row.original.source_attachment_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Not attached</span>
          ),
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 140,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Supersede"
              aria-label="Supersede policy"
              onClick={(e) => {
                e.stopPropagation();
                openDialog('supersede', row.original);
              }}
            >
              <Layers className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Edit"
              aria-label="Edit policy"
              onClick={(e) => {
                e.stopPropagation();
                openDialog('edit', row.original);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Delete"
              aria-label="Delete policy"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(row.original);
              }}
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
    data: rows,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
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

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <ScopeBadge scope={{ kind: 'company', name: activeCompany?.name ?? 'No company selected' }} />
      </div>

      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load warranty policies.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        listingKey="warranty.policies.view"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={
          isError
            ? 'Policies could not be loaded.'
            : 'No warranty policies yet. Add one to start recording what is covered.'
        }
        onRowClick={(row) =>
          router.push(`/warranty-management/policies/${(row as WarrantyPolicyRow).id}`)
        }
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              onRefresh={async () => {
                await refetch();
              }}
              isRefreshing={isFetching}
              exportConfig={false}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search version..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-56 ps-9"
                    aria-label="Search policies"
                  />
                  {searchQuery ? (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 size-6 -translate-y-1/2"
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                    >
                      <X />
                    </Button>
                  ) : null}
                </div>
              }
              primaryAction={
                <Button onClick={() => openDialog('create', null)}>
                  <Plus className="size-4" /> Add policy
                </Button>
              }
            />
          </CardHeader>
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

      <PolicyFormDialog
        open={dialogMode !== null}
        onOpenChange={(o) => {
          if (!o) {
            setDialogMode(null);
            setTarget(null);
            setFormError(null);
          }
        }}
        mode={dialogMode ?? 'create'}
        initial={dialogMode === 'edit' ? target : null}
        incumbent={dialogMode === 'supersede' ? target : null}
        onSubmit={submit}
        isSubmitting={createPolicy.isPending || updatePolicy.isPending || supersede.isPending}
        error={formError}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Confirm delete"
        description={
          <>
            This action cannot be undone. Policy <strong>{deleteTarget?.version}</strong> will be
            permanently removed
            {deleteTarget && deleteTarget.term_count > 0 ? (
              <>
                {' '}
                along with the <strong>{deleteTarget.term_count}</strong> term
                {deleteTarget.term_count === 1 ? '' : 's'} published under it
              </>
            ) : (
              <>. It has no terms under it</>
            )}
            .
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
