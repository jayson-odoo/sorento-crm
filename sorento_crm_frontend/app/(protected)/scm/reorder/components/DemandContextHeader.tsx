'use client';

import { Badge } from '@/components/ui/badge';
import { fmtInt } from '../../lib/format';

/**
 * The trailing-window fields both demand drills share (`PlanDemand` and
 * `OrderSummaryDemandDrill`) - kept structural rather than importing either concrete
 * type, so this header has no opinion on which popover is rendering it.
 */
export interface DemandContextFields {
  project_12m_qty?: number | null;
  retail_3m_qty?: number | null;
  project_window_months?: number | null;
  retail_window_months?: number | null;
}

/**
 * Compact per-channel context header for the demand drills (captain, 20 Aug follow-up):
 *
 * > "for project here, you need to show the past year project order for this item; for
 * >  retail, the last 3 months, for user to judge whether to top up the quantity ordered"
 *
 * This is the historical flow of orders PLACED over the window, whatever their status
 * today - distinct from the committed/open-demand figures the popover already renders
 * above it. Shared by `PlanDemandPopover` and `DemandDrillPopover` so the wording and the
 * window numbers can never drift between the two drills that answer the same question.
 *
 * Zero is a real answer ("nothing ordered in the window") and renders as `0`, never
 * hidden. The whole header is omitted only when the response predates the field (both
 * quantities absent) - the same cached/legacy convention `describeDemandTotals` already
 * uses for the committed-total split.
 */
export function DemandContextHeader({ data }: { data: DemandContextFields }) {
  if (data.project_12m_qty == null && data.retail_3m_qty == null) return null;
  const projectMonths = data.project_window_months ?? 12;
  const retailMonths = data.retail_window_months ?? 3;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5">
      <Badge variant="info" appearance="light" size="sm" className="font-normal">
        {`Project, last ${projectMonths} months: ${fmtInt(data.project_12m_qty ?? 0)}`}
      </Badge>
      <Badge variant="success" appearance="light" size="sm" className="font-normal">
        {`Retail, last ${retailMonths} months: ${fmtInt(data.retail_3m_qty ?? 0)}`}
      </Badge>
    </div>
  );
}

export default DemandContextHeader;
