'use client';

import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import type { PlanRowSupplier, PlanRowSupplierOption } from '../lib/planRow';
import {
  describeCheaper,
  describeLastPurchase,
  humanAge,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';

/**
 * Suggestion column: the SUPPLIER to buy from. Result first, justification behind it.
 *
 * > "also the suggested supplier ... should have detail to justify why this supplier and
 * >  why this cost, that's where we go into last PO, and the supplier, and also the
 * >  supplier performance" (user markup, 2026-08-11)
 *
 * The name is the row; the case for the name is the popup: the last PO we cut them, how
 * long they take, who else is on this product's shortlist at what price, and the cheaper
 * alternative when one exists. All of it from our own records - nothing here claims to
 * know the market.
 */
export function PlanSupplierCell({
  supplier,
  alternatives,
  price,
  cheaper,
  purchasable,
}: {
  supplier: PlanRowSupplier | null;
  alternatives: PlanRowSupplierOption[];
  /** Last/previous purchase from THIS supplier - the receipt behind the choice. */
  price: PriceAdvice | undefined;
  cheaper: CheaperAlternative | null;
  purchasable: boolean;
}) {
  if (!purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;
  if (!supplier || !supplier.code) {
    return (
      <span className="text-muted-foreground" title="No supplier linked to this product">
        {EM_DASH}
      </span>
    );
  }

  const others = alternatives.filter((a) => a.value !== supplier.code);
  const lastPo = describeLastPurchase(price?.last ?? null);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Why this supplier">
          <span className="block truncate text-sm font-medium" title={supplier.name}>
            {supplier.name}
          </span>
          <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
            {supplier.lead_time_days > 0
              ? `${supplier.code}, ${supplier.lead_time_days} day lead`
              : supplier.code}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-80 text-xs" align="start">
          {/* Why them: cheapest costed supplier on this product's own shortlist. */}
          <p className="font-medium text-foreground">
            {others.length
              ? `Cheapest of the ${others.length + 1} suppliers linked to this product.`
              : 'The only supplier linked to this product.'}
          </p>

          <ul className="mt-2 space-y-1 text-muted-foreground">
            {lastPo ? (
              <li>
                {`Last PO: ${lastPo}`}
                {price?.age_days != null ? ` (${humanAge(price.age_days)})` : ''}
              </li>
            ) : (
              <li>Never bought from them - no PO on record.</li>
            )}
            {supplier.lead_time_days > 0 ? (
              <li>{`Standard lead time ${supplier.lead_time_days} days.`}</li>
            ) : (
              <li>No lead time on file.</li>
            )}
            {cheaper ? <li>{describeCheaper(cheaper)}</li> : null}
          </ul>

          {others.length ? (
            <div className="mt-2 border-t pt-2">
              <p className="font-medium text-foreground">Also on the shortlist</p>
              <ul className="mt-1 space-y-0.5 text-muted-foreground">
                {others.map((a) => (
                  <li key={a.value} className="flex justify-between gap-2">
                    <span className="truncate" title={a.label}>{a.label}</span>
                    <span className="shrink-0 tabular-nums">
                      {a.unit_cost.toFixed(2)}
                      {a.lead_time_days > 0 ? `, ${a.lead_time_days}d` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="mt-3 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own purchase records only.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
