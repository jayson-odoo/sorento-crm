'use client';

/**
 * The List Price cell's change-history lightbox (LIST-PRICE-CHANGE-UI,
 * documentation/plans/products/PLAN-list-price-change-ui-08nov.md).
 *
 * Owner Q3: the history is the STANDARD list view, so this is the shared `DataGrid` +
 * `DataGridTable` + `DataGridPagination` (server-side paging and sorting, the products list's
 * own wiring) inside the shared `Dialog` lightbox. Rows come from the product's audit trail
 * through `useProductPriceHistory`. Rendered once by `ProductsList`, outside the grid;
 * `product` null = closed.
 */
import { useMemo, useState } from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  PaginationState,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { useCurrencyFormat } from '@/hooks/useCurrencyFormat';
import { formatCurrency, formatDateInMalaysia } from '@/lib/helpers';
import { codeWithName } from '@/lib/product-display';
import { useProductPriceHistory } from '../hooks/useProducts';
import type { PriceChange } from '../types/product.types';

export type ListPriceHistoryProduct = {
  id: string;
  product_code: string;
  product_name?: string | null;
};

const DEFAULT_SORT: SortingState = [{ id: 'changed_at', desc: true }];

function pctLabel(row: PriceChange): string {
  if (row.kind === 'initial') return 'Initial price';
  if (row.change_pct == null) return '';
  return `${row.change_pct > 0 ? '+' : ''}${row.change_pct.toFixed(1)}%`;
}

function pctClass(row: PriceChange): string {
  if (row.kind === 'initial' || row.change_pct == null) return 'text-muted-foreground';
  if (row.change_pct < 0) return 'text-destructive';
  if (row.change_pct > 0) return 'text-success';
  return '';
}

function HistoryGrid({ productId }: { productId: string }) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [sorting, setSorting] = useState<SortingState>(DEFAULT_SORT);
  const { data, isLoading, isPlaceholderData, error, refetch } = useProductPriceHistory(productId, {
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
  });
  const currencyFormat = useCurrencyFormat();

  const columns = useMemo<ColumnDef<PriceChange>[]>(() => {
    const money = (value: number | null) => formatCurrency(value, currencyFormat, '');
    return [
      {
        id: 'changed_at',
        accessorKey: 'changed_at',
        header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap">
            {row.original.changed_at ? formatDateInMalaysia(row.original.changed_at) : ''}
          </span>
        ),
        // A full dd/mm/yyyy plus the edge padding, unclipped at 375 px too.
        size: 130,
        meta: { headerTitle: 'Date', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'old_price',
        accessorKey: 'old_price',
        header: ({ column }) => <DataGridColumnHeader title="Old price" column={column} />,
        cell: ({ row }) => <span className="whitespace-nowrap">{money(row.original.old_price)}</span>,
        size: 120,
        meta: { headerTitle: 'Old price', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'new_price',
        accessorKey: 'new_price',
        header: ({ column }) => <DataGridColumnHeader title="New price" column={column} />,
        cell: ({ row }) => <span className="whitespace-nowrap">{money(row.original.new_price)}</span>,
        size: 120,
        meta: { headerTitle: 'New price', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'change_pct',
        accessorKey: 'change_pct',
        header: ({ column }) => <DataGridColumnHeader title="% change" column={column} />,
        cell: ({ row }) => (
          <span className={`whitespace-nowrap ${pctClass(row.original)}`}>{pctLabel(row.original)}</span>
        ),
        size: 110,
        meta: { headerTitle: '% change', skeleton: <Skeleton className="h-4 w-14" /> },
      },
      {
        id: 'changed_by',
        accessorKey: 'changed_by',
        header: ({ column }) => <DataGridColumnHeader title="By" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.changed_by ?? undefined}>
            {row.original.changed_by ?? ''}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'By', skeleton: <Skeleton className="h-4 w-24" /> },
      },
    ];
  }, [currencyFormat]);

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil((data?.pagination.total ?? 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    columnResizeMode: 'onChange',
    onPaginationChange: setPagination,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((prev) => ({ ...prev, pageIndex: 0 }));
    },
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total ?? 0}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      listingKey={null}
      error={error}
      onRetry={() => void refetch()}
      emptyMessage={
        <span className="flex flex-col items-center gap-1">
          <span className="font-medium">No list price changes recorded</span>
          <span className="text-muted-foreground">Price edits and AutoCount syncs appear here.</span>
        </span>
      }
      tableLayout={{ width: 'fixed', columnsResizable: true, scrollerMaxHeight: false }}
      tableClassNames={{ edgeCell: 'px-4' }}
    >
      <Card>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}

export default function ListPriceHistoryDialog({
  product,
  onOpenChange,
}: {
  product: ListPriceHistoryProduct | null;
  onOpenChange: (open: boolean) => void;
}) {
  const title = `List price history${
    product ? `: ${codeWithName(product.product_code, product.product_name ?? '')}` : ''
  }`;
  return (
    <Dialog open={!!product} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle className="truncate" title={title}>
            {title}
          </DialogTitle>
        </DialogHeader>
        <DialogBody>{product && <HistoryGrid key={product.id} productId={product.id} />}</DialogBody>
      </DialogContent>
    </Dialog>
  );
}
