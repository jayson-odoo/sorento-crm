'use client';

import { Badge } from '@/components/ui/badge';
import { formatDate } from '@/lib/helpers';
import { useComplaintFulfilmentOrders } from '../hooks/useComplaintFulfilmentOrders';

/**
 * A salesperson's own complaint: its fulfilment Delivery Orders as plain read-only text. No grid, no
 * link to a DO page they cannot open, no action.
 */
export default function ComplaintFulfilmentOrdersReadOnly({ complaintId }: { complaintId: string }) {
  const { data, isLoading, error } = useComplaintFulfilmentOrders(complaintId);
  const orders = Array.isArray(data) ? data : [];

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">Fulfilment Delivery Orders</h3>
      {isLoading ? null : error ? (
        <p className="text-sm text-muted-foreground">Could not load the delivery orders.</p>
      ) : orders.length === 0 ? (
        <p className="text-sm text-muted-foreground">No replacement delivery order linked yet.</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {orders.map((order) => (
            <li key={order.order_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-sm">
              <span className="font-medium">{order.order_number}</span>
              <Badge status={order.status}>{order.status_label}</Badge>
              <span className="text-muted-foreground">
                {order.actual_delivery_date ? formatDate(new Date(order.actual_delivery_date)) : '-'}
              </span>
              {order.items.length > 0 ? (
                <span className="text-muted-foreground">
                  {order.items.map((item) => `${item.product_code} x ${item.qty ?? '-'}`).join(', ')}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
