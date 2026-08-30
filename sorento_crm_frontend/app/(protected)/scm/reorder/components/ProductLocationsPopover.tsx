'use client';

import { useState } from 'react';
import { AlertCircle, MapPin } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { EM_DASH, fmtDecimal } from '../../lib/format';
import { fmtQty } from '../lib/qtyPrecision';
import { useOrderSummaryLocations } from '../hooks/useSummaryOrder';

/**
 * The locations behind one product row (AC-F08).
 *
 * The Product row is one row per product and its channel readings are analysis
 * inside it, so the question it cannot answer on its own is "where". This drill
 * answers exactly that, and it is the same drill whichever grain the run is
 * decided at - under Product policy the per-location view is a read and drill
 * view, not a decision surface (AC-F02), and there is no decision control here.
 *
 * Two rules the layout enforces:
 *
 * - **Demand is split by channel, supply is not.** Project and Retail
 *     are two demand columns; stock, incoming SPO, PO and the
 *     reorder level are single shared facts of the product-location, printed once
 *     (AC-F07). Repeating them per channel would double the supply on screen.
 * - **The once-rounded product figure is stated beside the split**, so the
 *     reader can check that the location quantities sum EXACTLY to the chosen
 *     quantity and that the supplier rounding happened once, at the product
 *     (AC-E06 / AC-F11 / AC-F12).
 */
export interface ProductLocationsPopoverProps {
  productCode: string;
  productName?: string | null;
  /** Opaque run key, so a past week drills to that week's frozen locations. */
  runId: string | null;
  /** The row's frozen `uom_decimal_places`, so a `kg` split is not shown as whole units. */
  decimalPlaces?: number;
  /** What the trigger says. The Retail reading opens the same drill by another name. */
  triggerLabel?: string;
  /** Rendered instead of the default pill trigger, when a cell supplies its own. */
  children?: React.ReactNode;
}

export function ProductLocationsPopover({
  productCode,
  productName,
  runId,
  decimalPlaces = 0,
  triggerLabel = 'Locations',
  children,
}: ProductLocationsPopoverProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, error, refetch } = useOrderSummaryLocations(
    productCode,
    runId,
    open,
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {children ?? (
          <button
            type="button"
            onClick={(e) => e.stopPropagation()}
            aria-label={`Member locations for ${productCode}`}
            className="inline-flex items-center gap-1 rounded-sm text-2xs text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <MapPin className="size-3.5 shrink-0" aria-hidden />
            {triggerLabel}
          </button>
        )}
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          align="end"
          collisionPadding={8}
          onClick={(e) => e.stopPropagation()}
          className="w-[min(34rem,calc(100vw-2rem))] p-0"
        >
          <div className="flex flex-col gap-1 border-b px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 break-words">
              <div className="text-xs font-semibold">Member locations</div>
              <div className="text-2xs text-muted-foreground">
                {productCode}
                {productName ? ` · ${productName}` : ''}
              </div>
            </div>
            {data ? (
              <Badge variant="secondary" appearance="light" size="xs" className="w-fit shrink-0">
                {data.locations.length} location{data.locations.length === 1 ? '' : 's'}
              </Badge>
            ) : null}
          </div>

          {isLoading ? (
            <div className="space-y-2 p-3" aria-label="Loading member locations" aria-busy="true">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full rounded-md" />
              ))}
            </div>
          ) : isError || !data ? (
            <div className="flex flex-col items-center gap-2 p-4 text-center">
              <AlertCircle className="size-4 text-destructive" aria-hidden />
              <p className="text-2xs text-muted-foreground">
                {error instanceof Error ? error.message : 'Failed to load the member locations.'}
              </p>
              <Button variant="outline" size="sm" onClick={() => void refetch()}>
                Try again
              </Button>
            </div>
          ) : data.locations.length === 0 ? (
            <div className="px-3 py-4 text-center text-2xs text-muted-foreground">
              This product holds no stock and no demand at any location in this plan.
            </div>
          ) : (
            <>
              <div className="max-h-72 overflow-auto" data-testid="location-rows">
                {/* One scroller, both axes: a nested one broke the sticky head.

                    The head is opaque and layered. `bg-muted/60` let forty rows
                    of figures show through it as they scrolled past, which reads
                    as a rendering fault long before it reads as a header.
                    Measured in the browser first: `border-collapse` does NOT
                    stop a thead sticking here, so the table keeps it. */}
                <table className="w-auto min-w-full text-2xs">
                  <thead className="sticky top-0 z-10 bg-popover text-muted-foreground">
                    <tr>
                      <th className="px-2 py-1.5 text-start font-medium">Location</th>
                      {/* These two are the row's `_need` figures - the confirmed-for-buy
                          / already-netted leg (same fields PlanLinesGrid's ungrouped grid
                          labels "Project need" / "Retail need"), NOT
                          a per-location split of a grouped row's channel columns (those read
                          `*_committed`, the channel's WHOLE open demand, and this endpoint
                          does not carry a location-level committed split at all - see
                          `app/services/scm/summary_order_service.py::locations` and
                          `OrderSummaryLocationRowOut` in `app/schemas/scm_order_summary.py`,
                          backend). Captain caught this exact mislabel on SRT-H3005: a bare
                          "Project"/"Retail" header here reads as the same fact as the group
                          row's channel cell, and it is not. */}
                      <th
                        className="px-2 py-1.5 text-end font-medium"
                        title="What CS asked for, less what is already on a PO or SPO. Firm: Retail netting never reduces it"
                      >
                        Project need
                      </th>
                      <th
                        className="px-2 py-1.5 text-end font-medium"
                        title="Retail-class need, after the normal netting of free supply"
                      >
                        Retail need
                      </th>
                      <th className="px-2 py-1.5 text-end font-medium">Stock</th>
                      <th className="px-2 py-1.5 text-end font-medium">SPO</th>
                      <th className="px-2 py-1.5 text-end font-medium">PO</th>
                      <th className="px-2 py-1.5 text-end font-medium">Level</th>
                      <th className="px-2 py-1.5 text-end font-medium">Split</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.locations.map((l) => (
                      <tr key={l.warehouse_code} className="border-b last:border-b-0">
                        <td className="px-2 py-1.5">
                          <div className="truncate font-medium" title={l.warehouse_name}>
                            {l.warehouse_code}
                          </div>
                          <div className="truncate text-muted-foreground" title={l.warehouse_name}>
                            {l.avg_daily_demand === null
                              ? 'no demand rate'
                              : `${fmtDecimal(l.avg_daily_demand)}/day`}
                          </div>
                        </td>
                        <Channel value={l.project_need} dp={decimalPlaces} />
                        <Channel value={l.retail_need} dp={decimalPlaces} />
                        {/* Shared supply, once. It carries no channel dimension. */}
                        <td className="px-2 py-1.5 text-end tabular-nums">
                          {fmtQty(l.on_hand, decimalPlaces)}
                        </td>
                        <td className="px-2 py-1.5 text-end tabular-nums">
                          {fmtQty(l.incoming_spo, decimalPlaces)}
                        </td>
                        <td className="px-2 py-1.5 text-end tabular-nums">
                          {fmtQty(l.on_order_po, decimalPlaces)}
                        </td>
                        <td className="px-2 py-1.5 text-end tabular-nums">
                          {l.reorder_level === null ? (
                            <span className="text-muted-foreground" title="No level set here">
                              {EM_DASH}
                            </span>
                          ) : (
                            fmtQty(l.reorder_level, decimalPlaces)
                          )}
                        </td>
                        <td className="px-2 py-1.5 text-end tabular-nums">
                          {l.allocated_qty === null ? (
                            <span className="text-muted-foreground">{EM_DASH}</span>
                          ) : (
                            <span className="font-medium">
                              {fmtQty(l.allocated_qty, decimalPlaces)}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* What the product row decided, restated so the split reconciles to it. */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-t px-3 py-2 text-2xs">
                <span className="text-muted-foreground">
                  Suggested once at the product:{' '}
                  <span className="font-medium tabular-nums text-foreground">
                    {fmtQty(data.suggested_qty, decimalPlaces)}
                  </span>
                  {data.uom ? ` ${data.uom}` : ''}
                </span>
                <span className="text-muted-foreground">
                  {data.chosen_qty === null ? (
                    'No quantity chosen yet'
                  ) : (
                    <>
                      Chosen:{' '}
                      <span className="font-medium tabular-nums text-foreground">
                        {fmtQty(data.chosen_qty, decimalPlaces)}
                      </span>
                      {data.uom ? ` ${data.uom}` : ''}
                    </>
                  )}
                </span>
              </div>

              {data.is_legacy ? (
                <div className="border-t px-3 py-2 text-2xs text-muted-foreground">
                  This plan predates front planning, so its channel breakdown is unavailable.
                </div>
              ) : null}
            </>
          )}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/** A channel demand cell. Null is UNAVAILABLE on a legacy run, and says so. */
function Channel({ value, dp }: { value: number | null; dp: number }) {
  return (
    <td className="px-2 py-1.5 text-end tabular-nums">
      {value === null ? (
        <span className="text-muted-foreground" title="Unavailable on a legacy plan">
          Unavailable
        </span>
      ) : (
        fmtQty(value, dp)
      )}
    </td>
  );
}

export default ProductLocationsPopover;
