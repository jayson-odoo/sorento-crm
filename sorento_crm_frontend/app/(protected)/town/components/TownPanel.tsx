'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { isPending, type TownPayload, type TownSnapshot } from '@/types/town.types';
import { boughtToday, count, rm, shopLabel, shopToday } from '../lib/townFormat';

/** The sheet's close button is 16px; on a touch screen its hit area grows to 44px (as COARSE_HIT_TARGET_CLASS does). */
const CLOSE_HIT_AREA =
  "[&_[data-slot=sheet-close]]:pointer-coarse:after:absolute [&_[data-slot=sheet-close]]:pointer-coarse:after:left-1/2 [&_[data-slot=sheet-close]]:pointer-coarse:after:top-1/2 [&_[data-slot=sheet-close]]:pointer-coarse:after:min-h-11 [&_[data-slot=sheet-close]]:pointer-coarse:after:min-w-11 [&_[data-slot=sheet-close]]:pointer-coarse:after:-translate-x-1/2 [&_[data-slot=sheet-close]]:pointer-coarse:after:-translate-y-1/2 [&_[data-slot=sheet-close]]:pointer-coarse:after:content-['']";

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
    <div className="mt-2 overflow-x-auto">
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-b border-border last:border-0">
              <td className="py-1.5 pe-2">{label}</td>
              <td className="py-1.5 text-end tabular-nums">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
        meta: '',
        content: (
          <>
            <Rows
              rows={[
                ...(full ? ([['Invoiced today', rm(today.amount as string)]] as [string, ReactNode][]) : []),
                ['Invoices', count(today.invoice_count)],
                ['Credit notes', count(today.credit_note_count)],
                ['Customers', count(today.customer_count)],
                ...(full && compare?.last_week_amount
                  ? ([[`vs all of ${compare.label}`, rm(compare.last_week_amount)]] as [string, ReactNode][])
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
        content: link(ROUTES.reorder, 'Open reorder planning'),
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
  const shown = target && !isPending(snapshot) ? body(snapshot, target) : null;
  // Not modal and no scrim: the town behind stays tappable. Escape closes, focus moves in.
  return (
    <Sheet open={shown !== null} onOpenChange={(open) => !open && onClose()} modal={false}>
      <SheetContent
        side="right"
        overlay={false}
        className={`inset-3 start-auto h-auto max-h-[85dvh] gap-0 rounded-lg p-4 sm:inset-y-24 sm:w-80 sm:max-w-none ${CLOSE_HIT_AREA}`}
      >
        <SheetHeader className="space-y-0 pe-8 text-start">
          <SheetTitle>{shown?.title}</SheetTitle>
          <SheetDescription className={shown?.meta ? 'text-xs' : 'sr-only'}>
            {shown?.meta || shown?.title}
          </SheetDescription>
        </SheetHeader>
        <SheetBody className="p-0">{shown?.content}</SheetBody>
      </SheetContent>
    </Sheet>
  );
}
