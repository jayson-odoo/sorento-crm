'use client';

import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH, fmtDate, fmtDecimal, fmtInt, fmtSupplierCost } from '../../lib/format';
import { describePurchaseTrend, type ProductPurchaseTrend } from '../lib/purchaseTrend';
import { humanAge, type PriceAdvice } from '../lib/priceAdvice';

/**
 * The PO cell's mirror of the order-trend popup: the trend of purchase, then the receipts.
 *
 * > "similar to SO - what is the trend of purchase, then the list of supplier, purchase
 * >  date, purchase quantity, purchase cost" (user markup, 2026-08-11)
 *
 * Same interaction as `PlanTrendPopover`: the number is the trigger, the trend sentence
 * and a Supplier/Date/Qty/Unit-cost table live in the popup. Underneath, when the price
 * ledger already holds a last AND a previous purchase (the SAME facts `PlanPriceCell`
 * reads, reused rather than re-fetched), one line answers "how do I know last cost is
 * high vs previous": a signed percentage, never a bare number.
 */
export function PlanPurchaseTrendPopover({
  qty,
  trend,
  windowMonths,
  price,
  onOpen,
}: {
  /** The Outstanding-PO figure already on the row - the trigger text. */
  qty: number | null | undefined;
  trend: ProductPurchaseTrend | undefined;
  windowMonths: number;
  /** The line's chosen-supplier price facts, already fetched for the price column. */
  price?: PriceAdvice;
  /** Fired the first time this popover opens - the caller's cue to lazily start the
   *  purchase-trend fetch instead of it running for every product on plan mount. */
  onOpen?: () => void;
}) {
  const lines = trend?.lines ?? [];
  const hasComparison =
    price?.last != null && price?.previous != null && price.movement_pct !== null;

  return (
    <Popover onOpenChange={(open) => (open ? onOpen?.() : undefined)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="block truncate text-left text-sm tabular-nums underline decoration-dotted underline-offset-2"
          title="Ordered, not yet received - open PO quantity"
          aria-label="Purchase trend"
        >
          {qty === null || qty === undefined ? (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ) : (
            fmtInt(qty)
          )}
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-96 max-w-[92vw] text-xs" align="start">
          <p className="font-medium text-foreground">{describePurchaseTrend(trend, windowMonths)}</p>

          <div className="mt-2">
            <p className="font-medium text-foreground">Recent purchases</p>
            {lines.length ? (
              <table className="mt-0.5 w-full text-muted-foreground">
                <thead>
                  <tr className="text-2xs uppercase text-muted-foreground/70">
                    <th className="pb-0.5 text-left font-normal">Supplier</th>
                    <th className="pb-0.5 text-right font-normal">Date</th>
                    <th className="pb-0.5 text-right font-normal">Qty</th>
                    <th className="pb-0.5 text-right font-normal">Unit cost</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l, i) => (
                    <tr key={`${l.po_number ?? i}-${l.order_date ?? i}`}>
                      <td
                        className="max-w-32 truncate py-0.5"
                        title={l.supplier_name ?? l.supplier_code ?? undefined}
                      >
                        {l.supplier_name ?? l.supplier_code ?? EM_DASH}
                      </td>
                      <td className="py-0.5 text-right tabular-nums">{fmtDate(l.order_date)}</td>
                      <td className="py-0.5 text-right tabular-nums">{fmtInt(l.qty)}</td>
                      <td className="py-0.5 text-right tabular-nums">
                        {fmtSupplierCost(l.unit_cost, l.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-muted-foreground">No purchases in the imported history.</p>
            )}
          </div>

          {/* "How do I know last cost is high vs previous" - the buyer's own question,
              answered with the same facts the price column already carries. */}
          {hasComparison ? (
            <p className="mt-2 border-t pt-2 text-muted-foreground">
              Last {fmtSupplierCost(price!.last!.unit_cost, price!.last!.currency)} vs previous{' '}
              {fmtSupplierCost(price!.previous!.unit_cost, price!.previous!.currency)} (
              {price!.movement_pct! >= 0 ? '+' : ''}
              {fmtDecimal(price!.movement_pct!, 1)}%)
              {price!.last!.issue_date ? `, ${humanAge(price!.age_days)}` : ''}.
            </p>
          ) : null}

          <p className="mt-2 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own purchase records only.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
