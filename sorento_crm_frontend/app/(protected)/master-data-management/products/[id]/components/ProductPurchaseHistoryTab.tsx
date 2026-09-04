'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef } from '@tanstack/react-table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { formatDateSafe } from '@/lib/helpers';
import { useProductPurchaseHistory } from '../../hooks/useProducts';
import { NO_CURRENCY_NOTE, formatUnitCost } from '../lib/cost';
import type { ProductPurchaseLine } from '../../services/productService';

interface ProductPurchaseHistoryTabProps {
  productId: string;
}

/**
 * Every purchase order that bought this item, newest first. The answer to "what does this
 * cost" is the top row, so the tab that proves it has to be reachable from the same page.
 */
export default function ProductPurchaseHistoryTab({
  productId,
}: ProductPurchaseHistoryTabProps) {
  const router = useRouter();
  const { data, isLoading, isError, error } = useProductPurchaseHistory(productId);

  const columns = useMemo<ColumnDef<ProductPurchaseLine>[]>(
    () => [
      {
        id: 'issue_date',
        accessorFn: (row) => row.issue_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap">{formatDateSafe(row.original.issue_date)}</span>
        ),
        size: 130,
        meta: { headerTitle: 'Date' },
      },
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="PO Number" column={column} />,
        cell: ({ row }) => <span className="font-medium">{row.original.po_number}</span>,
        size: 150,
        meta: { headerTitle: 'PO Number' },
      },
      {
        id: 'supplier_name',
        accessorFn: (row) => row.supplier_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.supplier_name ?? undefined}>
            {row.original.supplier_name ?? 'No supplier on the order'}
          </span>
        ),
        size: 220,
        meta: { headerTitle: 'Supplier' },
      },
      {
        accessorKey: 'qty_ordered',
        header: ({ column }) => <DataGridColumnHeader title="Quantity" column={column} />,
        cell: ({ row }) => (
          <span className="block text-end">{row.original.qty_ordered ?? '-'}</span>
        ),
        size: 110,
        meta: { headerTitle: 'Quantity' },
      },
      {
        accessorKey: 'qty_received',
        header: ({ column }) => <DataGridColumnHeader title="Received" column={column} />,
        cell: ({ row }) => (
          <span className="block text-end">{row.original.qty_received ?? '-'}</span>
        ),
        size: 110,
        meta: { headerTitle: 'Received' },
      },
      {
        id: 'unit_cost',
        accessorFn: (row) => row.unit_cost ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Unit Cost" column={column} />,
        cell: ({ row }) => (
          <span
            className="block text-end font-medium"
            title={
              row.original.unit_cost != null && !row.original.currency
                ? NO_CURRENCY_NOTE
                : undefined
            }
          >
            {formatUnitCost(row.original.unit_cost, row.original.currency)}
          </span>
        ),
        size: 130,
        meta: { headerTitle: 'Unit Cost' },
      },
    ],
    [],
  );

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Purchase History</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Purchase History</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="py-8 text-center text-sm text-muted-foreground">
            {error instanceof Error ? error.message : 'Failed to load purchase history.'}
          </p>
        </CardContent>
      </Card>
    );
  }

  const lines = data?.lines ?? [];

  return (
    <>
      <PanelDataGrid<ProductPurchaseLine>
        title="Purchase History"
        columns={columns}
        rows={lines}
        getRowId={(row) => row.purchase_order_id}
        listingKey="master_data.products.view::purchase-history"
        onRowClick={(row) =>
          router.push(`/procurement-management/purchase-orders/${row.purchase_order_id}`)
        }
        emptyTitle="This product has never been purchased."
        emptyBody="There is no purchase order for it, so it has no cost from history."
      />
      {/* A cap the user cannot see reads as "this is everything". */}
      {data && data.total > data.shown ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Showing the {data.shown} most recent of {data.total} purchase lines.
        </p>
      ) : null}
    </>
  );
}
