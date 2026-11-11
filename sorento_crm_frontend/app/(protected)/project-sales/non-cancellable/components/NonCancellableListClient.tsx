'use client';

import * as React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  NON_CANCELLABLE_RULES_KEY,
  useNonCancellableRules,
} from '../../_shared/hooks/useProjects';
import type { NonCancellableRule } from '../../_shared/types/project.types';
import { NonCancellableRuleDialog } from './NonCancellableRuleDialog';

const EDIT_PERMISSION = 'projects.types.edit';

/** What the rule applies TO, in words rather than a UUID. */
function targetOf(row: NonCancellableRule): string {
  if (row.product_code) {
    return row.product_name ? `${row.product_code} ${row.product_name}` : row.product_code;
  }
  return row.category_name ?? '-';
}

/** The company-wide defaults for lines outside any series: a product or a category. */
export function NonCancellableListClient() {
  const rules = useNonCancellableRules();
  const canEdit = useHasPermission(EDIT_PERMISSION);
  const [editing, setEditing] = React.useState<NonCancellableRule | 'new' | null>(null);
  const removal = useDeferredRowAction({
    actionKey: 'non_cancellable_rule.delete',
    entityType: 'non_cancellable_rule',
    verb: 'Deleting',
    successMessage: 'Item deleted',
    invalidateKeys: [NON_CANCELLABLE_RULES_KEY],
  });
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
  } = useDebouncedSearch();
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 15,
  });
  const [sorting, setSorting] = React.useState<SortingState>([]);

  const rows = React.useMemo(() => {
    const all = rules.data ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((row) => targetOf(row).toLowerCase().includes(needle));
  }, [rules.data, search]);

  const columns = React.useMemo<ColumnDef<NonCancellableRule>[]>(() => {
    const cols: ColumnDef<NonCancellableRule>[] = [
      {
        id: 'target',
        accessorFn: (row) => targetOf(row),
        header: ({ column }) => <DataGridColumnHeader title="Target" column={column} />,
        size: 300,
        meta: { headerTitle: 'Target', skeleton: <Skeleton className="h-4 w-40" /> },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={targetOf(row.original)}>
            {targetOf(row.original)}
          </span>
        ),
      },
      {
        id: 'type',
        accessorFn: (row) => (row.product_id ? 'Product' : 'Category'),
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 120,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => <span>{row.original.product_id ? 'Product' : 'Category'}</span>,
      },
      {
        accessorKey: 'non_cancellable',
        header: ({ column }) => <DataGridColumnHeader title="Non-cancellable" column={column} />,
        size: 150,
        meta: { headerTitle: 'Non-cancellable', skeleton: <Skeleton className="h-4 w-12" /> },
        cell: ({ row }) =>
          row.original.non_cancellable ? (
            <Badge variant="warning" appearance="light">
              Yes
            </Badge>
          ) : (
            <Badge variant="secondary">No</Badge>
          ),
      },
      {
        accessorKey: 'notes',
        header: ({ column }) => <DataGridColumnHeader title="Notes" column={column} />,
        size: 260,
        meta: { headerTitle: 'Notes', skeleton: <Skeleton className="h-4 w-40" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.notes ?? ''}>
            {row.original.notes || '-'}
          </span>
        ),
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated" column={column} />,
        size: 130,
        meta: { headerTitle: 'Updated', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.updated_at ? formatDateInMalaysia(row.original.updated_at) : '-'}
          </span>
        ),
      },
    ];
    if (canEdit) {
      cols.push({
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 60,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={`Delete ${targetOf(row.original)}`}
            disabled={removal.targetId === row.original.id}
            onClick={(event) => {
              event.stopPropagation();
              removal.run({ id: row.original.id, subject: targetOf(row.original) });
            }}
          >
            <Trash2 className="size-4 text-destructive" aria-hidden />
          </Button>
        ),
      });
    }
    return cols;
  }, [canEdit, removal]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  // The one offer this listing makes, in the toolbar only (#1335).
  const listPrimaryAction = canEdit ? (
    <Button onClick={() => setEditing('new')}>
      <Plus />
      Add item
    </Button>
  ) : undefined;

  return (
    <>
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={rules.isLoading}
        error={rules.error}
        onRetry={() => void rules.refetch()}
        onRowClick={canEdit ? (row: NonCancellableRule) => setEditing(row) : undefined}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        tableClassNames={{ edgeCell: 'px-5' }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  placeholder="Search items"
                  className="w-full sm:w-56 md:w-64"
                />
              }
              exportConfig={{ filename: 'non_cancellable_items_export.xlsx' }}
              onRefresh={() => void rules.refetch()}
              isRefreshing={rules.isFetching}
              primaryAction={listPrimaryAction}
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
      {removal.countdown}
      {editing && (
        <NonCancellableRuleDialog
          rule={editing === 'new' ? null : editing}
          onDone={() => setEditing(null)}
        />
      )}
    </>
  );
}
