'use client';

import { ClipboardCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH, fmtInt, fmtSupplierCost } from '../../lib/format';
import type { ReorderRecommendation } from '../types/reorder.types';

/**
 * The things the buyer looks up by hand before deciding, on the row itself.
 *
 * > "got this quantity to order, okay, do i have outstanding PO, do i have incoming, what's
 * >  the outstanding sales quantity, what is the last purchase cost and date"
 *
 * Every figure here is frozen with the recommendation, so the row still reads true next
 * month rather than re-deriving against stock that has since moved. Nothing is fetched:
 * this is what the plan already knows.
 */

/** What "last purchase" is actually telling you. */
const BASIS_NOTE: Record<string, string> = {
  own_segment: '',
  unattributed: 'not attributed to a segment',
  never_purchased: '',
};

function Line({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-end">
        <span className="tabular-nums">{value}</span>
        {note ? <span className="ms-1.5 text-2xs text-muted-foreground">{note}</span> : null}
      </span>
    </div>
  );
}

export function PlanChecklistPopover({
  rec,
  label = 'What the plan checked',
}: {
  rec: ReorderRecommendation;
  label?: string;
}) {
  const basis = rec.last_purchase_basis ?? null;
  // One money format, everywhere: `RM 105.00`, or the supplier's own code when the purchase
  // was not in ringgit. The old build appended the code to a ringgit-glyph figure, so a MYR
  // purchase read `RM 105 MYR` - the currency stated twice, and rounded on top.
  const price = fmtSupplierCost(rec.last_purchase_cost, rec.last_purchase_currency);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label}
          title={label}
          className="inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={(e) => e.stopPropagation()}
        >
          <ClipboardCheck className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-[320px] p-0">
          <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
            <span className="text-xs font-semibold">What the plan checked</span>
            {rec.segment ? (
              <Badge variant="secondary" size="sm" className="font-normal capitalize">
                {rec.segment}
              </Badge>
            ) : null}
          </div>

          <div className="space-y-1 px-3 py-2">
            <Line label="On hand" value={fmtInt(rec.on_hand ?? 0)} />
            {/* Two different questions, kept apart: what is on the water, and what has
                been ordered and not yet received. */}
            <Line label="Incoming (SPO)" value={fmtInt(rec.incoming_spo ?? 0)} />
            <Line label="Outstanding PO" value={fmtInt(rec.outstanding_po ?? 0)} />
            <Line label="Outstanding sales" value={fmtInt(rec.outstanding_sales ?? 0)} />
            <div className="mt-1 flex items-baseline justify-between gap-3 border-t pt-1 text-xs font-medium">
              <span>Net position</span>
              <span className="tabular-nums">
                {rec.net_position == null ? EM_DASH : fmtInt(rec.net_position)}
              </span>
            </div>
          </div>

          <div className="space-y-1 border-t px-3 py-2">
            <Line
              label="Reorder level"
              value={rec.reorder_level == null ? EM_DASH : fmtInt(rec.reorder_level)}
              note={rec.reorder_level_source === 'accepted_suggestion' ? 'suggested' : undefined}
            />
            <Line label="MoQ" value={rec.moq == null ? EM_DASH : fmtInt(rec.moq)} />
            <Line
              label="Order multiple"
              value={rec.order_multiple == null ? EM_DASH : fmtInt(rec.order_multiple)}
            />
          </div>

          <div className="space-y-1 border-t px-3 py-2">
            {basis === 'never_purchased' ? (
              <p className="text-2xs text-muted-foreground">
                Never purchased, so there is no cost to compare against.
              </p>
            ) : (
              <>
                <Line label="Last purchase" value={price} note={BASIS_NOTE[basis ?? ''] || undefined} />
                <Line label="Bought on" value={rec.last_purchase_date ?? EM_DASH} />
              </>
            )}
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

export default PlanChecklistPopover;
