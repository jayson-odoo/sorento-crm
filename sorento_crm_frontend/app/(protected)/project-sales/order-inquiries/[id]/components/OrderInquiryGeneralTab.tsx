'use client';

import Link from 'next/link';
import { Card, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { EventTimeline, type TimelineEvent } from '@/components/common/EventTimeline';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { formatMoneyExact } from '../../../_shared/lib/money';
import { isSparePartInquiry, sparePartStateLabel } from '../../../_shared/lib/sparePartRequest';
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

/** What the Request and Approval cards read: the OI header on the OI page, the request's own
 *  detail on its record page (`SparePartRequestRecord`). */
export type SparePartGeneralFields = Pick<
  OrderInquiryHeaderDetail,
  | 'state'
  | 'currency'
  | 'needed_by'
  | 'default_location'
  | 'reason'
  | 'requested_by_name'
  | 'submitted_at'
  | 'approved_at'
  | 'approved_by_name'
  | 'reject_reason'
  | 'total'
>;

/** A spare part request's Request and Approval cards (UAC P4, G3). */
export function SparePartRequestGeneralCards({ header }: { header: SparePartGeneralFields }) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Request</CardTitle>
          </CardHeading>
        </CardHeader>
        <section aria-label="Request" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
          <Field label="Requested by">{header.requested_by_name ?? <NotStated />}</Field>
          <Field label="Needed by">
            {header.needed_by ? formatDateInMalaysia(header.needed_by) : <NotStated />}
          </Field>
          <Field label="Currency">{header.currency ?? <NotStated />}</Field>
          <Field label="Default location">{header.default_location ?? <NotStated />}</Field>
          <Field label="Total">
            {header.total != null ? formatMoneyExact(header.total, header.currency) : <NotStated />}
          </Field>
          <div className="min-w-0 sm:col-span-2">
            <dt className="text-xs text-muted-foreground">Reason</dt>
            <dd className="whitespace-pre-line break-words text-sm font-medium">
              {header.reason ?? <NotStated />}
            </dd>
          </div>
        </section>
      </Card>

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Approval</CardTitle>
          </CardHeading>
        </CardHeader>
        <section aria-label="Approval" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
          <Field label="Status">{sparePartStateLabel(header.state)}</Field>
          <Field label="Submitted at">
            {header.submitted_at ? formatDateTimeInMalaysia(header.submitted_at) : <NotStated />}
          </Field>
          <Field label="Approved by">{header.approved_by_name ?? <NotStated />}</Field>
          <Field label="Approved at">
            {header.approved_at ? formatDateTimeInMalaysia(header.approved_at) : <NotStated />}
          </Field>
          {header.reject_reason ? (
            <div className="min-w-0 sm:col-span-2">
              <dt className="text-xs text-muted-foreground">Reject reason</dt>
              <dd className="whitespace-pre-line break-words text-sm font-medium">
                {header.reject_reason}
              </dd>
            </div>
          ) : null}
        </section>
      </Card>
    </>
  );
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

  const raiseHistory = (
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
  );

  // SPARE-PART-ORDER-REQUEST (UAC P4): a spare part request has no sales order or
  // customer; its General tab reads the request and its approval in the same card layout.
  if (isSparePartInquiry(header)) {
    return (
      <div className="space-y-4">
        <SparePartRequestGeneralCards header={header} />
        {raiseHistory}
      </div>
    );
  }

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

      {raiseHistory}
    </div>
  );
}

export default OrderInquiryGeneralTab;
