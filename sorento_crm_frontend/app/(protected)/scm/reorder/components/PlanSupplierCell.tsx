'use client';

import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { BASE_CURRENCY, EM_DASH, fmtSupplierCost, isBaseCurrency } from '../../lib/format';
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
 *
 * The supplier is also the BUYER'S to change (AC-R14). Under the name sits a select over
 * this product's own suppliers - the recommendation's proposal first, then its ranked
 * alternatives - and picking another one re-reads THAT supplier's last price and lead
 * time and carries both onto the row's decision and into the draft PO. Read-only when no
 * `onSupplierChange` is given.
 */
export function PlanSupplierCell({
  supplier,
  alternatives,
  price,
  cheaper,
  purchasable,
  chosenCode = null,
  onSupplierChange,
}: {
  supplier: PlanRowSupplier | null;
  alternatives: PlanRowSupplierOption[];
  /** Last/previous purchase from THIS supplier - the receipt behind the choice. */
  price: PriceAdvice | undefined;
  cheaper: CheaperAlternative | null;
  purchasable: boolean;
  /** The supplier the row is currently set to. Null = the engine's own proposal. */
  chosenCode?: string | null;
  /** Record the buyer's switch to another of the product's suppliers. Absent = read-only. */
  onSupplierChange?: (code: string) => void;
}) {
  if (!purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;
  if (!supplier || !supplier.code) {
    return (
      <span className="text-muted-foreground" title="No supplier linked to this product">
        {EM_DASH}
      </span>
    );
  }

  // What the row is SET to, which is the buyer's pick when they made one. The chosen
  // option's own price and lead time replace the engine's on the row.
  const code = chosenCode ?? supplier.code;
  const picked = alternatives.find((a) => a.value === code) ?? null;
  const shown: PlanRowSupplier =
    picked && picked.value !== supplier.code
      ? {
          code: picked.value,
          name: picked.label,
          unit_cost: picked.unit_cost,
          lead_time_days: picked.lead_time_days,
        }
      : supplier;

  const others = alternatives.filter((a) => a.value !== shown.code);
  const lastPo = describeLastPurchase(price?.last ?? null);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Why this supplier">
          <span className="block truncate text-sm font-medium" title={shown.name}>
            {shown.name}
          </span>
          <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
            {shown.lead_time_days > 0
              ? `${shown.code}, ${shown.lead_time_days} day lead`
              : shown.code}
          </span>
        </button>
      </PopoverTrigger>
      {/* The switch sits OUTSIDE the popover trigger: choosing a supplier is a decision,
          not a request to read the case for the current one. */}
      {onSupplierChange && alternatives.length > 1 ? (
        <div className="mt-1">
          <SearchableSelect
            size="sm"
            value={shown.code}
            onChange={onSupplierChange}
            options={alternatives.map((a) => ({
              value: a.value,
              label: a.label,
              description: `${fmtSupplierCost(a.unit_cost, a.currency)}${
                a.lead_time_days > 0 ? `, ${a.lead_time_days} day lead` : ''
              }`,
            }))}
            placeholder="Choose a supplier"
            emptyMessage="No other supplier is linked to this product."
            wrapOptions
            triggerClassName="h-7 text-2xs"
          />
        </div>
      ) : null}
      <PopoverPortal>
        <PopoverContent className="w-80 text-xs" align="start">
          {/* Why them: cheapest costed supplier on this product's own shortlist. */}
          <p className="font-medium text-foreground">
            {shown.code !== supplier.code
              ? `You chose this supplier over ${supplier.name}.`
              : others.length
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
            {shown.lead_time_days > 0 ? (
              <li>{`Standard lead time ${shown.lead_time_days} days.`}</li>
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
                      {/* The price in the money it is quoted in, and beside it the same
                          price restated in base when the two differ - which is the pair
                          the ranking compared. Printed bare, a USD 8.00 option reads
                          cheaper than an RM 10.00 one while costing about three times as
                          much. */}
                      {fmtSupplierCost(a.unit_cost, a.currency)}
                      {a.unit_cost_base !== null && !isBaseCurrency(a.currency)
                        ? ` (${fmtSupplierCost(a.unit_cost_base, BASE_CURRENCY)})`
                        : ''}
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
