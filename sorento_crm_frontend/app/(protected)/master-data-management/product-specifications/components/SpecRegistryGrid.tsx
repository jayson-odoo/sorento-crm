'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MessageSquareText, Plus, Trash2, X } from 'lucide-react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Skeleton } from '@/components/ui/skeleton';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredBulkAction } from '@/hooks/useDeferredBulkAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { pendingEntityKey, usePendingEntityKeys } from '@/lib/pending-entity-store';
import { toast } from '@/lib/toast';
import { SpecKeyRowActions } from '../actions';
import { AddSpecificationDialog } from './AddSpecificationDialog';
import { TryPhraseDialog } from './TryPhraseDialog';
import { useKeysForProductQuery } from '../hooks/useKeysForProductQuery';
import { SPEC_REGISTRY_QUERY_KEY, useSpecRegistryQuery } from '../hooks/useSpecRegistryQuery';
import { filterSpecKeys } from '../lib/specRegistryFilter';
import { specTypeLabel } from '../lib/specTypeLabel';
import type { SpecRegistryKey } from '../types/productSpec.types';

/**
 * Every specification the system knows, one row each (AC-A.2).
 *
 * The list is 37 rows, ETag-cached and read whole (D9): filtering, and the
 * product-code narrowing, both run in the browser rather than round-tripping the
 * server on every keystroke. The toolbar reads structurally the same as the
 * Products list (D13): search, primary Add, secondary Actions, select column, row
 * "..." menu, bulk delete strip (D14).
 */
export function SpecRegistryGrid() {
  const router = useRouter();
  const canAdd = useHasPermission('master_data.spec_registry.add');
  const canDelete = useHasPermission('master_data.spec_registry.delete');
  const [adding, setAdding] = useState(false);
  const [trying, setTrying] = useState(false);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const { data: keys, isLoading, isError, error } = useSpecRegistryQuery();
  const {
    value: filter,
    setValue: setFilter,
    debouncedValue: debouncedFilter,
    isSettling,
  } = useDebouncedSearch();
  const { matchedCode, keys: productKeys, loading: probeLoading } =
    useKeysForProductQuery(debouncedFilter);

  // A matched product wins over word matching: the reader asked about a code, so
  // the answer is that code's specifications, not every key whose wording happens
  // to contain the digits. Shared with the record page's pager (D9) via
  // `filterSpecKeys`, so the two never disagree about what "the current list" is.
  const visible = useMemo(
    () => filterSpecKeys(keys ?? [], filter, productKeys),
    [keys, filter, productKeys],
  );

  const rowHref = useCallback(
    (row: SpecRegistryKey) => {
      const search = buildDetailSearch({
        pageIndex: 0,
        pageSize: Math.max(visible.length, 1),
        sorting: [{ id: 'label', desc: false }],
        searchQuery: filter,
      });
      return `/master-data-management/product-specifications/${row.spec_key}${
        search ? `?${search}` : ''
      }`;
    },
    [visible.length, filter],
  );

  const columns = useMemo<ColumnDef<SpecRegistryKey>[]>(
    () => [
      buildSelectColumn<SpecRegistryKey>({
        rowLabel: (row) => `Select ${row.original.label}`,
      }),
      {
        id: 'label',
        accessorFn: (row) => row.label,
        header: ({ column }) => <DataGridColumnHeader title="Specification" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Specification', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.label}>
            {row.original.label}
          </span>
        ),
      },
      {
        id: 'type',
        accessorFn: (row) => row.data_type,
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-5 w-16" /> },
        cell: ({ row }) => (
          <Badge variant="secondary" size="sm" appearance="light" shape="circle">
            {specTypeLabel(row.original.data_type, row.original.unit)}
          </Badge>
        ),
      },
      {
        id: 'values',
        accessorFn: (row) => row.allowed_values.length,
        header: ({ column }) => <DataGridColumnHeader title="Choices" column={column} />,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Choices', skeleton: <Skeleton className="h-4 w-8" /> },
        cell: ({ row }) => {
          // AC-S3.3: a number or a yes/no key has no choices to count.
          if (row.original.data_type === 'numeric' || row.original.data_type === 'boolean') {
            return <span className="text-muted-foreground">-</span>;
          }
          return <span className="tabular-nums">{row.original.allowed_values.length}</span>;
        },
      },
      {
        id: 'seen_in',
        accessorFn: (row) => row.measured_coverage ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Products" column={column} />,
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Products', skeleton: <Skeleton className="h-4 w-12" /> },
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.measured_coverage != null
              ? row.original.measured_coverage.toLocaleString()
              : '-'}
          </span>
        ),
      },
      // Code, Rules and Built in: available in the column chooser, hidden by
      // default (AC-S3.1). Not deleted - a maintainer can still switch them on.
      {
        id: 'code',
        accessorFn: (row) => row.spec_key,
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => (
          <span
            className="truncate font-mono text-xs text-muted-foreground"
            title={row.original.spec_key}
          >
            {row.original.spec_key}
          </span>
        ),
      },
      {
        id: 'rules',
        accessorFn: (row) => row.effective_rules.length,
        header: ({ column }) => <DataGridColumnHeader title="Rules" column={column} />,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Rules', skeleton: <Skeleton className="h-4 w-8" /> },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.effective_rules.length}</span>
        ),
      },
      {
        id: 'source',
        accessorFn: (row) => row.source,
        header: ({ column }) => <DataGridColumnHeader title="Built in" column={column} />,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Built in', skeleton: <Skeleton className="h-5 w-14" /> },
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {row.original.source === 'user' ? 'No' : 'Yes'}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => <SpecKeyRowActions specKey={row.original} />,
        size: 50,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    [],
  );

  // Code, Rules and Built in start hidden (AC-S3.1) - the column chooser (already
  // on this DataGrid) is where a maintainer switches one back on; the choice is
  // then persisted per viewer through the grid's own column preferences.
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({
    code: false,
    rules: false,
    source: false,
  });

  const table = useReactTable({
    columns,
    data: visible,
    getRowId: (row) => row.spec_key,
    state: {
      // Every key on one page (D9): this is a small vocabulary read whole, not a
      // feed paged through.
      pagination: { pageIndex: 0, pageSize: Math.max(visible.length, 1) },
      rowSelection,
      columnVisibility,
    },
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
  });

  // A specification whose deletion is counting down stays on the grid, dimmed,
  // until the window lapses (D7).
  const pendingKeys = usePendingEntityKeys();
  const rowPending = (row: SpecRegistryKey) =>
    pendingKeys.has(pendingEntityKey('spec_key', row.spec_key));

  // Bulk delete = one countdown over the user-made rows in the selection (D14). A
  // seed row ships with the product and would just reappear on the next deploy, so
  // it never enters the batch - the toast says how many were left out and why,
  // rather than the selection quietly shrinking with no explanation.
  const bulkDeletion = useDeferredBulkAction({
    actionKey: 'spec_key.delete',
    entityType: 'spec_key',
    describe: (count) => `${count} specification${count === 1 ? '' : 's'}`,
    invalidateKeys: [SPEC_REGISTRY_QUERY_KEY],
    onStarted: () => setRowSelection({}),
  });

  const handleBulkDelete = () => {
    const selectedKeys = table.getSelectedRowModel().rows.map((r) => r.original);
    const deletable = selectedKeys.filter((key) => key.source === 'user');
    const skipped = selectedKeys.length - deletable.length;
    if (skipped > 0) {
      toast.warning(
        `${skipped} skipped (shipped with the product)`,
      );
    }
    if (deletable.length === 0) return;
    bulkDeletion.run(deletable.map((key) => ({ id: key.spec_key })));
  };

  if (isError) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load the specifications.'}
      </div>
    );
  }

  // The one offer this listing makes, in both places it belongs: the toolbar, and
  // the empty state's next step.
  const listPrimaryAction = canAdd ? (
    <Button onClick={() => setAdding(true)}>
      <Plus className="size-4" aria-hidden />
      Add specification
    </Button>
  ) : undefined;

  return (
    <DataGrid
      table={table}
      recordCount={visible.length}
      isLoading={isLoading}
      rowHref={rowHref}
      rowPending={rowPending}
      listingKey="master_data.spec_registry.view"
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="No specifications match that search."
      emptyAction={listPrimaryAction}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <>
                <ListSearchInput
                  className="w-full sm:w-72"
                  value={filter}
                  onChange={setFilter}
                  isSettling={isSearchInFlight(isSettling, probeLoading, debouncedFilter)}
                  placeholder="Find a specification, word or product code"
                />
                {matchedCode && (
                  <div className="flex items-center gap-1.5">
                    <Badge variant="secondary" appearance="light" shape="circle" size="sm">
                      Specifications of {matchedCode}
                    </Badge>
                    <Button
                      type="button"
                      mode="icon"
                      size="sm"
                      variant="ghost"
                      aria-label={`Clear the ${matchedCode} filter`}
                      onClick={() => setFilter('')}
                    >
                      <X className="size-3.5" />
                    </Button>
                  </div>
                )}
              </>
            }
            primaryAction={listPrimaryAction}
            secondaryActions={[
              {
                key: 'try-phrase',
                label: 'Try a phrase',
                icon: MessageSquareText,
                onClick: () => setTrying(true),
              },
            ]}
            bulkActions={
              canDelete
                ? [
                    {
                      key: 'delete',
                      label: 'Delete selected',
                      icon: Trash2,
                      destructive: true,
                      onClick: handleBulkDelete,
                    },
                  ]
                : []
            }
          />
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
      </Card>
      <AddSpecificationDialog
        open={adding}
        onOpenChange={setAdding}
        onCreated={(specKey) =>
          router.push(`/master-data-management/product-specifications/${specKey}`)
        }
      />
      <TryPhraseDialog open={trying} onOpenChange={setTrying} />
    </DataGrid>
  );
}

export default SpecRegistryGrid;
