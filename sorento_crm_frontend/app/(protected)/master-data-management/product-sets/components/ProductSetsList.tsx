'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Layers, Plus, Search, Sparkles, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useDeleteProductSet, useProductSets } from '../hooks/useProductSets';
import type { ProductSet } from '../types/productSet.types';
import { ProductSetFormModal } from './ProductSetFormModal';

/** RM, or an explicit absence. A price of zero and a missing price differ. */
function priceCell(set: ProductSet) {
  const { resolved, is_overridden, computed } = set.price;
  if (resolved === null) {
    return (
      <span className="text-muted-foreground" title="No member sets the price yet">
        Not set
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5">
      <span className="tabular-nums">RM {resolved.toLocaleString('en-MY')}</span>
      {is_overridden ? (
        <Badge variant="warning" size="sm" title={`Computed: RM ${computed?.toLocaleString('en-MY')}`}>
          Override
        </Badge>
      ) : null}
    </span>
  );
}

export default function ProductSetsList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'set_code', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<ProductSet | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [debouncedSearch, sorting]);

  const { data, isLoading, isError, error, refetch, isFetching } = useProductSets({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: debouncedSearch,
  });
  const remove = useDeleteProductSet();

  const rows = useMemo<ProductSet[]>(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;
  /** No rows AND no search: the difference between "none exist" and "none match". */
  const isTrulyEmpty = !isLoading && !isError && total === 0 && debouncedSearch === '';

  const columns = useMemo<ColumnDef<ProductSet>[]>(
    () => [
      {
        accessorKey: 'set_code',
        header: ({ column }) => <DataGridColumnHeader title="Set code" column={column} />,
        cell: ({ row }) => (
          <Link
            href={`/master-data-management/product-sets/${row.original.id}`}
            className="truncate font-medium text-primary hover:underline"
            title={row.original.set_code}
          >
            {row.original.set_code}
          </Link>
        ),
        size: 200,
        meta: { headerTitle: 'Set code', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        size: 280,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'member_count',
        header: ({ column }) => <DataGridColumnHeader title="Members" column={column} />,
        cell: ({ row }) =>
          row.original.member_count === 0 ? (
            <Badge variant="secondary" size="sm">
              None yet
            </Badge>
          ) : (
            <span className="tabular-nums">{row.original.member_count}</span>
          ),
        size: 110,
        meta: { headerTitle: 'Members', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'price',
        header: ({ column }) => <DataGridColumnHeader title="Price" column={column} />,
        cell: ({ row }) => priceCell(row.original),
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Price', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'complete_sets',
        header: ({ column }) => <DataGridColumnHeader title="Complete sets" column={column} />,
        cell: ({ row }) => {
          const { complete_sets, limiting_member_code } = row.original;
          if (complete_sets === null) return <span className="text-muted-foreground">-</span>;
          // A zero is only useful with the part that caused it. "0" alone reads
          // as a bug when there is stock on the shelf.
          return complete_sets === 0 && limiting_member_code ? (
            <span className="flex items-center gap-1.5">
              <span className="tabular-nums font-medium text-destructive">0</span>
              <span className="truncate text-xs text-muted-foreground" title={`Short on ${limiting_member_code}`}>
                short on {limiting_member_code}
              </span>
            </span>
          ) : (
            <span className="tabular-nums">{complete_sets}</span>
          );
        },
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Complete sets', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              mode="icon"
              variant="ghost"
              title="Delete set"
              aria-label={`Delete ${row.original.set_code}`}
              onClick={() => setDeleting(row.original)}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ),
        size: 70,
        enableSorting: false,
        enableHiding: false,
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

  return (
    <div className="space-y-3">
      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load product sets.'}
        </div>
      ) : null}

      {isTrulyEmpty ? (
        <Card>
          <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
            <div className="rounded-full bg-muted p-3">
              <Layers className="size-6 text-muted-foreground" />
            </div>
            <p className="max-w-md text-sm text-muted-foreground">
              A set gives one code to products sold together, so a code printed on a flyer can
              be found and priced.
            </p>
            <div className="flex flex-wrap justify-center gap-2 pt-1">
              <Button onClick={() => setCreating(true)}>
                <Plus className="size-4" /> Add set
              </Button>
              <Button variant="outline" asChild>
                <Link href="/master-data-management/product-sets/proposals">
                  <Sparkles className="size-4" /> Propose from catalogue
                </Link>
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <DataGrid
          table={table}
          recordCount={total}
          isLoading={isLoading}
          listingKey="master_data.product_sets.view"
          tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
          emptyMessage="No product sets match that search."
        >
          <Card>
            <CardHeader className="block">
              <DataGridListToolbar
                table={table}
                searchSlot={
                  <div className="relative">
                    <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      placeholder="Search set code or name..."
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
                }
                exportConfig={false}
                onRefresh={() => void refetch()}
                isRefreshing={isFetching && !isLoading}
                primaryAction={
                  <div className="flex flex-wrap items-center gap-2">
                    <Button variant="outline" asChild>
                      <Link href="/master-data-management/product-sets/proposals">
                        <Sparkles className="size-4" /> Propose
                      </Link>
                    </Button>
                    <Button onClick={() => setCreating(true)}>
                      <Plus className="size-4" /> Add set
                    </Button>
                  </div>
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
      )}

      <ProductSetFormModal
        open={creating}
        onOpenChange={setCreating}
        productSet={null}
      />

      <ConfirmDeleteDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title="Delete this product set?"
        description={
          deleting
            ? `${deleting.set_code} will be removed permanently. Its ${deleting.member_count} member product${deleting.member_count === 1 ? '' : 's'} are not affected.`
            : ''
        }
        successMessage="Product set deleted"
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
      />
    </div>
  );
}
