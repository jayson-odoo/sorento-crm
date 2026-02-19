'use client';

import { useRouter } from 'next/navigation';
import { ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useStockBalance } from '@/app/(protected)/inventory-management/stock/hooks/useStock';
import type { Stock } from '@/app/(protected)/inventory-management/stock/types/stock.types';

interface ProductStockTabProps {
  productId: string;
}

export default function ProductStockTab({ productId }: ProductStockTabProps) {
  const router = useRouter();
  const { data, isLoading } = useStockBalance({
    pageIndex: 0,
    pageSize: 100,
    product_id: productId,
    sorting: [],
  });

  const stockItems = (data?.data || []) as Stock[];

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Stock Information</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (stockItems.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Stock Information</CardTitle>
          <p className="text-sm text-muted-foreground">
            Stock levels across warehouses. Ledger entries available from stock detail.
          </p>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            <p>No stock information available for this product.</p>
            <p className="text-sm mt-2">Stock records will appear here once inventory is added.</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const statusVariants: Record<string, 'destructive' | 'warning' | 'success' | 'secondary'> = {
    low: 'warning',
    critical: 'destructive',
    normal: 'success',
    overstock: 'secondary',
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stock Information</CardTitle>
        <p className="text-sm text-muted-foreground">
          Warehouse quantities and ledger. Click a row to view ledger entries.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Warehouse</TableHead>
              <TableHead>Available</TableHead>
              <TableHead>Reserved</TableHead>
              <TableHead>Total</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {stockItems.map((stock) => {
              const available = stock.quantity_available ?? stock.available ?? 0;
              const reserved = stock.quantity_reserved ?? stock.reserved_quantity ?? 0;
              const total = stock.quantity_on_hand ?? stock.quantity ?? 0;
              const reorderLevel = stock.product?.reorder_level ?? 0;
              let status: 'low' | 'critical' | 'normal' | 'overstock' = 'normal';
              if (available <= 0) status = 'critical';
              else if (available <= reorderLevel * 0.5) status = 'critical';
              else if (available <= reorderLevel) status = 'low';
              else if (available > reorderLevel * 2) status = 'overstock';

              return (
                <TableRow
                  key={stock.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() =>
                    stock.product_id &&
                    stock.warehouse_id &&
                    router.push(`/inventory-management/stock/${stock.product_id}/${stock.warehouse_id}`)
                  }
                >
                  <TableCell className="font-medium">
                    {stock.warehouse?.warehouse_name || 'Unknown Warehouse'}
                  </TableCell>
                  <TableCell>{available}</TableCell>
                  <TableCell>{reserved}</TableCell>
                  <TableCell>{total}</TableCell>
                  <TableCell>
                    <Badge
                      variant={statusVariants[status] || 'secondary'}
                      appearance="ghost"
                    >
                      {status.charAt(0).toUpperCase() + status.slice(1)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
      {data?.pagination && data.pagination.total > 100 && (
        <div className="p-4 text-sm text-muted-foreground text-center border-t">
          Showing 100 of {data.pagination.total} warehouses
        </div>
      )}
    </Card>
  );
}
