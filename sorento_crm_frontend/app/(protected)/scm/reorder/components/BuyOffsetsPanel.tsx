'use client';

import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { fmtInt } from '../../lib/format';
import {
  buyOffsetsFor,
  declineReason,
  grossRequirement,
  qtyWithDeclined,
  type BuyOffsetKey,
} from '../lib/buyOffsets';
import type { M8PlanRow } from '../lib/planRow';

/**
 * What we need, what we propose to cover it with, and what is left to buy.
 *
 * Each offset is a checkbox because each is a claim the buyer is allowed to disagree with.
 * Unticking one does not merely change a number: it stages an adjustment carrying the reason,
 * so the decision is still readable after the run.
 */
export function BuyOffsetsPanel({
  row,
  onApply,
}: {
  row: M8PlanRow;
  /** Stage the adjustment: same path as the inline qty edit. */
  onApply: (qty: number, reason: string) => void;
}) {
  const offsets = useMemo(() => buyOffsetsFor(row), [row]);
  const [declined, setDeclined] = useState<Set<BuyOffsetKey>>(new Set());

  // Nothing was netted, so there is no suggestion to accept or decline and the quantity is
  // simply the requirement. Saying so beats an empty box that looks like a loading failure.
  if (offsets.length === 0) {
    return (
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          What this covers
        </div>
        <p className="text-2xs text-muted-foreground">
          Nothing on hand, incoming, or on order, so the whole requirement is bought.
        </p>
      </div>
    );
  }

  const gross = grossRequirement(row);
  const proposed = qtyWithDeclined(row, declined);
  const changed = proposed !== row.order_qty;

  const toggle = (key: BuyOffsetKey) =>
    setDeclined((d) => {
      const next = new Set(d);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="border-t px-3 py-2">
      <div className="mb-1.5 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
        What this covers
      </div>

      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">Needed</span>
        <span className="tabular-nums">{fmtInt(gross)}</span>
      </div>

      <div className="mt-1.5 space-y-1.5">
        {offsets.map((o) => {
          const id = `offset-${row.id}-${o.key}`;
          const used = !declined.has(o.key);
          return (
            <div key={o.key} className="flex items-start gap-2">
              <Checkbox
                id={id}
                checked={used}
                onCheckedChange={() => toggle(o.key)}
                className="mt-0.5 shrink-0"
              />
              <div className="min-w-0 flex-1">
                <Label htmlFor={id} className="flex justify-between gap-2 text-xs font-normal">
                  <span className={used ? '' : 'text-muted-foreground line-through'}>
                    {o.label}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {used ? `-${fmtInt(o.qty)}` : fmtInt(0)}
                  </span>
                </Label>
                {!used ? (
                  <p className="mt-0.5 text-2xs text-muted-foreground">{o.hint}</p>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-1.5 flex justify-between border-t pt-1.5 text-xs font-medium">
        <span>Buy</span>
        <span className="tabular-nums">
          {changed ? (
            <>
              <span className="me-1.5 font-normal text-muted-foreground line-through">
                {fmtInt(row.order_qty)}
              </span>
              <span className="text-scm-overstock">{fmtInt(proposed)}</span>
            </>
          ) : (
            fmtInt(proposed)
          )}
        </span>
      </div>

      {changed ? (
        <Button
          type="button"
          size="sm"
          className="mt-2 w-full"
          onClick={() => onApply(proposed, declineReason(row, declined))}
        >
          Buy {fmtInt(proposed)} instead
        </Button>
      ) : null}
    </div>
  );
}
