'use client';

import { useMemo, useState } from 'react';
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
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import type { RecordAction } from '@/components/common/recordActions';
import { useTechnicianMutations, useTechnicians } from '../hooks/useTechnicians';
import type { Technician } from '../types/technician.types';
import TechnicianFormDialog from './TechnicianFormDialog';

const TYPE_LABEL: Record<string, string> = { employee: 'Employee', contractor: 'Contractor' };

interface TechnicianRow extends Technician {
  in_use?: boolean;
}

export default function TechniciansList() {
  const canManage = useHasPermission('complaint_management.technicians.manage');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const [form, setForm] = useState<{ open: boolean; technician: Technician | null }>({
    open: false,
    technician: null,
  });
  useResetPageOnFilterChange(setPagination, [searchQuery]);

  const { data, isLoading, isPlaceholderData, isFetching, refetch, error } = useTechnicians({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });
  const { create, update } = useTechnicianMutations();
  const remove = useDeferredRowAction({
    actionKey: 'technician.delete',
    entityType: 'technician',
    verb: 'Deleting',
    successMessage: 'Technician deleted.',
    invalidateKeys: [['technicians'], ['technicians-select']],
  });

  const actionsFor = (row: TechnicianRow): RecordAction[] => {
    if (!canManage) return [];
    const actions: RecordAction[] = [
      { key: 'edit', label: 'Edit', run: () => setForm({ open: true, technician: row }) },
    ];
    if (row.is_active) {
      actions.push({
        key: 'archive',
        label: 'Archive',
        run: () => update.mutate({ id: row.id, values: { is_active: false } }),
      });
    } else {
      actions.push({
        key: 'restore',
        label: 'Restore',
        run: () => update.mutate({ id: row.id, values: { is_active: true } }),
      });
    }
    // A technician on a job is archived, never deleted.
    if (!row.in_use) {
      actions.push({
        key: 'delete',
        label: 'Delete',
        kind: 'destructive',
        run: () => remove.run({ id: row.id, subject: row.name }),
      });
    }
    return actions;
  };

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
      {
        id: 'actions',
        header: '',
        size: 56,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        cell: ({ row }) =>
          canManage ? <RowActionsMenu actions={actionsFor(row.original)} ariaLabel="technician" /> : null,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canManage],
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
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        isPlaceholderData={isPlaceholderData}
        error={error}
        onRetry={() => void refetch()}
        onRowClick={canManage ? (row) => setForm({ open: true, technician: row }) : undefined}
        rowPending={(row) => remove.targetId === row.id}
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
