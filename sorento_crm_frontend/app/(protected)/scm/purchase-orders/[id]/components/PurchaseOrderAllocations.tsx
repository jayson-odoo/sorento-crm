'use client';

import { Card, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { EM_DASH, fmtInt } from '../../../lib/format';
import type { PurchaseOrderLineAllocation } from '../../../types/scm.types';

/**
 * Allocated to - who is already waiting on this purchase order's lines (section 3.G,
 * AC-G1/AC-G2).
 *
 * BESIDE THE LINE, NEVER IN IT. The captain, 25 August 2026: the buyer re-keys the split in
 * AutoCount and re-uploads the book, and an upload overwriting our split would lose it. So
 * this sits BELOW the lines grid as its own panel; nothing here is a column of that grid and
 * nothing here is editable. There is no "Split for AutoCount" section: AC-G2 withdrew it,
 * and the "location differs" mark on each placement IS the split instruction.
 *
 * THE THREE FIGURES PER LINE. `Outstanding` is what is still to arrive on the line (the same
 * figure the grid above prints), `Allocated` is the sum of every order-inquiry link on it,
 * and `Free` is what is left. They are computed on the server off one reader, so this panel
 * and the order-inquiry worklist cannot come to disagree about where a quantity sits.
 *
 * NO IDS. The inquiry reads as its number, the sales order as its document number, the
 * customer and the agent as the labels the worklist already prints for them.
 */
export function PurchaseOrderAllocations({
  allocations,
}: {
  allocations: PurchaseOrderLineAllocation[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Allocated to</CardTitle>
        </CardHeading>
      </CardHeader>
      <div className="p-4">
        {allocations.length === 0 ? (
          // Rendered whatever the data says, with an explicit empty state and the next step:
          // a hidden section on a detail page is a code-review hard fail, and a buyer who
          // sees nothing cannot tell "nobody is waiting on this" from "the panel is broken".
          <p className="text-sm text-muted-foreground">
            No order inquiry is linked to this purchase order yet. Purchasing links one from
            Order inquiries.
          </p>
        ) : (
          <div className="space-y-5">
            {allocations.map((line) => (
              <section key={line.line_id} className="space-y-2">
                <div className="flex flex-col gap-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4">
                  <span className="truncate font-medium" title={line.sku}>
                    {line.sku}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {line.warehouse_code || EM_DASH}
                  </span>
                  <span className="text-sm tabular-nums text-muted-foreground">
                    Outstanding{' '}
                    <span className="font-medium text-foreground">
                      {fmtInt(line.outstanding)}
                    </span>
                  </span>
                  <span className="text-sm tabular-nums text-muted-foreground">
                    Allocated{' '}
                    <span className="font-medium text-foreground">
                      {fmtInt(line.allocated)}
                    </span>
                  </span>
                  <span className="text-sm tabular-nums text-muted-foreground">
                    Free{' '}
                    <span className="font-medium text-foreground">{fmtInt(line.free)}</span>
                  </span>
                </div>

                <ScrollArea>
                  <table className="w-full min-w-[640px] text-sm">
                    <thead>
                      <tr className="text-2xs uppercase tracking-wide text-muted-foreground">
                        <th className="py-1 pr-3 text-left font-medium">Order inquiry</th>
                        <th className="py-1 pr-3 text-left font-medium">Sales order</th>
                        <th className="py-1 pr-3 text-left font-medium">Customer</th>
                        <th className="py-1 pr-3 text-left font-medium">Agent</th>
                        <th className="py-1 pr-3 text-right font-medium">Qty</th>
                        <th className="py-1 text-left font-medium">Needed at</th>
                      </tr>
                    </thead>
                    <tbody>
                      {line.placements.map((placement, index) => (
                        <tr
                          key={`${line.line_id}-${index}`}
                          className="border-t border-border/60"
                        >
                          <td className="py-1.5 pr-3">{placement.inquiry_no || EM_DASH}</td>
                          <td className="py-1.5 pr-3">{placement.so_number || EM_DASH}</td>
                          <td
                            className="max-w-[240px] truncate py-1.5 pr-3"
                            title={placement.customer || undefined}
                          >
                            {placement.customer || EM_DASH}
                          </td>
                          <td
                            className="max-w-[140px] truncate py-1.5 pr-3"
                            title={placement.agent || undefined}
                          >
                            {placement.agent || EM_DASH}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums">
                            {fmtInt(placement.qty)}
                          </td>
                          <td className="py-1.5">
                            <span className="flex flex-wrap items-center gap-1.5">
                              <span>{placement.needed_at || EM_DASH}</span>
                              {placement.location_differs ? (
                                // The split instruction, said where the buyer is looking:
                                // this quantity has to be re-keyed onto a line at the
                                // demand's own location before the book goes back up.
                                <Badge variant="warning" appearance="light" size="sm">
                                  Location differs
                                </Badge>
                              ) : null}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              </section>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

export default PurchaseOrderAllocations;
