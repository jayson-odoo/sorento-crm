'use client';

import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import {
  PRICE_ADVICE_LABEL,
  PRICE_ADVICE_TONE,
  describePriceAdvice,
  priceFootnotes,
  rowFact,
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
}: {
  price: PriceAdvice | undefined;
  staleAfterDays: number;
  purchasable: boolean;
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

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Price history">
          <Badge
            variant={TONE_VARIANT[PRICE_ADVICE_TONE[price.advice]]}
            appearance="light"
            size="sm"
          >
            {PRICE_ADVICE_LABEL[price.advice]}
          </Badge>
          {/* One plain fact: the price and its age. The receipt (order number, exact
              date) is popup material - on the row it is clutter a reviewer scans past. */}
          <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
            {rowFact(price)}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-80 text-xs" align="start">
          <p className="font-medium text-foreground">
            {describePriceAdvice(price, staleAfterDays)}
          </p>
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
