'use client';

import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import type { PlanRowPriceMode } from '../types/decisions.types';
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
 *
 * The price is also the BUYER'S to set (AC-R13): under the figure sits a two-way switch,
 * Use last price / Ask new price. It rides on the row's own decision and follows it into
 * the draft PO - "ask new" drafts the line unpriced rather than carrying a figure nobody
 * quoted. Read-only when no `onPriceMode` is given.
 */

/** The two price calls, in the order the buyer reads them. */
const PRICE_MODE_OPTIONS: { value: PlanRowPriceMode; label: string }[] = [
  { value: 'use_last', label: 'Use last price' },
  { value: 'ask_new', label: 'Ask new price' },
];

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
  priceMode = 'use_last',
  onPriceMode,
}: {
  /** The price the plan is costing this line at - the suggestion itself. */
  unitCost: number | null;
  currency: string | null;
  price: PriceAdvice | undefined;
  staleAfterDays: number;
  purchasable: boolean;
  /** S13e: a materially cheaper supplier on this row's own shortlist, when one exists. */
  cheaper?: CheaperAlternative | null;
  /** The buyer's own price call (AC-R13). Defaults to the last price. */
  priceMode?: PlanRowPriceMode;
  /** Record a change of price call. Absent = read-only. */
  onPriceMode?: (mode: PlanRowPriceMode) => void;
}) {
  // An allocation moves stock we already own. There is no supplier and no price to judge.
  if (!purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;

  // No price and no history: the line cannot be costed, and the Status column already
  // says "No price". A dash, not a zero - zero is the trap this column exists to catch.
  // Asking for a new price is the same absence, chosen deliberately.
  const asking = priceMode === 'ask_new';
  const hasFigure = !asking && unitCost !== null && unitCost > 0;

  // The switch is only the HEADLINE when the current price has nothing wrong with it:
  // a stale/zero/moved price is the more urgent question, and the cheaper name waits in
  // the popup. One suggestion per cell, or the reviewer reads neither.
  const suggestSwitch = price?.advice === 'recent' && cheaper != null;
  // Which side the ENGINE would take, marked with a star beside the option it suggests.
  // A recent price is one it stands behind; anything else is a price worth re-asking.
  const suggestedMode: PlanRowPriceMode = price?.advice === 'recent' ? 'use_last' : 'ask_new';
  // The row note under the switch: the price problems the two words cannot express.
  const rowNote = !price
    ? 'No purchase history'
    : price.advice === 'recent' || price.advice === 'stale'
      ? suggestSwitch
        ? `Ask ${cheaper!.supplier_code} instead`
        : null
      : PRICE_ADVICE_LABEL[price.advice];
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
            <span
              className="block text-muted-foreground"
              title={asking ? 'Waiting on a new price' : 'No usable price on file'}
            >
              {EM_DASH}
            </span>
          )}
          {/* Read-only: the verdict as a pill. With the switch below it would be the same
              two words twice, so the pill only survives where the buyer cannot choose. */}
          {onPriceMode ? null : price ? (
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
      {/* The pill IS the switch (AC-R13). It sits OUTSIDE the popover trigger: pressing it
          is a decision, not a request to read the receipt. The engine's own verdict marks
          the option it suggests rather than occupying the row with a second copy of the
          same two words. */}
      {onPriceMode ? (
        <>
          <div
            role="radiogroup"
            aria-label="Price to use"
            className="mt-1 inline-flex overflow-hidden rounded-md border border-input"
          >
            {PRICE_MODE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={priceMode === opt.value}
                title={suggestedMode === opt.value ? 'What the price history suggests' : undefined}
                className={`px-1.5 py-0.5 text-2xs ${
                  priceMode === opt.value
                    ? 'bg-primary text-primary-foreground'
                    : suggestedMode === opt.value
                      ? 'font-medium text-foreground hover:bg-muted'
                      : 'text-muted-foreground hover:bg-muted'
                }`}
                onClick={() => onPriceMode(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {/* A price problem the switch cannot express - a zero, a gap, no history at all -
              still has to reach the row. */}
          {rowNote ? (
            <span className="mt-0.5 block truncate text-2xs text-muted-foreground" title={rowNote}>
              {rowNote}
            </span>
          ) : null}
        </>
      ) : null}
      <PopoverPortal>
        <PopoverContent className="w-80 text-xs" align="start">
          {asking ? (
            <p className="mb-2 border-b pb-2 font-medium text-foreground">
              This line is waiting on a new price, so the draft PO goes out unpriced.
            </p>
          ) : null}
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
