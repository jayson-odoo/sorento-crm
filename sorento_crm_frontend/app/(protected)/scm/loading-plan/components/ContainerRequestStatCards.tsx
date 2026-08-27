'use client';

import { StatCard } from '@/components/scm/StatCard';
import { fmtInt, fmtTrimmedDecimal } from '../../lib/format';
import type { ContainerRequestSummary } from './containerRequestSummary';

/**
 * The five figures above the grid (PLAN section 2b, AC-A2.1) - the same cards the fulfilment
 * board opens with, reading the loading plan's own vocabulary.
 *
 * They carry the colour swatches, which is why there is no separate legend (r4): pool stock
 * emerald, SPO violet, the ask rose, exactly as the board paints those three kinds.
 */
export function ContainerRequestStatCards({
  summary,
  horizonDate,
}: {
  summary: ContainerRequestSummary;
  /** "Plan until", as applied by the build - null when there is no cutoff. */
  horizonDate: string | null;
}) {
  return (
    <div
      data-testid="container-request-stat-cards"
      // Two per row at phone width rather than five stacked cards: stacked, the grid they
      // summarise starts a screen and a half down the page.
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5"
    >
      <StatCard
        testId="stat-need"
        label="Outstanding"
        value={fmtInt(summary.need)}
        sub={horizonDate ? `until ${horizonDate}` : undefined}
      />
      <StatCard
        testId="stat-pool"
        label="BRW On Hand"
        value={fmtInt(summary.fromPool)}
        swatch="bg-emerald-500"
        tone="text-emerald-700"
      />
      <StatCard
        testId="stat-spo"
        label="From SPO"
        value={fmtInt(summary.fromSpo)}
        swatch="bg-violet-500"
        tone="text-violet-700"
      />
      <StatCard
        testId="stat-ask"
        label="To request"
        value={fmtInt(summary.toAsk)}
        swatch="bg-rose-500"
        tone="text-rose-700"
        sub={
          summary.askCbmUnmeasured > 0
            ? `est. ${fmtTrimmedDecimal(summary.askCbm)} cbm, ${summary.askCbmUnmeasured} unmeasured`
            : `est. ${fmtTrimmedDecimal(summary.askCbm)} cbm`
        }
      />
      <StatCard
        testId="stat-packed"
        label="They can pack now"
        value={fmtInt(summary.canPackNow)}
      />
    </div>
  );
}

export default ContainerRequestStatCards;
