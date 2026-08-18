'use client';

import * as React from 'react';
import { ListChecks } from 'lucide-react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { formatDateInMalaysia } from '@/lib/helpers';
import { aheadFactorLabel } from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardAheadLine,
  BoardContribution,
  BoardTrailStep,
} from '../../_shared/types/fulfilmentPlanning.types';
import { PileQueueDialog } from './PileQueueDialog';

/**
 * How this line's proposal was arrived at, rung by rung.
 *
 * The captain, on a Buy: "can you justify how you arrive at the buy, like what's the process
 * you have gone through: checking the available quantity first, deciding whether to reserve it
 * or not, then checking the SPO quantity, then checking whether can borrow ... need more
 * justification" - and then, on being shown a paragraph: "the justification needs to be
 * STRUCTURED instead of plain text explaining, you can put it under the tooltip".
 *
 * So it is a table of STEPS in the order the ladder walked them, and every rung is here
 * including the ones that gave nothing: "the pool was checked and had none" is the answer to
 * that question, and a rung left out reads as a rung nobody walked. What each source HELD, who
 * was ahead of this line at it, what it could offer, what the line took, and what was still
 * owed after it - the same numbers the source strip beside it is the summary of.
 *
 * A real `<table>` and not the shared DataGrid on purpose: five fixed rows of arithmetic inside
 * a popover, with no sorting, paging or column preferences to speak of.
 */
export function BoardTrailPopover({ contribution }: { contribution: BoardContribution }) {
  const trail = contribution.trail ?? [];
  /**
   * The whole queue, over the popover.
   *
   * Held HERE rather than inside the rung, and rendered outside the `Popover`, so pressing the
   * button can close the popover without taking the dialog down with it: the queue is the thing
   * the reader asked for, and the three-line summary it was opened from has done its job.
   */
  const [queueOpen, setQueueOpen] = React.useState(false);

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label="How this decision was reached"
            data-testid={`trail-info-${contribution.key}`}
            className="inline-flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={(event) => event.stopPropagation()}
          >
            <ListChecks className="size-3.5" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent
            align="start"
            className="w-[620px] max-w-[92vw] p-0"
            // Portalled out of the dialog's scrolling body so it cannot be clipped, which puts it
            // outside the dialog's focus scope: taking focus on open reads to the dialog as focus
            // leaving and closes it (measured - the first press shut the breakdown). Read-only
            // content, so it does not need the focus.
            onOpenAutoFocus={(event) => event.preventDefault()}
          >
            {/* Scrolls in BOTH directions: at 375px the eight columns are wider than the phone,
                and clipping them silently drops Still owed and Outcome - the two that say how the
                rung ended. */}
            <div data-testid={`trail-${contribution.key}`} className="max-h-[60vh] overflow-auto">
              <div className="border-b px-3 py-2 text-xs font-semibold">
                How this decision was reached
              </div>
              {trail.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">
                  {trailAbsence(contribution)}
                </p>
              ) : (
                <table className="w-full min-w-[560px] text-xs">
                  <thead>
                    <tr className="border-b text-2xs uppercase tracking-wide text-muted-foreground">
                      <th className="px-3 py-1.5 text-start font-medium">#</th>
                      <th className="px-2 py-1.5 text-start font-medium">Source</th>
                      <th className="px-2 py-1.5 text-end font-medium">Had</th>
                      <th className="px-2 py-1.5 text-start font-medium">Ahead</th>
                      <th className="px-2 py-1.5 text-end font-medium">For this line</th>
                      <th className="px-2 py-1.5 text-end font-medium">Took</th>
                      <th className="px-2 py-1.5 text-end font-medium">Still owed</th>
                      <th className="px-3 py-1.5 text-start font-medium">Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trail.map((step) => (
                      <React.Fragment key={step.step}>
                        <tr
                          data-step={step.step}
                          data-testid={`trail-step-${contribution.key}-${step.kind}`}
                          className={hasFooter(step) ? '' : 'border-b last:border-b-0'}
                        >
                          <td className="px-3 py-1.5 tabular-nums">{step.step}</td>
                          <td className="px-2 py-1.5">{sourceOf(step)}</td>
                          <td className="px-2 py-1.5 text-end tabular-nums">
                            {step.opening ?? '-'}
                          </td>
                          <td className="px-2 py-1.5 tabular-nums">{aheadOf(step)}</td>
                          <td className="px-2 py-1.5 text-end tabular-nums">{step.offered}</td>
                          <td className="px-2 py-1.5 text-end font-medium tabular-nums">
                            {step.taken}
                          </td>
                          <td className="px-2 py-1.5 text-end tabular-nums">
                            {step.remaining_after}
                          </td>
                          <td className="px-3 py-1.5">
                            <span
                              className={`inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium ${
                                OUTCOME_CLASS[step.outcome] ?? 'bg-muted text-muted-foreground'
                              }`}
                            >
                              {OUTCOME_LABEL[step.outcome] ?? step.outcome}
                            </span>
                          </td>
                        </tr>
                        {hasFooter(step) && (
                          <tr className="border-b last:border-b-0">
                            <td />
                            <td colSpan={7} className="space-y-1 px-2 pb-1.5">
                              {/* WHY it ended that way, in the server's own words. The row above
                                  is the arithmetic; this is the sentence the captain asked for
                                  when the arithmetic alone left him asking "what does this
                                  mean? why do the orders stand ahead of me? why?" */}
                              {step.why && (
                                <p
                                  data-testid={`trail-why-${contribution.key}-${step.kind}`}
                                  className="text-2xs text-muted-foreground"
                                >
                                  {step.why}
                                </p>
                              )}
                              {step.note && (
                                <p className="text-2xs text-muted-foreground">{step.note}</p>
                              )}
                              {step.kind === 'reserve_own' && (step.ahead?.length ?? 0) > 0 && (
                                <AheadList
                                  step={step}
                                  contributionKey={contribution.key}
                                  onOpenQueue={
                                    contribution.product_id && contribution.fulfilment_warehouse_id
                                      ? () => setQueueOpen(true)
                                      : undefined
                                  }
                                />
                              )}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </PopoverContent>
        </PopoverPortal>
      </Popover>
      {queueOpen && contribution.product_id && contribution.fulfilment_warehouse_id && (
        <PileQueueDialog
          productId={contribution.product_id}
          warehouseId={contribution.fulfilment_warehouse_id}
          lineId={contribution.line_id}
          itemCode={contribution.item_code}
          onClose={() => setQueueOpen(false)}
        />
      )}
    </>
  );
}

/** A rung says something under itself when it has a sentence, a hint or a queue to name. */
function hasFooter(step: BoardTrailStep): boolean {
  return Boolean(step.why || step.note || (step.ahead?.length ?? 0) > 0);
}

/**
 * The top of the queue, named, and the rest of it counted by what put them there.
 *
 * The captain read `18730 across 142 lines` and asked "why do the orders stand ahead of me?
 * why?" - which a total cannot answer. Three lines is what fits beside a rung; the whole queue
 * is a press away, because the follow-up was "I need to know what is ahead of me to have the
 * visibility, and why they are ahead of me, meaning I need to know their rank also".
 */
function AheadList({
  step,
  contributionKey,
  onOpenQueue,
}: {
  step: BoardTrailStep;
  contributionKey: string;
  /** Absent when the line's order states no location: there is no pile, so there is no queue. */
  onOpenQueue?: () => void;
}) {
  const ahead = step.ahead ?? [];
  const more = step.ahead_more ?? 0;
  const byFactor = Object.entries(step.ahead_by_factor ?? {}).sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
  );

  return (
    <div data-testid={`trail-ahead-${contributionKey}`} className="space-y-0.5 pt-0.5">
      <p className="text-2xs font-medium text-muted-foreground">Ahead of this line</p>
      {ahead.map((line, index) => (
        <p
          key={`${line.so_number}-${line.line_no ?? index}`}
          data-testid={`trail-ahead-line-${index}`}
          className="text-2xs text-muted-foreground tabular-nums"
        >
          {aheadLineText(line)}
        </p>
      ))}
      {more > 0 && (
        <p className="text-2xs text-muted-foreground">
          {`and ${more} more (${byFactor
            .map(([key, count]) => `${aheadFactorLabel(key)} ${count}`)
            .join(' · ')})`}
        </p>
      )}
      {onOpenQueue && (
        <button
          type="button"
          data-testid={`trail-queue-${contributionKey}`}
          className="text-2xs font-medium text-primary hover:underline"
          onClick={onOpenQueue}
        >
          {`View the queue (${step.ahead_lines ?? ahead.length} ahead)`}
        </button>
      )}
    </div>
  );
}

/** One queued line on one line: who, how much, when it is due, its rank, and why it is first. */
function aheadLineText(line: BoardAheadLine): string {
  const who = line.same_order
    ? `same order, line ${line.line_no ?? '?'}`
    : `${line.so_number}${line.line_no ? ` L${line.line_no}` : ''}`;
  return [
    who,
    line.qty,
    line.required_date ? `due ${formatDateInMalaysia(line.required_date)}` : 'no required date',
    line.rank_score.toFixed(2),
    line.leading_factor ? aheadFactorLabel(line.leading_factor) : 'ranked first',
  ].join(' · ');
}

/** What the rung is, in the words the source strip already uses. */
function sourceOf(step: BoardTrailStep): string {
  if (step.kind === 'reserve_own') {
    return step.location ? `Reserve at ${step.location}` : 'Reserve';
  }
  if (step.kind === 'reserve_pool') return step.location ? `Pool ${step.location}` : 'Pool';
  if (step.kind === 'incoming') return 'Incoming (SPO)';
  if (step.kind === 'borrow') return 'Borrow';
  return 'Buy';
}

/**
 * Who was in front of this line at its own pile. Only the own location has a queue: the pool
 * nets its own book before it offers anything, and incoming, borrow and buy have none.
 */
function aheadOf(step: BoardTrailStep): string {
  if (step.kind !== 'reserve_own' || !step.ahead_lines) return '-';
  return `${step.ahead_qty ?? '0'} across ${step.ahead_lines} line${
    step.ahead_lines === 1 ? '' : 's'
  }`;
}

const OUTCOME_LABEL: Record<string, string> = {
  took: 'Took',
  nothing_left: 'Nothing left',
  not_eligible: 'Not eligible',
  offered: 'Offered',
  none_needed: 'Not needed',
};

const OUTCOME_CLASS: Record<string, string> = {
  took: 'bg-emerald-100 text-emerald-800',
  nothing_left: 'bg-amber-100 text-amber-800',
  not_eligible: 'bg-muted text-muted-foreground',
  offered: 'bg-sky-100 text-sky-800',
  none_needed: 'bg-muted text-muted-foreground',
};

/**
 * Why there is no ladder, when there is none.
 *
 * Two reasons, and they are opposite: a line an active decision COVERS was not planned again
 * (there is nothing to justify - it was decided, and when is the fact worth having), and a line
 * with no location could not be planned at all.
 */
function trailAbsence(contribution: BoardContribution): string {
  const decision = contribution.covered ? contribution.decision : null;
  if (decision) {
    const when = decision.confirmed_at
      ? ` on ${formatDateInMalaysia(decision.confirmed_at)}`
      : '';
    return `Confirmed in revision ${decision.revision_no}${when}.`;
  }
  return `No plan: ${noPlanReason(contribution)}`;
}

/** Why there is no ladder to show: the server's own sentence, never one invented here. */
function noPlanReason(contribution: BoardContribution): string {
  const stated = contribution.sources.find((source) => source.kind === 'unplannable');
  return (
    stated?.reason ??
    'No fulfilment location on the sales order line, so nothing can be sourced for it.'
  );
}

export default BoardTrailPopover;
