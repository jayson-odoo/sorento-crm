'use client';

import * as React from 'react';
import { Info } from 'lucide-react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { factorLabel } from '../../_shared/lib/fulfilmentBoard';
import type { BoardContribution } from '../../_shared/types/fulfilmentPlanning.types';

/**
 * How this row's rank was arrived at (the captain: "how is the rank calculated? can have an
 * information tooltip to show the calculation").
 *
 * The number in the Rank column is `SUM(w x v) / SUM(w present)` over the active
 * `scm.priority_policy`, and until now the only way to see the terms was hover text - a
 * paragraph, truncated, and impossible to check against a second row. So the terms are a
 * TABLE: one row per factor with the FACT behind it first, then its normalised score, the
 * policy's weight, and the product of the two; the footer is the division itself.
 *
 * A real `<table>` and not the shared DataGrid on purpose: this is five aligned columns of
 * arithmetic inside a popover, not a listing - no sorting, no paging, no column preferences.
 *
 * An absent factor is shown and greyed rather than dropped, because "not recorded" is a
 * different statement from "scored zero" and the divisor is the proof: an unknown leaves BOTH
 * sums, so it can never drag a score down.
 */
export function BoardRankPopover({
  contribution,
  /** What the cell says about its own ranking, when the policy separated nothing (13.5). */
  note,
}: {
  contribution: BoardContribution;
  note?: string | null;
}) {
  const factors = contribution.rank_factors ?? [];
  const present = factors.filter((factor) => factor.present && factor.value !== null);
  const weightSum = present.reduce((total, factor) => total + factor.weight, 0);
  const weightedSum = present.reduce(
    (total, factor) => total + factor.weight * (factor.value ?? 0),
    0,
  );

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="How this rank was calculated"
          data-testid={`rank-info-${contribution.key}`}
          className="inline-flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={(event) => event.stopPropagation()}
        >
          <Info className="size-3.5" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          align="end"
          // Never wider than the phone it is read on: at 375px a fixed 420 ran the Weighted
          // column off the screen, which is the column the total is made of.
          className="w-[420px] max-w-[92vw] p-0"
          // The popover is portalled to the document root so the dialog's scrolling body
          // cannot clip it - and that puts it OUTSIDE the dialog's focus scope, so letting it
          // take focus on open reads to the dialog as focus leaving and CLOSES the dialog
          // under the reader. Measured in the browser: the first press on this icon shut the
          // breakdown. The content is read, not typed into, so it does not need the focus.
          onOpenAutoFocus={(event) => event.preventDefault()}
        >
          <div
            data-testid={`rank-calculation-${contribution.key}`}
            className="max-h-[60vh] overflow-y-auto"
          >
            <div className="border-b px-3 py-2 text-xs font-semibold">
              How this rank was calculated
            </div>
            {note && (
              <p className="border-b px-3 py-2 text-xs text-muted-foreground">{note}</p>
            )}
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-2xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-1.5 text-start font-medium">Factor</th>
                  <th className="px-2 py-1.5 text-start font-medium">Fact</th>
                  <th className="px-2 py-1.5 text-end font-medium">Score</th>
                  <th className="px-2 py-1.5 text-end font-medium">Weight</th>
                  <th className="px-3 py-1.5 text-end font-medium">Weighted</th>
                </tr>
              </thead>
              <tbody>
                {factors.map((factor) => {
                  const scored = factor.present && factor.value !== null;
                  return (
                    <tr
                      key={factor.key}
                      data-testid={`rank-factor-${factor.key}`}
                      className={`border-b last:border-b-0 ${
                        scored ? '' : 'text-muted-foreground'
                      }`}
                    >
                      <td className="px-3 py-1.5">{factorLabel(factor.key)}</td>
                      <td className="px-2 py-1.5">{factor.raw ?? '-'}</td>
                      <td className="px-2 py-1.5 text-end tabular-nums">
                        {scored ? (factor.value as number).toFixed(2) : 'not recorded'}
                      </td>
                      <td className="px-2 py-1.5 text-end tabular-nums">{num(factor.weight)}</td>
                      <td className="px-3 py-1.5 text-end tabular-nums">
                        {scored ? (factor.weight * (factor.value as number)).toFixed(2) : '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t font-medium">
                  <td className="px-3 py-1.5" colSpan={3}>
                    Total
                  </td>
                  <td className="px-2 py-1.5 text-end tabular-nums">{num(weightSum)}</td>
                  <td className="px-3 py-1.5 text-end tabular-nums">{weightedSum.toFixed(2)}</td>
                </tr>
              </tfoot>
            </table>
            <div className="border-t px-3 py-2">
              <div className="flex items-baseline justify-between gap-3 text-xs font-medium">
                <span>Rank</span>
                <span
                  data-testid={`rank-total-${contribution.key}`}
                  className="tabular-nums"
                >
                  {weightSum > 0
                    ? `${weightedSum.toFixed(2)} / ${num(weightSum)} = ${(
                        weightedSum / weightSum
                      ).toFixed(2)}`
                    : 'no weighted fact was recorded'}
                </span>
              </div>
              <p className="mt-1 text-2xs text-muted-foreground">
                Score 1.00 = best in this cell; absent facts are left out, not counted as zero
              </p>
            </div>
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/** A weight as it was written: `3`, not `3.00`, and `0.5`, not `0.50`. */
function num(value: number): string {
  return String(Number(value.toFixed(4)));
}

export default BoardRankPopover;
