'use client';

import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH, fmtDecimal } from '../../lib/format';
import type { RankFactor } from '../../services/fulfilmentService';

/**
 * Why this line ranked where it did (AC-E7).
 *
 * A rank a planner cannot decompose is one they stop trusting the first time it disagrees
 * with them, so every factor is shown with its weight and its value - including the ones
 * weighted zero, because "the policy ignores need-by today" is itself the answer to half the
 * questions this popover gets opened for.
 */

const FACTOR_LABELS: Record<string, string> = {
  po_document_sequence: 'Order sequence',
  demand_class: 'Demand class',
  need_by_date: 'Needed by',
  document_age: 'Order age',
};

function pct(v: number | null): string {
  return v === null ? EM_DASH : `${Math.round(v * 100)}%`;
}

/**
 * Shared with the Stage 1 container-request grid (`ContainerRequestSection`), which carries
 * `rank_score` / `rank_factors` on a row shape that is not a `LoadingPlanLine` - the prop is
 * the subset both actually use, not the loading-plan line itself.
 *
 * `PopoverContent` is wrapped in `PopoverPortal` (captain, live test): both grids render this
 * trigger inside a `DataGrid` cell, whose sticky/pinned columns paint OVER an un-portaled
 * popover - a sibling `position: sticky` cell wins the cell's own stacking context. Portaling
 * to `document.body` escapes it. See `SoLinesDrillPopover.tsx` for the same fix, same cause.
 */
export interface RankedLine {
  rank_score: number | null;
  factors: RankFactor[];
}

export function RankFactorsPopover({ line }: { line: RankedLine }) {
  const score = fmtDecimal(line.rank_score, 2);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 px-2 tabular-nums">
          {score}
        </Button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-72" align="end">
          <h4 className="text-xs font-semibold">How this line ranked</h4>
          <table className="mt-2 w-full text-2xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="text-start font-normal">Factor</th>
                <th className="text-end font-normal">Weight</th>
                <th className="text-end font-normal">Value</th>
              </tr>
            </thead>
            <tbody>
              {line.factors.map((f) => (
                <tr key={f.key} className={f.weight === 0 ? 'text-muted-foreground' : undefined}>
                  <td className="py-0.5">{FACTOR_LABELS[f.key] ?? f.key}</td>
                  <td className="py-0.5 text-end tabular-nums">{f.weight}</td>
                  <td className="py-0.5 text-end tabular-nums">
                    {f.present ? pct(f.value) : 'not known'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-2xs text-muted-foreground">
            Score {score}. A factor with no weight does not move it.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

export default RankFactorsPopover;
