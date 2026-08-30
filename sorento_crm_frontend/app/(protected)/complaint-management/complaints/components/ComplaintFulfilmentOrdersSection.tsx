'use client';

import Link from 'next/link';
import { PackageOpen } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { formatDate } from '@/lib/helpers';
import { useComplaintFulfilmentOrders } from '../hooks/useComplaintFulfilmentOrders';
import type { FulfilmentOrder } from '../services/complaintFulfilmentService';

interface ComplaintFulfilmentOrdersSectionProps {
  complaintId: string;
}

function FulfilmentItemsPopover({ order }: { order: FulfilmentOrder }) {
  const itemCount = order.items.length;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`View items for delivery order ${order.order_number}`}
          title="View delivery order items"
        >
          <PackageOpen className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-0">
        <div className="border-b px-3 py-2">
          <p className="text-sm font-semibold truncate" title={order.order_number}>
            {order.order_number}
          </p>
          <p className="text-xs text-muted-foreground">
            {itemCount} item{itemCount === 1 ? '' : 's'}
          </p>
        </div>
        <div className="max-h-64 overflow-y-auto">
          {itemCount === 0 ? (
            <p className="px-3 py-3 text-sm text-muted-foreground">
              No line items recorded.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-left">Product code</TableHead>
                  <TableHead className="w-16 text-right">Qty</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {order.items.map((item, i) => (
                  <TableRow key={`${item.product_code}-${i}`}>
                    <TableCell className="text-left font-medium">
                      <span className="block truncate" title={item.product_code}>
                        {item.product_code}
                      </span>
                      {item.product_type && (
                        <span
                          className="block truncate text-xs text-muted-foreground"
                          title={item.product_type}
                        >
                          {item.product_type}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">{item.qty ?? '-'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default function ComplaintFulfilmentOrdersSection({
  complaintId,
}: ComplaintFulfilmentOrdersSectionProps) {
  const { data: orders, isLoading } = useComplaintFulfilmentOrders(complaintId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Fulfilment Delivery Orders</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : !orders || orders.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            No replacement delivery order linked yet.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>DO Number</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Delivery Date</TableHead>
                  <TableHead className="w-12 text-right">Items</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.order_id}>
                    <TableCell>
                      <Link
                        href={`/order-management/orders/${order.order_id}`}
                        className="block max-w-[14rem] truncate font-medium text-primary hover:underline underline-offset-2"
                        title={order.order_number}
                      >
                        {order.order_number}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge status={order.status}>
                        {order.status_label}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {order.actual_delivery_date
                        ? formatDate(new Date(order.actual_delivery_date))
                        : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      <FulfilmentItemsPopover order={order} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
