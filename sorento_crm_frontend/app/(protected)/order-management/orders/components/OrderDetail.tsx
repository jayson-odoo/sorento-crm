'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrder, useDeleteOrder, useOrders } from '../hooks/useOrders';
import { formatDate } from '@/lib/helpers';
import OrderDeleteDialog from './order-delete-dialog';
import RecordNavigation from '@/components/common/RecordNavigation';

interface OrderDetailProps {
  orderId: string;
}

export default function OrderDetail({ orderId }: OrderDetailProps) {
  const router = useRouter();
  const { data: order, isLoading } = useOrder(orderId);
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = useOrders(navigationParams);
  const navigationItems = navigationData?.data ?? [];
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

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
        <p className="text-muted-foreground">Order not found</p>
        <Button variant="outline" onClick={() => router.push('/order-management/orders')} className="mt-4">
          Back to Orders
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
              <Badge variant="secondary">
                {order.order_status.status_name}
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {order.debtor_name || order.debtor_code || '—'} • Order Date: {order.order_date ? formatDate(new Date(order.order_date)) : '-'}
          </p>
        </div>
        <div className="flex gap-2">
          <RecordNavigation
            currentId={orderId}
            items={navigationItems}
            basePath="/order-management/orders"
          />
          <Button variant="outline" onClick={() => router.push(`/order-management/orders/${orderId}/edit`)}>
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
            router.push('/order-management/orders');
          }}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Order Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Order Number</p>
                <p className="font-medium">{order.order_number}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Order Date</p>
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
                <p className="text-sm text-muted-foreground">Order Type</p>
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
                <p className="text-sm text-muted-foreground">Order Status</p>
                <p className="font-medium">
                  {order.order_status ? (
                    <Badge variant="secondary">{order.order_status.status_name}</Badge>
                  ) : (
                    '-'
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Promised Delivery Date</p>
                <p className="font-medium">{order.promised_delivery_date ? formatDate(new Date(order.promised_delivery_date)) : '-'}</p>
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

        <Card>
          <CardHeader>
            <CardTitle>Financial Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <div className="pt-4 border-t">
              <p className="text-sm text-muted-foreground">Total Amount</p>
              <p className="font-bold text-xl">
                {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(order.total_amount)}
              </p>
            </div>
            <div className="pt-4">
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
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Delivery & Tracking</CardTitle>
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
              <p className="text-sm text-muted-foreground">Order Type</p>
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
              <p className="font-medium">{order.delivery_time || '-'}</p>
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
    </div>
  );
}
