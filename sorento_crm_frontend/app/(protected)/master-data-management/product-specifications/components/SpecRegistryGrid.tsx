'use client';

import { useCallback, useMemo } from 'react';
import { X } from 'lucide-react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Skeleton } from '@/components/ui/skeleton';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useKeysForProductQuery } from '../hooks/useKeysForProductQuery';
import { useSpecRegistryQuery } from '../hooks/useSpecRegistryQuery';
import { filterSpecKeys } from '../lib/specRegistryFilter';
import { specTypeLabel } from '../lib/specTypeLabel';
import type { SpecRegistryKey } from '../types/productSpec.types';

/**
 * Every specification the system knows, one row each (AC-A.2).
 *
 * The list is 37 rows, ETag-cached and read whole (D9): filtering, and the
 * product-code narrowing, both run in the browser rather than round-tripping the
 * server on every keystroke.
 */
export function SpecRegistryGrid() {
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
      {
        id: 'label',
        accessorFn: (row) => row.label,
        header: ({ column }) => <DataGridColumnHeader title="Label" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Label', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.label}>
            {row.original.label}
          </span>
        ),
      },
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
        id: 'type',
        accessorFn: (row) => row.data_type,
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-5 w-16" /> },
        cell: ({ row }) => (
          <Badge variant="secondary" size="sm" appearance="light" shape="circle">
            {specTypeLabel(row.original.data_type)}
          </Badge>
        ),
      },
      {
        id: 'unit',
        accessorFn: (row) => row.unit ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Unit" column={column} />,
        size: 80,
        enableSorting: false,
        meta: { headerTitle: 'Unit', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => (
          <span className="text-muted-foreground">{row.original.unit ?? '-'}</span>
        ),
      },
      {
        id: 'values',
        accessorFn: (row) => row.allowed_values.length,
        header: ({ column }) => <DataGridColumnHeader title="Values" column={column} />,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Values', skeleton: <Skeleton className="h-4 w-8" /> },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.allowed_values.length}</span>
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
        id: 'seen_in',
        accessorFn: (row) => row.measured_coverage ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Seen in" column={column} />,
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Seen in', skeleton: <Skeleton className="h-4 w-12" /> },
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.measured_coverage != null
              ? row.original.measured_coverage.toLocaleString()
              : '-'}
          </span>
        ),
      },
      {
        id: 'source',
        accessorFn: (row) => row.source,
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Source', skeleton: <Skeleton className="h-5 w-14" /> },
        cell: ({ row }) => (
          <Badge
            variant={row.original.source === 'user' ? 'primary' : 'secondary'}
            size="sm"
            appearance="light"
            shape="circle"
          >
            {row.original.source === 'user' ? 'User' : 'Seed'}
          </Badge>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: visible,
    getRowId: (row) => row.spec_key,
    state: {
      // Every key on one page (D9): this is a small vocabulary read whole, not a
      // feed paged through.
      pagination: { pageIndex: 0, pageSize: Math.max(visible.length, 1) },
    },
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isError) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load the specifications.'}
      </div>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={visible.length}
      isLoading={isLoading}
      rowHref={rowHref}
      listingKey="master_data.spec_registry.view"
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="No specifications match that search."
    >
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
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
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                aria-label={`Clear the ${matchedCode} filter`}
                onClick={() => setFilter('')}
              >
                <X className="size-3.5" />
              </button>
            </div>
          )}
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
      </Card>
    </DataGrid>
  );
}

export default SpecRegistryGrid;
