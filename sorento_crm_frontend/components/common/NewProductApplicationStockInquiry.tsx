'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { STOCK_INQUIRY_STATUS_LABELS } from '@/app/(protected)/procurement-management/stock-inquiries/types/stockInquiry.types';
import type { NewProductApplicationStockInquiry as StockInquiry } from '@/types/newProductApplication';

const dash = (v: string | number | null | undefined) =>
  v === null || v === undefined || String(v).trim() === '' ? '-' : String(v);

/**
 * The "Stock inquiry" tab of a new product application: the inquiry it was raised from, read-only.
 * `href` is the staff link to the inquiry; the portal passes none and shows the number as text.
 */
export function NewProductApplicationStockInquiry({
  inquiry,
  href,
}: {
  inquiry: StockInquiry | null | undefined;
  href?: (id: string) => string;
}) {
  if (!inquiry) {
    return (
      <div className="rounded-lg border border-dashed px-6 py-10 text-center">
        <h3 className="text-base font-semibold">No stock inquiry</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Applications raised from a stock inquiry show it here.
        </p>
      </div>
    );
  }
  const label = inquiry.status
    ? (STOCK_INQUIRY_STATUS_LABELS[inquiry.status] ?? inquiry.status)
    : null;
  const rows: [string, React.ReactNode][] = [
    [
      'Inquiry',
      href && inquiry.inquiry_number ? (
        <Link href={href(inquiry.id)} className="text-primary hover:underline">
          {inquiry.inquiry_number}
        </Link>
      ) : (
        dash(inquiry.inquiry_number)
      ),
    ],
    [
      'Status',
      inquiry.status ? <Badge status={inquiry.status}>{label}</Badge> : '-',
    ],
    ['Product code', dash(inquiry.product_code)],
    ['Item description', dash(inquiry.item_description)],
    ['Purchasing response', dash(inquiry.purchasing_response)],
    ['Qty', dash(inquiry.quantity)],
  ];
  return (
    <dl className="divide-y rounded-md border text-sm">
      {rows.map(([name, value]) => (
        <div
          key={name}
          className="grid grid-cols-1 gap-1 px-3 py-2 sm:grid-cols-[11rem_1fr]"
        >
          <dt className="text-muted-foreground">{name}</dt>
          <dd className="min-w-0 whitespace-pre-wrap break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
