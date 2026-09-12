'use client';

import { StatCard } from '@/components/scm/StatCard';
import { fmtInt, fmtTrimmedDecimal } from '../../lib/format';
import { describeWindow } from '../../reorder/lib/runListing';
import type { ContainerRequestSummary } from './containerRequestSummary';

/**
 * The five figures above the grid (PLAN section 2b, AC-A2.1) - the same cards the fulfilment
 * board opens with, reading the loading plan's own vocabulary.
 *
 * They carry the colour swatches, which is why there is no separate legend (r4): on hand
 * emerald, SPO violet, the ask rose, exactly as the board paints those three kinds.
 */
export function ContainerRequestStatCards({
  summary,
  planHorizonStart,
  planHorizonDate,
}: {
  summary: ContainerRequestSummary;
  /** "Sales orders needed" window (AC-N7), as applied by the build - both read through
   *  `describeWindow`, the same call the heading above this grid makes, so the two cannot
   *  say different things about what the build was worked out against. */
  planHorizonStart: string | null;
  planHorizonDate: string | null;
}) {
  const window = describeWindow(planHorizonStart, planHorizonDate);
  return (
    <div
      data-testid="container-request-stat-cards"
      // Two per row at phone width rather than five stacked cards: stacked, the grid they
      // summarise starts a screen and a half down the page.
      className="grid grid-cols-2 gap-3 sm:grid-cols-4"
    >
      <StatCard
        testId="stat-need"
        label="Outstanding"
        value={fmtInt(summary.need)}
        sub={window === 'every open order' ? undefined : window}
      />
      <StatCard
        testId="stat-on-hand"
        label="On hand"
        value={fmtInt(summary.fromOnHand)}
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
    </div>
  );
}

export default ContainerRequestStatCards;
