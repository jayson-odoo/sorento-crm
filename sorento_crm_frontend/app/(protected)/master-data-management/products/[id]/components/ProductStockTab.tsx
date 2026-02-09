'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { useStockBalance } from '@/app/(protected)/inventory-management/stock/hooks/useStock';
import { formatDate } from '@/lib/helpers';
import type { Stock } from '@/app/(protected)/inventory-management/stock/types/stock.types';

interface ProductStockTabProps {
  productId: string;
}

export default function ProductStockTab({ productId }: ProductStockTabProps) {
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize] = useState(50);

  const { data, isLoading } = useStockBalance({
    pageIndex,
    pageSize,
    product_id: productId,
    sorting: [],
  });

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

  const stockItems = data?.data || [];

  if (stockItems.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Stock Information</CardTitle>
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stock Information</CardTitle>
        <p className="text-sm text-muted-foreground">
          Stock levels across different warehouses
        </p>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {stockItems.map((stock: Stock) => {
            const available = stock.quantity_available ?? stock.available ?? 0;
            const reserved = stock.quantity_reserved ?? stock.reserved_quantity ?? 0;
            const total = stock.quantity_on_hand ?? stock.quantity ?? 0;
            
            // Determine status
            const reorderLevel = stock.product?.reorder_level ?? 0;
            let status: 'low' | 'critical' | 'normal' | 'overstock' = 'normal';
            if (available <= 0) {
              status = 'critical';
            } else if (available <= reorderLevel * 0.5) {
              status = 'critical';
            } else if (available <= reorderLevel) {
              status = 'low';
            } else if (available > reorderLevel * 2) {
              status = 'overstock';
            }

            const statusVariants: Record<string, 'destructive' | 'warning' | 'success' | 'secondary'> = {
              low: 'warning',
              critical: 'destructive',
              normal: 'success',
              overstock: 'secondary',
            };

            return (
              <div
                key={stock.id}
                className="border rounded-lg p-4 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-semibold">
                      {stock.warehouse?.warehouse_name || 'Unknown Warehouse'}
                    </h4>
                    {stock.zone_id && (
                      <p className="text-sm text-muted-foreground">
                        Zone: {stock.zone_id}
                      </p>
                    )}
                  </div>
                  <Badge
                    variant={statusVariants[status] || 'secondary'}
                    appearance="ghost"
                  >
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </Badge>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Available</p>
                    <p className="text-lg font-semibold">{available}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Reserved</p>
                    <p className="text-lg font-semibold">{reserved}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Total</p>
                    <p className="text-lg font-semibold">{total}</p>
                  </div>
                </div>

                {stock.quantity_damaged && stock.quantity_damaged > 0 && (
                  <div>
                    <p className="text-sm text-muted-foreground">Damaged</p>
                    <p className="text-sm font-medium text-destructive">
                      {stock.quantity_damaged}
                    </p>
                  </div>
                )}

                {stock.reorder_point !== null && stock.reorder_point !== undefined && (
                  <div>
                    <p className="text-sm text-muted-foreground">Reorder Point</p>
                    <p className="text-sm font-medium">{stock.reorder_point}</p>
                  </div>
                )}

                <div className="pt-2 border-t text-xs text-muted-foreground">
                  Last updated: {stock.updated_at ? formatDate(new Date(stock.updated_at)) : formatDate(new Date(stock.created_at))}
                </div>
              </div>
            );
          })}
        </div>

        {data?.pagination && data.pagination.total > pageSize && (
          <div className="mt-4 text-sm text-muted-foreground text-center">
            Showing {stockItems.length} of {data.pagination.total} warehouses
          </div>
        )}
      </CardContent>
    </Card>
  );
}
