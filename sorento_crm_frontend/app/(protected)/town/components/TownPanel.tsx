'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { isPending, type TownPayload, type TownSnapshot } from '@/types/town.types';
import { boughtToday, count, rm, shopLabel, shopToday } from '../lib/townFormat';

export type TownTarget =
  | { kind: 'sales' }
  | { kind: 'bought' }
  | { kind: 'shop'; key: string }
  | { kind: 'low' }
  | { kind: 'deliver' }
  | { kind: 'approve' };

/** The existing screens a panel opens (each is permission-checked by its own page). */
const ROUTES = {
  sales: '/sales/sales-and-outstanding',
  invoices: '/finance/billing-documents',
  reorder: '/scm/reorder',
  deliveries: '/scm/sales-orders',
  approvals: '/procurement-management/purchase-requests',
} as const;

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <table className="mt-2 w-full text-sm">
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label} className="border-b border-border last:border-0">
            <td className="py-1.5 pe-2">{label}</td>
            <td className="py-1.5 text-end tabular-nums">{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function body(snapshot: TownSnapshot, target: TownTarget): { title: string; meta: string; content: ReactNode } {
  const { today, compare, reorder, deliveries, approvals } = snapshot;
  const link = (href: string, label: string) => (
    <Button asChild variant="outline" size="sm" className="mt-3">
      <Link href={href}>{label}</Link>
    </Button>
  );
  const full = today.amount != null;
  switch (target.kind) {
    case 'sales':
      return {
        title: "Today's sales",
        meta: 'Same figure as the sales report',
        content: (
          <>
            <Rows
              rows={[
                ...(full ? ([['Invoiced today', rm(today.amount as string)]] as [string, ReactNode][]) : []),
                ['Invoices', count(today.invoice_count)],
                ['Credit notes', count(today.credit_note_count)],
                ['Customers', count(today.customer_count)],
                ...(full && compare?.last_week_amount
                  ? ([[compare.label, rm(compare.last_week_amount)]] as [string, ReactNode][])
                  : []),
              ]}
            />
            {full ? link(ROUTES.sales, 'Open sales report') : null}
          </>
        ),
      };
    case 'bought': {
      const { bought, others } = boughtToday(snapshot);
      return {
        title: 'Bought today',
        meta: `${count(today.dealer_customer_count || bought.length)} dealers invoiced today`,
        content: (
          <Rows
            rows={[
              ...bought.map((shop): [string, ReactNode] => [shopLabel(shop), shopToday(shop)]),
              ...(others ? ([[`+ ${others} more dealers`, '']] as [string, ReactNode][]) : []),
            ]}
          />
        ),
      };
    }
    case 'shop': {
      const shop = snapshot.shops.find((s) => s.key === target.key);
      if (!shop) return { title: 'Dealer', meta: '', content: null };
      return {
        title: shopLabel(shop),
        meta: `${shop.today_docs ? 'Bought today' : 'No invoice today'}${
          shop.rank && shop.name ? ` · rank ${shop.rank} of 30 (90 days)` : ''
        }`,
        content: (
          <>
            <Rows
              rows={[
                ['Invoices today', shop.today_docs],
                ...(shop.today_amount ? ([['Invoiced today', rm(shop.today_amount)]] as [string, ReactNode][]) : []),
                ...(shop.ninety_day_amount
                  ? ([['Last 90 days', rm(shop.ninety_day_amount)]] as [string, ReactNode][])
                  : []),
              ]}
            />
            {full ? link(ROUTES.invoices, 'Open invoices') : null}
          </>
        ),
      };
    }
    case 'low':
      return {
        title: `${count(reorder.below_count)} products low`,
        meta: `below their reorder level, of ${count(reorder.set_count)} with a level`,
        content: link(ROUTES.reorder, 'Open reorder list'),
      };
    case 'deliver':
      return {
        title: `${deliveries ? count(deliveries.to_deliver) : '-'} to deliver`,
        meta: 'Sales orders due today or overdue',
        content: link(ROUTES.deliveries, 'Open sales orders'),
      };
    case 'approve':
      return {
        title: 'Approvals',
        meta: approvals.total ? `${approvals.total} waiting for a decision` : 'All clear',
        content: (
          <>
            <Rows
              rows={[
                ['Purchase requests', approvals.purchase_requests],
                ['Quotation documents', approvals.quotation_documents],
              ]}
            />
            {link(ROUTES.approvals, 'Open purchase requests')}
          </>
        ),
      };
  }
}

/** What a tap on a building or a card opens, beside both views. */
export function TownPanel({
  snapshot,
  target,
  onClose,
}: {
  snapshot: TownPayload;
  target: TownTarget | null;
  onClose: () => void;
}) {
  if (!target || isPending(snapshot)) return null;
  const { title, meta, content } = body(snapshot, target);
  return (
    <aside className="fixed inset-x-3 bottom-3 z-50 max-h-[55vh] overflow-auto rounded-lg border border-border bg-background p-4 shadow-lg sm:inset-x-auto sm:end-4 sm:top-24 sm:bottom-auto sm:w-80">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="absolute end-2 top-2"
        aria-label="Close panel"
        onClick={onClose}
      >
        <X className="size-4" />
      </Button>
      <h2 className="pe-8 text-base font-semibold">{title}</h2>
      {meta ? <p className="text-xs text-muted-foreground">{meta}</p> : null}
      {content}
    </aside>
  );
}
