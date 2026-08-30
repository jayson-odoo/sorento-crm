'use client';

import { fmtInt } from '../../lib/format';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

/**
 * What a decision is made of, as a table.
 *
 * > "Hovering the Accept button shows a table (location | qty to use, then the buy line),
 * >  not a run-on sentence."
 *
 * The old hover was a sentence built by `describeCover` ("Use 5 from BRW-BB, 1 from PJ-SR,
 * and buy 182"). One location reads fine; three do not, and the buyer was left adding the
 * numbers up themselves to check they came to the shortage. Here every part is one row and
 * the total is printed, so the row either adds up in front of them or it does not.
 *
 * Not a `DataGrid`: this is a three-to-five row summary of ONE row's own decision inside a
 * hover card, with no sorting, paging, selection or column preferences to carry - the grid
 * standard governs listings, and rendering one here would put a fetch behind a tooltip.
 */

export interface CoverBreakdownSource {
  warehouse_code: string;
  qty: number;
}

export function CoverBreakdownTable({
  sources,
  poQty = 0,
  buyQty = 0,
  buyLabel = 'Buy',
  title,
}: {
  /** One row per location the stock comes from. Empty = a pure buy. */
  sources: CoverBreakdownSource[];
  /** Units the open PO book absorbs, if any. Named so the total still adds up. */
  poQty?: number;
  buyQty?: number;
  /** `Buy` while it is a suggestion, `Bought` once the decision is taken. */
  buyLabel?: string;
  title?: string;
}) {
  const total = sources.reduce((t, s) => t + s.qty, 0) + poQty + buyQty;
  return (
    <div className="space-y-1.5">
      {title ? <p className="text-xs font-medium">{title}</p> : null}
      <ScrollArea>
        <table className="w-auto min-w-full text-xs">
          <tbody>
            {sources.map((s) => (
              <tr key={s.warehouse_code}>
                <td className="py-0.5 pe-3 text-muted-foreground">{s.warehouse_code}</td>
                <td className="py-0.5 text-end tabular-nums">{fmtInt(s.qty)}</td>
              </tr>
            ))}
            {poQty > 0 ? (
              <tr>
                <td className="py-0.5 pe-3 text-muted-foreground">PO</td>
                <td className="py-0.5 text-end tabular-nums">{fmtInt(poQty)}</td>
              </tr>
            ) : null}
            {buyQty > 0 ? (
              <tr>
                <td className="py-0.5 pe-3 text-muted-foreground">{buyLabel}</td>
                <td className="py-0.5 text-end tabular-nums">{fmtInt(buyQty)}</td>
              </tr>
            ) : null}
            <tr className="border-t font-medium">
              <td className="pt-1 pe-3">Total</td>
              <td className="pt-1 text-end tabular-nums">{fmtInt(total)}</td>
            </tr>
          </tbody>
        </table>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
}
