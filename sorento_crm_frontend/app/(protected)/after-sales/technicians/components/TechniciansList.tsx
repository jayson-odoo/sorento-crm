'use client';

import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { listUrlSearch } from '../../service-jobs/lib/listUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useTechnicianMutations, useTechnicians } from '../hooks/useTechnicians';
import type { Technician } from '../types/technician.types';
import TechnicianFormDialog from './TechnicianFormDialog';

const TYPE_LABEL: Record<string, string> = { employee: 'Employee', contractor: 'Contractor' };

interface TechnicianRow extends Technician {
  in_use?: boolean;
}

export default function TechniciansList() {
  const canManage = useHasPermission('after_sales.technicians.manage');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearchQuery,
  } = useDebouncedSearch();
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting.length ? state.sorting : [{ id: 'name', desc: false }]);
    resetSearchQuery(state.searchQuery);
    setTypeFilter(splitMulti(state.filters.employment_type));
    setStatusFilter(splitMulti(state.filters.is_active));
  });
  const [form, setForm] = useState<{ open: boolean; technician: Technician | null }>({
    open: false,
    technician: null,
  });
  useResetPageOnFilterChange(setPagination, [searchQuery, typeFilter.join(','), statusFilter.join(',')]);
  // All list state lives in the address, so Back restores it.
  useEffect(() => {
    const next = listUrlSearch(window.location.search, {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      filters: {
        employment_type: typeFilter.length ? joinMulti(typeFilter) : undefined,
        is_active: statusFilter.length ? joinMulti(statusFilter) : undefined,
      },
    });
    if (next !== window.location.search.replace(/^\?/, '')) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}?${next}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.pageIndex, pagination.pageSize, sorting, searchQuery, typeFilter.join(','), statusFilter.join(',')]);
  const filtersActiveCount = (typeFilter.length ? 1 : 0) + (statusFilter.length ? 1 : 0);

  const { data, isLoading, isPlaceholderData, isFetching, refetch, error } = useTechnicians({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    employment_type: typeFilter,
    is_active: statusFilter,
  });
  const { create, update } = useTechnicianMutations();
  const remove = useDeferredRowAction({
    actionKey: 'technician.delete',
    entityType: 'technician',
    verb: 'Deleting',
    successMessage: 'Technician deleted.',
    invalidateKeys: [['technicians'], ['technicians-select']],
  });

  const [menuRow, setMenuRow] = useState<TechnicianRow | null>(null);

  const columns = useMemo<ColumnDef<TechnicianRow>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (r) => r.name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 240,
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'phone',
        accessorFn: (r) => r.phone,
        header: ({ column }) => <DataGridColumnHeader title="Phone" column={column} />,
        size: 180,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.phone ?? undefined}>
            {row.original.phone || '-'}
          </span>
        ),
        meta: { headerTitle: 'Phone', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'employment_type',
        accessorFn: (r) => r.employment_type,
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 140,
        cell: ({ row }) => TYPE_LABEL[row.original.employment_type ?? ''] ?? '-',
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'is_active',
        accessorFn: (r) => r.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 120,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} size="sm">
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        meta: { headerTitle: 'Active', skeleton: <Skeleton className="h-4 w-16" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: (data?.data as TechnicianRow[]) || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
  });

  return (
    <>
      <ContextMenu modal={false}>
        <ContextMenuTrigger asChild>
          <div
            onContextMenuCapture={(event) => {
              const rowEl = (event.target as Element).closest('[data-technician-id]');
              const row = ((data?.data as TechnicianRow[]) ?? []).find(
                (t) => t.id === rowEl?.getAttribute('data-technician-id'),
              );
              if (!row || !canManage) {
                event.stopPropagation();
                return;
              }
              setMenuRow(row);
            }}
          >
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        isPlaceholderData={isPlaceholderData}
        error={error}
        onRetry={() => void refetch()}
        onRowClick={canManage ? (row) => setForm({ open: true, technician: row }) : undefined}
        rowPending={(row) => remove.targetId === row.id}
        rowAttributes={(row) => ({ 'data-technician-id': row.id })}
        emptyMessage="No technicians"
        standardToolbar={false}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                  placeholder="Search technicians..."
                  className="w-64"
                />
              }
              filters={{
                kind: 'custom',
                active: filtersActiveCount > 0,
                activeCount: filtersActiveCount,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label>Type</Label>
                      <SearchableMultiSelect
                        value={typeFilter}
                        onChange={setTypeFilter}
                        options={[
                          { value: 'employee', label: 'Employee' },
                          { value: 'contractor', label: 'Contractor' },
                        ]}
                        placeholder="All types"
                        triggerClassName="mt-1"
                        clearable
                      />
                    </div>
                    <div>
                      <Label>Status</Label>
                      <SearchableMultiSelect
                        value={statusFilter}
                        onChange={setStatusFilter}
                        options={[
                          { value: 'true', label: 'Active' },
                          { value: 'false', label: 'Inactive' },
                        ]}
                        placeholder="All statuses"
                        triggerClassName="mt-1"
                        clearable
                      />
                    </div>
                  </div>
                ),
              }}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
              primaryAction={
                canManage ? (
                  <Button onClick={() => setForm({ open: true, technician: null })}>
                    <Plus />
                    Create
                  </Button>
                ) : undefined
              }
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent className="w-48">
          {menuRow && (
            <>
              <ContextMenuItem onSelect={() => setForm({ open: true, technician: menuRow })}>Edit</ContextMenuItem>
              <ContextMenuItem
                onSelect={() => update.mutate({ id: menuRow.id, values: { is_active: !menuRow.is_active } })}
              >
                {menuRow.is_active ? 'Archive' : 'Restore'}
              </ContextMenuItem>
              {/* A technician on a job is archived, never deleted. */}
              {!menuRow.in_use && (
                <>
                  <ContextMenuSeparator />
                  <ContextMenuItem
                    className="text-destructive"
                    onSelect={() => remove.run({ id: menuRow.id, subject: menuRow.name })}
                  >
                    Delete
                  </ContextMenuItem>
                </>
              )}
            </>
          )}
        </ContextMenuContent>
      </ContextMenu>
      <TechnicianFormDialog
        open={form.open}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        technician={form.technician}
        isSubmitting={create.isPending || update.isPending}
        onSubmit={async (values) => {
          try {
            if (form.technician) {
              await update.mutateAsync({ id: form.technician.id, values });
            } else {
              await create.mutateAsync(values);
            }
            setForm({ open: false, technician: null });
          } catch {
            /* the mutation toasts the server's message */
          }
        }}
      />
    </>
  );
}
