'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import { isPending, type TownPayload, type TownShipment, type TownSnapshot } from '@/types/town.types';
import { boughtToday, count, rm, shopLabel, shopToday } from '../lib/townFormat';

export type TownTarget =
  | { kind: 'sales' }
  | { kind: 'bought' }
  | { kind: 'shop'; key: string }
  | { kind: 'low' }
  | { kind: 'deliver' }
  | { kind: 'approve' }
  | { kind: 'port' };

/** The existing screens a lightbox opens (each is permission-checked by its own page). */
const ROUTES = {
  sales: '/sales/sales-and-outstanding',
  invoices: '/finance/billing-documents',
  reorder: '/scm/reorder',
  deliveries: '/scm/sales-orders',
  approvals: '/procurement-management/purchase-requests',
  shipments: '/procurement-management/packing-lists',
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

/** One section of the port lightbox. Both sections always show, with a short hint at zero; whether
 * the Supplier column shows is decided once for both, so the two tables keep the same columns. */
function Shipments({
  title,
  rows,
  total,
  supplier,
  empty,
  late,
}: {
  title: string;
  rows: TownShipment[];
  total: number;
  supplier: boolean;
  empty: string;
  late?: boolean;
}) {
  return (
    <section className="mt-4 first:mt-0">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        {title}
        <Badge variant={late ? 'destructive' : 'secondary'} appearance={late ? 'light' : undefined} size="sm">
          {count(total)}
        </Badge>
      </h3>
      {total ? (
        <div className="mt-1.5 overflow-x-auto">
          <table className="w-full text-xs sm:text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="py-1.5 pe-2 sm:pe-3 text-start font-medium">Shipment</th>
                <th className="hidden py-1.5 pe-2 sm:pe-3 text-start font-medium sm:table-cell">Container</th>
                {supplier ? <th className="py-1.5 pe-2 sm:pe-3 text-start font-medium">Supplier</th> : null}
                <th className="py-1.5 pe-2 sm:pe-3 text-start font-medium">ETA</th>
                <th className="hidden py-1.5 pe-2 sm:pe-3 text-end font-medium sm:table-cell">Products</th>
                <th className="py-1.5 text-end font-medium">Qty</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.shipment_number ?? ''}-${index}`} className="border-b border-border last:border-0">
                  <td className="whitespace-nowrap py-1.5 pe-2 sm:pe-3">{row.shipment_number ?? '-'}</td>
                  <td className="hidden whitespace-nowrap py-1.5 pe-2 sm:pe-3 sm:table-cell">{row.container ?? '-'}</td>
                  {supplier ? (
                    <td className="max-w-24 truncate py-1.5 sm:max-w-40 pe-2 sm:pe-3" title={row.supplier ?? undefined}>
                      {row.supplier ?? '-'}
                    </td>
                  ) : null}
                  <td className="whitespace-nowrap py-1.5 pe-2 sm:pe-3">{row.eta ? formatDateInMalaysia(row.eta) : 'No ETA'}</td>
                  <td className="hidden py-1.5 pe-2 sm:pe-3 text-end tabular-nums sm:table-cell">{count(row.products)}</td>
                  <td className="py-1.5 text-end tabular-nums">{count(row.quantity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-1.5 text-sm text-muted-foreground">{empty}</p>
      )}
      {total > rows.length ? (
        <p className="mt-1.5 text-sm text-muted-foreground">+ {count(total - rows.length)} more</p>
      ) : null}
    </section>
  );
}

function body(snapshot: TownSnapshot, target: TownTarget): { title: string; meta: string; content: ReactNode } {
  const { today, compare, reorder, deliveries, approvals } = snapshot;
  const link = (href: string, label: string) => (
    <Button asChild variant="outline" size="sm" className="mt-4">
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
    case 'port': {
      const incoming = snapshot.incoming;
      const total = incoming ? incoming.incoming + incoming.late : 0;
      const supplier = !!incoming?.shipments.some((row) => row.supplier);
      return {
        title: 'Incoming shipments',
        meta: '',
        content: (
          <>
            {incoming && total ? (
              <>
                <Shipments
                  title="Incoming"
                  rows={incoming.shipments.filter((row) => !row.late)}
                  total={incoming.incoming}
                  supplier={supplier}
                  empty="None on the way"
                />
                <Shipments
                  title="Late"
                  rows={incoming.shipments.filter((row) => row.late)}
                  total={incoming.late}
                  supplier={supplier}
                  empty="None late"
                  late
                />
              </>
            ) : (
              <div className="py-6 text-center">
                <h3 className="text-sm font-semibold">Nothing on the way</h3>
              </div>
            )}
            {link(ROUTES.shipments, 'Open packing lists')}
          </>
        ),
      };
    }
  }
}

/** What a tap on a building, a label or a card opens: a centred lightbox over the town (owner, 10 Nov:
 * popups over side panels). Escape, the close button or a click outside closes it. */
export function TownLightbox({
  snapshot,
  target,
  onClose,
}: {
  snapshot: TownPayload;
  target: TownTarget | null;
  onClose: () => void;
}) {
  const shown = target && !isPending(snapshot) ? body(snapshot, target) : null;
  const wide = target?.kind === 'port';
  return (
    <Dialog open={shown !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={wide ? 'sm:max-w-2xl' : 'sm:max-w-md'}>
        <DialogHeader className="mb-2 space-y-0 pe-8 text-start">
          <DialogTitle>{shown?.title}</DialogTitle>
          <DialogDescription className={shown?.meta ? 'text-xs' : 'sr-only'}>
            {shown?.meta || shown?.title}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>{shown?.content}</DialogBody>
      </DialogContent>
    </Dialog>
  );
}
