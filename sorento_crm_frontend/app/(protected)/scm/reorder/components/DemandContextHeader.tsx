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
 * The channel the row being drilled belongs to. Wide enough to take either caller's own
 * vocabulary unconverted - `PlanChannel` on the plan grid, `OrderSummaryDemandKind` on the
 * summary report - because only one distinction is made here: project, or not.
 */
export type DemandContextChannel = 'project' | 'retail' | 'unclassified' | 'dealer';

/**
 * Compact context header for the demand drills (captain, 20 Aug follow-up):
 *
 * > "for project here, you need to show the past year project order for this item; for
 * >  retail, the last 3 months, for user to judge whether to top up the quantity ordered"
 *
 * ONE badge, the drilled row's OWN channel (P5, captain 25 Aug). It used to render both,
 * so a project row was told its retail history and a retail row its project year - two
 * numbers where the question had one, and the reader had to work out which of them was
 * theirs. A row that is not project reads the retail window, the same fallback the
 * neighbouring "no orders in the last N full months" line already takes.
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
 *
 * Both windows are FULL calendar months, and stop at the end of last month - the same
 * boundary `trajectory_service.demand_context_for_product` shares with the plan's own
 * trend verdict (`trajectory_for_run`), on purpose, so this figure and the verdict badge
 * elsewhere on the row can never disagree about what "recent" means (S9, code review 20
 * Aug 2026). Labelled "full months" here rather than quietly including today's partial
 * one, which would say more than the number actually counts.
 */
export function DemandContextHeader({
  data,
  channel,
}: {
  data: DemandContextFields;
  channel?: DemandContextChannel;
}) {
  if (data.project_12m_qty == null && data.retail_3m_qty == null) return null;
  const isProject = channel === 'project';
  const months = isProject
    ? (data.project_window_months ?? 12)
    : (data.retail_window_months ?? 3);
  const qty = isProject ? data.project_12m_qty : data.retail_3m_qty;
  const title = 'Full calendar months only - the month in progress is not counted yet.';
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5">
      <Badge
        variant={isProject ? 'info' : 'success'}
        appearance="light"
        size="sm"
        className="font-normal"
        title={title}
      >
        {`${isProject ? 'Project' : 'Retail'}, last ${months} full months: ${fmtInt(qty ?? 0)}`}
      </Badge>
    </div>
  );
}

export default DemandContextHeader;
