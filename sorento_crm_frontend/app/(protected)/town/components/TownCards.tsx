'use client';

import type { ReactNode } from 'react';
import { Receipt, Ship } from 'lucide-react';
import { cn } from '@/lib/utils';
import { COARSE_HIT_TARGET_CLASS, PRESSED_CLASS } from '@/components/ui/primitive-classes';
import { formatDateInMalaysia } from '@/lib/helpers';
import { isPending, type TownPayload } from '@/types/town.types';
import {
  boughtToday,
  changePercent,
  compactCount,
  count,
  rm,
  shopLabel,
  shopToday,
  signedPercent,
} from '../lib/townFormat';
import type { TownTarget } from './TownLightbox';

function Card({
  question,
  icon,
  tone,
  onClick,
  children,
}: {
  question: string;
  icon: ReactNode;
  tone: string;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-0.5 rounded-lg border border-border bg-card p-3 text-start',
        PRESSED_CLASS,
        COARSE_HIT_TARGET_CLASS,
      )}
    >
      <span
        className={cn(
          'row-span-3 grid min-h-[2.125rem] min-w-[2.125rem] w-auto place-items-center rounded-lg px-1.5 text-sm font-bold text-white',
          tone,
        )}
        aria-hidden="true"
      >
        {icon}
      </span>
      <span className="text-xs text-muted-foreground">{question}</span>
      {children}
    </button>
  );
}

/** The five answers as plain cards: the only view without WebGL or with reduced motion. */
export function TownCards({
  snapshot,
  onOpen,
}: {
  snapshot: TownPayload;
  onOpen?: (target: TownTarget) => void;
}) {
  if (isPending(snapshot)) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center">
        <h2 className="text-base font-semibold">No figures yet</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          The town fills in once the first snapshot of the day is ready.
        </p>
      </div>
    );
  }
  const { today, compare, reorder, deliveries, approvals, incoming } = snapshot;
  const { bought, others } = boughtToday(snapshot);
  const pct = changePercent(snapshot);
  const open = (target: TownTarget) => () => onOpen?.(target);
  return (
    <div className="grid gap-2.5">
      <Card
        question="How much did we sell today?"
        icon={<Receipt className="size-4" />}
        tone="bg-teal-700"
        onClick={open({ kind: 'sales' })}
      >
        <span className="text-xl font-bold tracking-tight">
          {today.amount != null ? rm(today.amount) : `${count(today.invoice_count)} invoices`}
        </span>
        <span className="text-sm text-muted-foreground">
          {today.amount != null ? `${count(today.invoice_count)} invoices` : null}
          {today.amount != null && pct != null ? ' · ' : null}
          {pct != null && compare ? (
            <>
              <span className={pct >= 0 ? 'font-semibold text-success' : 'font-semibold text-destructive'}>
                {signedPercent(pct)}
              </span>{' '}
              vs all of {compare.label}
            </>
          ) : null}
        </span>
      </Card>
      <Card
        question="Who bought today?"
        icon={compactCount(bought.length + others)}
        tone="bg-amber-500"
        onClick={open({ kind: 'bought' })}
      >
        <span className="text-xl font-bold tracking-tight">
          {count(today.dealer_customer_count || bought.length)} dealers
        </span>
        <span className="mt-1.5 grid min-w-0 gap-1 text-sm">
          {bought.slice(0, 5).map((shop) => (
            <span key={shop.key} className="flex min-w-0 justify-between gap-2">
              <span className="min-w-0 truncate" title={shopLabel(shop)}>
                {shopLabel(shop)}
              </span>
              <span className="shrink-0 whitespace-nowrap tabular-nums">{shopToday(shop)}</span>
            </span>
          ))}
        </span>
      </Card>
      <Card
        question="What stock is low?"
        icon="!"
        tone="bg-destructive"
        onClick={open({ kind: 'low' })}
      >
        <span className="text-xl font-bold tracking-tight">{count(reorder.below_count)} products</span>
        <span className="text-sm text-muted-foreground">below reorder level</span>
      </Card>
      <Card
        question="What must go out?"
        icon={deliveries ? compactCount(deliveries.to_deliver) : '-'}
        tone="bg-blue-600"
        onClick={open({ kind: 'deliver' })}
      >
        <span className="text-xl font-bold tracking-tight">
          {deliveries ? `${count(deliveries.to_deliver)} to deliver` : '-'}
        </span>
        <span className="text-sm text-muted-foreground">sales orders due</span>
      </Card>
      <Card
        question="What needs a decision?"
        icon={compactCount(approvals.total)}
        tone="bg-violet-600"
        onClick={open({ kind: 'approve' })}
      >
        <span className="text-xl font-bold tracking-tight">
          {approvals.total ? `${approvals.total} waiting` : 'All clear'}
        </span>
        <span className="text-sm text-muted-foreground">
          {approvals.purchase_requests} purchase request{approvals.purchase_requests === 1 ? '' : 's'} ·{' '}
          {approvals.quotation_documents} quotation{approvals.quotation_documents === 1 ? '' : 's'}
        </span>
      </Card>
      {incoming ? (
        <Card
          question="What is coming in?"
          icon={<Ship className="size-4" />}
          tone="bg-cyan-700"
          onClick={open({ kind: 'port' })}
        >
          <span className="text-xl font-bold tracking-tight">
            {incoming.incoming || incoming.late ? `${count(incoming.incoming)} incoming` : 'Nothing on the way'}
          </span>
          <span className="text-sm text-muted-foreground">
            {incoming.late ? (
              <span className="font-semibold text-destructive">{count(incoming.late)} late</span>
            ) : null}
            {incoming.late && incoming.next_eta ? ' · ' : null}
            {incoming.next_eta ? `next ETA ${formatDateInMalaysia(incoming.next_eta)}` : null}
            {incoming.incoming && !incoming.late && !incoming.next_eta ? 'No ETA yet' : null}
          </span>
        </Card>
      ) : null}
    </div>
  );
}
