'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
} from '@tanstack/react-table';
import { RefreshCw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import { useSpecKeyProductsQuery } from '../../hooks/useSpecKeyProductsQuery';
import { useSpecRegistryMutations } from '../../hooks/useSpecRegistryMutations';
import type { SpecKeyProduct } from '../../services/productSpecService';

/** Where a value came from, in the words the person reading this uses. */
const SOURCE_LABEL: Record<string, string> = {
  derived: 'Description',
  flyer: 'Flyer',
  code: 'Product code',
  category: 'Category',
  human: 'Set by hand',
};

const PAGE_SIZE = 25;

/**
 * Every product carrying this specification, and the words each value was read
 * from (AC-B.5). Replaces the hand-rolled `SpecKeyProducts` table and its own
 * Prev/Next pager with the shared `DataGrid` + `DataGridPagination` (D10, G.2).
 */
export function SeenInProductsTab({
  specKey,
  label,
}: {
  specKey: string;
  label: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const canEdit = useHasPermission('master_data.spec_registry.edit');
  const { reread } = useSpecRegistryMutations();
  const [valueFilter, setValueFilter] = useState<string | undefined>();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: PAGE_SIZE,
  });
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: query,
    isSettling,
  } = useDebouncedSearch();

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [query, valueFilter]);

  const { data, isLoading, isFetching } = useSpecKeyProductsQuery(specKey, {
    value: valueFilter,
    q: query || undefined,
    limit: pagination.pageSize,
    offset: pagination.pageIndex * pagination.pageSize,
  });

  const products = data?.products ?? [];
  const total = data?.total ?? 0;

  const openProduct = (row: SpecKeyProduct) => {
    const back = `${pathname}`;
    router.push(
      `/master-data-management/products/${row.id}?tab=specifications&back=${encodeURIComponent(back)}`,
    );
  };

  const columns = useMemo<ColumnDef<SpecKeyProduct>[]>(
    () => [
      {
        accessorKey: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 140,
        meta: { headerTitle: 'Code' },
        cell: ({ row }) => (
          <span className="truncate font-mono text-xs" title={row.original.product_code}>
            {row.original.product_code}
          </span>
        ),
      },
      {
        accessorKey: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        size: 260,
        meta: { headerTitle: 'Description' },
        cell: ({ row }) => (
          <span className="truncate" title={row.original.description ?? ''}>
            {row.original.description ?? '-'}
          </span>
        ),
      },
      {
        accessorKey: 'class',
        header: ({ column }) => <DataGridColumnHeader title="Class" column={column} />,
        size: 140,
        meta: { headerTitle: 'Class' },
        cell: ({ row }) => (
          <span className="truncate text-muted-foreground" title={row.original.class ?? ''}>
            {row.original.class ?? '-'}
          </span>
        ),
      },
      {
        accessorKey: 'value',
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        size: 130,
        meta: { headerTitle: 'Value' },
        cell: ({ row }) => (
          <span className="truncate font-mono text-xs" title={String(row.original.value ?? '')}>
            {String(row.original.value ?? '-')}
          </span>
        ),
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        size: 130,
        meta: { headerTitle: 'Source' },
        cell: ({ row }) => (
          <span className="truncate text-muted-foreground">
            {SOURCE_LABEL[String(row.original.source)] ?? row.original.source ?? '-'}
          </span>
        ),
      },
      {
        accessorKey: 'evidence',
        header: ({ column }) => <DataGridColumnHeader title="Evidence" column={column} />,
        size: 220,
        meta: { headerTitle: 'Evidence' },
        cell: ({ row }) => (
          <span
            className="truncate font-mono text-xs text-muted-foreground"
            title={row.original.evidence ?? ''}
          >
            {row.original.evidence ?? '-'}
          </span>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: products,
    getRowId: (row) => row.id,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    state: { pagination },
    onPaginationChange: setPagination,
    manualPagination: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const emptyState = (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <p className="text-sm font-medium">Not seen on any product yet</p>
      {canEdit && (
        <Button
          size="sm"
          variant="outline"
          disabled={reread.isPending}
          onClick={() => reread.mutate()}
        >
          <RefreshCw className="size-4" aria-hidden />
          Reread catalogue
        </Button>
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-3">
      {data && (data.by_value.length > 0 || data.by_class.length > 0 || data.by_source.length > 0) && (
        <div className="flex flex-col gap-1.5 text-xs">
          {data.by_value.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-14 shrink-0 uppercase tracking-wide text-muted-foreground">
                Values
              </span>
              {valueFilter && (
                <button
                  type="button"
                  className="text-muted-foreground underline"
                  onClick={() => setValueFilter(undefined)}
                >
                  Show all
                </button>
              )}
              {data.by_value.slice(0, 30).map((row) => (
                <button
                  key={String(row.value)}
                  type="button"
                  onClick={() => setValueFilter(String(row.value))}
                >
                  <Badge
                    variant={valueFilter === String(row.value) ? 'primary' : 'secondary'}
                    size="sm"
                    appearance="light"
                  >
                    {String(row.value)} · {row.count.toLocaleString()}
                  </Badge>
                </button>
              ))}
            </div>
          )}
          {data.by_class.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-14 shrink-0 uppercase tracking-wide text-muted-foreground">
                Class
              </span>
              {data.by_class.slice(0, 30).map((row) => (
                <Badge key={String(row.class)} variant="outline" size="sm" appearance="light">
                  {row.class ?? 'unclassed'} · {row.count.toLocaleString()}
                </Badge>
              ))}
            </div>
          )}
          {data.by_source.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-14 shrink-0 uppercase tracking-wide text-muted-foreground">
                Source
              </span>
              {data.by_source.slice(0, 30).map((row) => (
                <Badge key={String(row.source)} variant="outline" size="sm" appearance="light">
                  {SOURCE_LABEL[String(row.source)] ?? row.source ?? 'unknown'} ·{' '}
                  {row.count.toLocaleString()}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        onRowClick={openProduct}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={total === 0 && !isLoading ? emptyState : undefined}
      >
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
            <ListSearchInput
              className="w-full sm:w-72"
              value={search}
              onChange={setSearch}
              isSettling={isSearchInFlight(isSettling, isFetching, query)}
              placeholder={`Find a code or description in ${label}`}
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination sizes={[25, 50, 100]} />
          </CardFooter>
        </Card>
      </DataGrid>
    </div>
  );
}

export default SeenInProductsTab;
