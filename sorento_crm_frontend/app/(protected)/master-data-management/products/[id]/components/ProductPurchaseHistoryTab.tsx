'use client';

import { useRouter } from 'next/navigation';
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
import { formatDateSafe } from '@/lib/helpers';
import { useProductPurchaseHistory } from '../../hooks/useProducts';
import { NO_CURRENCY_NOTE, formatUnitCost } from '../lib/cost';

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
    <Card>
      <CardHeader>
        <CardTitle>Purchase History</CardTitle>
      </CardHeader>
      <CardContent>
        {lines.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            <p>This product has never been purchased.</p>
            <p className="mt-2 text-sm">
              There is no purchase order for it, so it has no cost from history.
            </p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>PO Number</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead className="text-end">Quantity</TableHead>
                  <TableHead className="text-end">Received</TableHead>
                  <TableHead className="text-end">Unit Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lines.map((line, i) => (
                  <TableRow
                    key={`${line.purchase_order_id}-${i}`}
                    className="cursor-pointer"
                    onClick={() =>
                      router.push(
                        `/procurement-management/purchase-orders/${line.purchase_order_id}`,
                      )
                    }
                  >
                    <TableCell className="whitespace-nowrap">
                      {formatDateSafe(line.issue_date)}
                    </TableCell>
                    <TableCell className="font-medium">{line.po_number}</TableCell>
                    <TableCell
                      className="max-w-[220px] truncate"
                      title={line.supplier_name ?? undefined}
                    >
                      {line.supplier_name ?? 'No supplier on the order'}
                    </TableCell>
                    <TableCell className="text-end">{line.qty_ordered ?? '-'}</TableCell>
                    <TableCell className="text-end">{line.qty_received ?? '-'}</TableCell>
                    <TableCell
                      className="text-end font-medium"
                      title={
                        line.unit_cost != null && !line.currency
                          ? NO_CURRENCY_NOTE
                          : undefined
                      }
                    >
                      {formatUnitCost(line.unit_cost, line.currency)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {/* A cap the user cannot see reads as "this is everything". */}
            {data && data.total > data.shown ? (
              <p className="mt-3 text-xs text-muted-foreground">
                Showing the {data.shown} most recent of {data.total} purchase lines.
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
