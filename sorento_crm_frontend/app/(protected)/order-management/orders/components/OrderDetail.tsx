'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useOrder, useUpdateOrder } from '../hooks/useOrders';
import { useOrderStatusSelectQuery } from '../../shared/hooks/use-order-status-select-query';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import OrderDeleteDialog from './order-delete-dialog';
import OrderLinesCard from './OrderLinesCard';
import OrderFulfilledComplaintsCard from './OrderFulfilledComplaintsCard';
import OrderNavigation from './OrderNavigation';

interface OrderDetailProps {
  orderId: string;
  /** Raw list query string (search/sort/filters) carried from the list page, so
   *  Back/Edit links preserve it. The prev/next pager reads it from the URL. */
  listSearch: string;
}

export default function OrderDetail({ orderId, listSearch }: OrderDetailProps) {
  const router = useRouter();
  const { data: order, isLoading } = useOrder(orderId);
  const listQs = listSearch ? `?${listSearch}` : '';
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const updateMutation = useUpdateOrder();
  const { data: orderStatuses = [] } = useOrderStatusSelectQuery();
  const statusList = orderStatuses ?? [];
  const newOrDeliveredStatuses = statusList.filter((s) => {
    const code = (s.status_code ?? '').toString().trim().toLowerCase();
    return code === 'new' || code === 'delivered';
  });
  const gearStatuses = newOrDeliveredStatuses.length > 0 ? newOrDeliveredStatuses : statusList;

  const handleStatusChange = async (statusId: string) => {
    try {
      await updateMutation.mutateAsync({ id: orderId, data: { order_status_id: statusId } });
    } catch {
      // Error toast is handled by the mutation
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Delivery order not found</p>
        <Button
          variant="outline"
          onClick={() => router.push(`/order-management/orders${listQs}`)}
          className="mt-4"
        >
          Back to delivery orders
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{order.order_number}</h1>
            {order.order_status && (
              <Badge variant={getStatusBadgeVariant(order.order_status.status_name)}>
                {order.order_status.status_name}
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {order.debtor_name || order.debtor_code || '-'} • Delivery order date: {order.order_date ? formatDate(new Date(order.order_date)) : '-'}
          </p>
        </div>
        <div className="flex gap-2">
          <OrderNavigation orderId={orderId} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="outline" size="icon" aria-label="Change delivery order status">
                <Settings className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {gearStatuses.map((status) => (
                <DropdownMenuItem
                  key={status.id}
                  onClick={() => handleStatusChange(status.id)}
                  disabled={updateMutation.isPending}
                >
                  {status.status_name}
                </DropdownMenuItem>
              ))}
              {gearStatuses.length === 0 && (
                <DropdownMenuItem disabled>No statuses available</DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            onClick={() =>
              router.push(`/order-management/orders/${orderId}/edit${listQs}`)
            }
          >
            <Edit className="size-4" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      {order && (
        <OrderDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          order={order}
          onSuccess={() => {
            router.push(`/order-management/orders${listQs}`);
          }}
        />
      )}

      <Tabs defaultValue="information" className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start overflow-x-auto">
          <TabsTrigger value="information">Delivery order information</TabsTrigger>
          <TabsTrigger value="financial">Financial summary</TabsTrigger>
          <TabsTrigger value="delivery">Delivery &amp; tracking</TabsTrigger>
        </TabsList>

        <TabsContent value="information" className="mt-0 space-y-6 focus-visible:outline-none">
          <Card>
            <CardHeader>
              <CardTitle>Delivery order information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Delivery Order Number</p>
                  <p className="font-medium">{order.order_number}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Delivery Order Date</p>
                  <p className="font-medium">{order.order_date ? formatDate(new Date(order.order_date)) : '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Debtor Code</p>
                  <p className="font-medium">{order.debtor_code || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Debtor Name</p>
                  <p className="font-medium">{order.debtor_name || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Agent</p>
                  <p className="font-medium">{order.agent || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Delivery Order Type</p>
                  <p className="font-medium">{order.order_type || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Cancelled</p>
                  <p className="font-medium">{order.is_cancelled ? 'Yes' : 'No'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Remarks CS</p>
                  <p className="font-medium">{order.remarks_cs || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Delivery Order Status</p>
                  <p className="font-medium">
                    {order.order_status ? (
                      <Badge variant={getStatusBadgeVariant(order.order_status.status_name)}>{order.order_status.status_name}</Badge>
                    ) : (
                      '-'
                    )}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Estimated Delivery Date</p>
                  <p className="font-medium">{order.estimated_delivery_date ? formatDate(new Date(order.estimated_delivery_date)) : '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Actual Delivery Date</p>
                  <p className="font-medium">{order.actual_delivery_date ? formatDate(new Date(order.actual_delivery_date)) : '-'}</p>
                </div>
              </div>
              {order.remarks && (
                <div>
                  <p className="text-sm text-muted-foreground">Remarks</p>
                  <p className="font-medium whitespace-pre-wrap">{order.remarks}</p>
                </div>
              )}
            </CardContent>
          </Card>
          <OrderLinesCard orderId={orderId} lines={order.lines ?? []} />
        </TabsContent>

        <TabsContent value="financial" className="mt-0 focus-visible:outline-none">
          <Card>
            <CardHeader>
              <CardTitle>Financial summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-muted-foreground">Subtotal Amount</p>
                  <p className="font-medium text-lg">
                    {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(order.subtotal_amount)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Discount Amount</p>
                  <p className="font-medium text-lg text-destructive">
                    -{new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(order.discount_amount)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Tax Amount</p>
                  <p className="font-medium text-lg">
                    {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(order.tax_amount)}
                  </p>
                </div>
              </div>
              <div className="pt-4 border-t">
                <p className="text-sm text-muted-foreground">Total Amount</p>
                <p className="font-bold text-xl">
                  {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(order.total_amount)}
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4">
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium text-sm">
                    {formatDate(new Date(order.created_at))}
                  </p>
                </div>
                {order.updated_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Last Updated</p>
                    <p className="font-medium text-sm">
                      {formatDate(new Date(order.updated_at))}
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="delivery" className="mt-0 focus-visible:outline-none">
          <Card>
            <CardHeader>
              <CardTitle>Delivery &amp; tracking</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Debtor Code</p>
                  <p className="font-medium">{order.debtor_code || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Debtor Name</p>
                  <p className="font-medium">{order.debtor_name || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Agent</p>
                  <p className="font-medium">{order.agent || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Delivery Order Type</p>
                  <p className="font-medium">{order.order_type || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Remarks CS</p>
                  <p className="font-medium">{order.remarks_cs || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Customer (Ref)</p>
                  <p className="font-medium">{order.customer_ref || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Cancelled</p>
                  <p className="font-medium">{order.is_cancelled ? 'Yes' : 'No'}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Delivery Time</p>
                  <p className="font-medium">{order.pickup_time || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Checker</p>
                  <p className="font-medium">{order.checker || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Transporter</p>
                  <p className="font-medium">{order.transporter || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Driver Name</p>
                  <p className="font-medium">{order.driver_name || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Lorry Plate</p>
                  <p className="font-medium">{order.lorry_plate || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Warehouse</p>
                  <p className="font-medium">{order.warehouse || '-'}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Salesman</p>
                  <p className="font-medium">{order.salesman || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Trips</p>
                  <p className="font-medium">{order.trips ?? '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Delivery Days (2)</p>
                  <p className={`font-medium ${order.kpi_warning ? 'text-amber-600' : ''}`}>
                    {order.delivery_days ?? '-'} day(s)
                  </p>
                </div>
              </div>

              {(order.delivery_remarks || order.delivery_remarks_cs) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {order.delivery_remarks_cs && (
                    <div>
                      <p className="text-sm text-muted-foreground">Remarks CS</p>
                      <p className="font-medium whitespace-pre-wrap">{order.delivery_remarks_cs}</p>
                    </div>
                  )}
                  {order.delivery_remarks && (
                    <div>
                      <p className="text-sm text-muted-foreground">Remarks</p>
                      <p className="font-medium whitespace-pre-wrap">{order.delivery_remarks}</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Reverse of the complaint "Fulfilment Delivery Orders" section: the
          complaint(s) this DO fulfils (auto-linked from Remarks CS). Always
          rendered with its own empty state. */}
      <OrderFulfilledComplaintsCard orderId={orderId} />
    </div>
  );
}
