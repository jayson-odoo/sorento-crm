'use client';

import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH, fmtSupplierCost } from '../../lib/format';
import {
  PRICE_ADVICE_LABEL,
  PRICE_ADVICE_TONE,
  describeCheaper,
  describePriceAdvice,
  priceFootnotes,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';

/**
 * Suggestion column: the PRICE to buy at. Result first, verdict second.
 *
 * > "we need a suggested price to buy ... now it just says ask new price last paid etc,
 * >  very confusing, I need the price & supplier column, then only derive at the total
 * >  cost" (user markup, 2026-08-11)
 *
 * The first cut led with the verdict ("Ask new price") and kept the figure in small
 * print, which read as a to-do list rather than a price column. Now the NUMBER the plan
 * costs this line at is the headline, and the verdict rides under it as the caveat.
 * The receipt (order number, exact date, the purchase before) stays in the popup.
 */

const TONE_VARIANT = {
  danger: 'destructive',
  warning: 'warning',
  neutral: 'secondary',
  ok: 'success',
} as const;

/** One money format on this screen: `RM 105.00`, or the supplier's own code. */
function money(amount: number, currency: string | null): string {
  return fmtSupplierCost(amount, currency);
}

export function PlanPriceCell({
  unitCost,
  currency,
  price,
  staleAfterDays,
  purchasable,
  cheaper = null,
}: {
  /** The price the plan is costing this line at - the suggestion itself. */
  unitCost: number | null;
  currency: string | null;
  price: PriceAdvice | undefined;
  staleAfterDays: number;
  purchasable: boolean;
  /** S13e: a materially cheaper supplier on this row's own shortlist, when one exists. */
  cheaper?: CheaperAlternative | null;
}) {
  // An allocation moves stock we already own. There is no supplier and no price to judge.
  if (!purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;

  // No price and no history: the line cannot be costed, and the Status column already
  // says "No price". A dash, not a zero - zero is the trap this column exists to catch.
  const hasFigure = unitCost !== null && unitCost > 0;

  // The switch is only the HEADLINE when the current price has nothing wrong with it:
  // a stale/zero/moved price is the more urgent question, and the cheaper name waits in
  // the popup. One suggestion per cell, or the reviewer reads neither.
  const suggestSwitch = price?.advice === 'recent' && cheaper != null;
  const notes = priceFootnotes(price);
  if (cheaper && !suggestSwitch) {
    notes.push(describeCheaper(cheaper));
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Price history">
          {hasFigure ? (
            <span className="block truncate text-sm font-medium tabular-nums">
              {money(unitCost, currency)}
            </span>
          ) : (
            <span className="block text-muted-foreground" title="No usable price on file">
              {EM_DASH}
            </span>
          )}
          {price ? (
            <Badge
              variant={suggestSwitch ? 'info' : TONE_VARIANT[PRICE_ADVICE_TONE[price.advice]]}
              appearance="light"
              size="sm"
              className="mt-0.5"
            >
              {suggestSwitch
                ? `Ask ${cheaper!.supplier_code} instead`
                : PRICE_ADVICE_LABEL[price.advice]}
            </Badge>
          ) : (
            <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
              No purchase history
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-80 text-xs" align="start">
          <p className="font-medium text-foreground">
            {suggestSwitch ? describeCheaper(cheaper!) : describePriceAdvice(price, staleAfterDays)}
          </p>
          {suggestSwitch ? (
            <p className="mt-1 text-muted-foreground">
              {describePriceAdvice(price, staleAfterDays)}
            </p>
          ) : null}
          {notes.length ? (
            <ul className="mt-2 space-y-1 text-muted-foreground">
              {notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
          {/* The limit, stated where the advice is given. The buyer named it first and the
              screen must not quietly outgrow it. */}
          <p className="mt-3 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own purchase records only.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
