'use client';

import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import {
  PRICE_ADVICE_LABEL,
  PRICE_ADVICE_TONE,
  describeCheaper,
  describePriceAdvice,
  priceFootnotes,
  rowFact,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';

/**
 * What we last paid, and whether to go back for a quote.
 *
 * > "i need to know the last PO for this product and this supplier, and the last purchase
 * >  date, i will know how has the market changed and make decision"
 *
 * The plan already used the last paid price as its cost, but only ever showed the number.
 * A number with no date behind it cannot be judged, and on this book almost every price is
 * from a 2020 import - so the cell leads with the age and the verdict, and keeps the figure
 * beside it.
 *
 * Its own column rather than a note on Cost: the quantity decision and the price decision
 * are two different questions, and folding one into the other is what hid the age for so
 * long.
 */

const TONE_VARIANT = {
  danger: 'destructive',
  warning: 'warning',
  neutral: 'secondary',
  ok: 'success',
} as const;

export function PlanPriceCell({
  price,
  staleAfterDays,
  purchasable,
  cheaper = null,
}: {
  price: PriceAdvice | undefined;
  staleAfterDays: number;
  purchasable: boolean;
  /** S13e: a materially cheaper supplier on this row's own shortlist, when one exists. */
  cheaper?: CheaperAlternative | null;
}) {
  // An allocation moves stock we already own. There is no supplier and no price to judge.
  if (!purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;

  // No opinion is not the same as a clean bill of health, so it renders as absence.
  if (!price) {
    return (
      <span className="text-muted-foreground" title="No price history for this supplier">
        {EM_DASH}
      </span>
    );
  }

  const notes = priceFootnotes(price);

  // The switch is only the HEADLINE when the current price has nothing wrong with it:
  // a stale/zero/moved price is the more urgent question, and the cheaper name waits in
  // the popup. One suggestion per cell, or the reviewer reads neither.
  const suggestSwitch = price.advice === 'recent' && cheaper != null;
  if (cheaper && !suggestSwitch) {
    notes.push(describeCheaper(cheaper));
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Price history">
          <Badge
            variant={suggestSwitch ? 'info' : TONE_VARIANT[PRICE_ADVICE_TONE[price.advice]]}
            appearance="light"
            size="sm"
          >
            {suggestSwitch ? `Ask ${cheaper!.supplier_code} instead` : PRICE_ADVICE_LABEL[price.advice]}
          </Badge>
          {/* One plain fact: the price and its age. The receipt (order number, exact
              date) is popup material - on the row it is clutter a reviewer scans past. */}
          <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
            {suggestSwitch
              ? `Their price ${cheaper!.currency ?? ''} ${cheaper!.unit_cost?.toFixed(2)}, ${cheaper!.saving_pct}% less`.trim()
              : rowFact(price)}
          </span>
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
