'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrderStatus, useDeleteOrderStatus } from '../hooks/useOrderStatuses';
import { formatDate } from '@/lib/helpers';
import OrderStatusDeleteDialog from './order-status-delete-dialog';

interface OrderStatusDetailProps {
  orderStatusId: string;
}

export default function OrderStatusDetail({ orderStatusId }: OrderStatusDetailProps) {
  const router = useRouter();
  const { data: orderStatus, isLoading } = useOrderStatus(orderStatusId);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!orderStatus) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Delivery order status not found</p>
        <Button variant="outline" onClick={() => router.push('/order-management/order-statuses')} className="mt-4">
          Back to delivery order statuses
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
            <h2 className="text-2xl font-bold">{orderStatus.status_name}</h2>
            <Badge variant={orderStatus.is_final_status ? 'success' : 'secondary'}>
              {orderStatus.is_final_status ? 'Final Status' : 'Intermediate Status'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Status Code: {orderStatus.status_code} • Sequence: {orderStatus.sequence}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => router.push(`/order-management/order-statuses/${orderStatusId}/edit`)}>
            <Edit className="size-4" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Delivery order status information */}
      <Card>
        <CardHeader>
          <CardTitle>Delivery Order Status Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Status Code</p>
              <p className="font-medium">{orderStatus.status_code}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status Name</p>
              <p className="font-medium">{orderStatus.status_name}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Sequence</p>
              <p className="font-medium">{orderStatus.sequence}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Final Status</p>
              <p className="font-medium">
                <Badge variant={orderStatus.is_final_status ? 'success' : 'secondary'}>
                  {orderStatus.is_final_status ? 'Yes' : 'No'}
                </Badge>
              </p>
            </div>
            {orderStatus.description && (
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Description</p>
                <p className="font-medium">{orderStatus.description}</p>
              </div>
            )}
            <div>
              <p className="text-sm text-muted-foreground">Created At</p>
              <p className="font-medium">{formatDate(new Date(orderStatus.created_at))}</p>
            </div>
            {orderStatus.orders_count !== undefined && (
              <div>
                <p className="text-sm text-muted-foreground">Delivery Orders Using This Status</p>
                <p className="font-medium">{orderStatus.orders_count}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Delete Dialog */}
      {orderStatus && (
        <OrderStatusDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          orderStatus={orderStatus}
          onSuccess={() => {
            router.push('/order-management/order-statuses');
          }}
        />
      )}
    </div>
  );
}
