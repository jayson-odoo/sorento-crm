'use client';

import Link from 'next/link';
import { Card, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { EventTimeline, type TimelineEvent } from '@/components/common/EventTimeline';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { OrderInquiryHeaderDetail } from '../../../_shared/types/orderInquiry.types';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm font-medium">{children}</dd>
    </div>
  );
}

function NotStated() {
  return <span className="font-normal text-muted-foreground">Not stated</span>;
}

/**
 * General tab (AC-DP-07): the SO detail's own layout - an Order card and a Customer
 * card, each at most two columns of label/value - plus a Raise history card, one entry
 * per raise (`raised`/`reconfirmed`), newest first, so who confirmed and when is never
 * lost the way the header's own `raised_at` used to be re-stamped over it.
 */
export function OrderInquiryGeneralTab({ header }: { header: OrderInquiryHeaderDetail }) {
  const events: TimelineEvent[] = (header.raise_history ?? [])
    .slice()
    .sort((a, b) => (b.at ?? '').localeCompare(a.at ?? ''))
    .map((entry, index) => ({
      id: `${entry.kind}-${entry.at ?? index}`,
      title: entry.kind === 'raised' ? 'Raised' : 'Reconfirmed',
      actor: entry.by_name ?? undefined,
      at: entry.at,
      tone: index === 0 ? 'current' : 'default',
    }));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Order</CardTitle>
          </CardHeading>
        </CardHeader>
        <section aria-label="Order" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
          <Field label="S/O no">
            {header.so_number ? (
              header.sales_order_id ? (
                <Link
                  href={`/scm/sales-orders/${header.sales_order_id}`}
                  className="text-primary hover:underline"
                >
                  {header.so_number}
                </Link>
              ) : (
                header.so_number
              )
            ) : (
              <NotStated />
            )}
          </Field>
          <Field label="SO date">
            {header.so_date ? formatDateInMalaysia(header.so_date) : <NotStated />}
          </Field>
          <Field label="Agent">{header.agent_name ?? <NotStated />}</Field>
          <Field label="Project">{header.project_title ?? <NotStated />}</Field>
          <Field label="Order type">{header.order_type ?? <NotStated />}</Field>
        </section>
      </Card>

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Customer</CardTitle>
          </CardHeading>
        </CardHeader>
        <section aria-label="Customer" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
          <Field label="Customer">{header.customer_name ?? <NotStated />}</Field>
          <Field label="Customer code">{header.customer_code ?? <NotStated />}</Field>
        </section>
      </Card>

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Raise history</CardTitle>
          </CardHeading>
        </CardHeader>
        <div className="p-4">
          <EventTimeline events={events} emptyTitle="No raise recorded yet" />
        </div>
      </Card>
    </div>
  );
}

export default OrderInquiryGeneralTab;
