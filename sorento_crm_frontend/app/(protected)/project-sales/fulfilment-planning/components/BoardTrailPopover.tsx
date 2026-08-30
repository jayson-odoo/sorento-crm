'use client';

import * as React from 'react';
import { ListChecks } from 'lucide-react';
import {
  Popover,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
import { formatDateInMalaysia } from '@/lib/helpers';
import { statusPillClass } from '@/lib/status-pill';
import type {
  BoardContribution,
  BoardTrailPool,
  BoardTrailStep,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BoardLadderOptionsTable } from './BoardLadderOptionsTable';
import { ClassificationProofPopover } from './ClassificationProofPopover';
import { PileQueueDialog } from './PileQueueDialog';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

/**
 * How this line's proposal was arrived at: the four questions, and Buy.
 *
 * The captain, on a Buy: "can you justify how you arrive at the buy, like what's the process
 * you have gone through" - and then, on being shown a paragraph: "the justification needs to be
 * STRUCTURED instead of plain text explaining, you can put it under the tooltip". And on 26
 * August, walking SO381895: "our thought process is simpler now."
 *
 * So it is FIVE ROWS, always, one per question plus Buy, and every one is answered: "the pool
 * was checked and had none" is the answer to that question, and a row left out reads as a
 * question nobody asked. Each row is a QUESTION, a Yes or No, what it took, where from, and
 * one sentence with the deciding figure inside it - the group's net, the pile's net, the donor
 * group's net, the cap. The eight columns of arithmetic this replaced left the reader to do
 * the subtraction themselves.
 *
 * The engine's rung names (own, pool, cross_group_borrow, group_borrow, buy) stay internal and
 * are never rendered.
 *
 * A real `<table>` and not the shared DataGrid on purpose: five fixed rows inside a popover,
 * with no sorting, paging or column preferences to speak of.
 */
export function BoardTrailPopover({
  contribution,
}: {
  contribution: BoardContribution;
}) {
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
            {/* Scrolls in BOTH directions: at 375px the row is wider than the phone, and
                clipping it silently drops Took and From. */}
            <div
              data-testid={`trail-${contribution.key}`}
              className="max-h-[60vh] overflow-auto"
            >
              <div className="flex flex-wrap items-center gap-1.5 border-b px-3 py-2 text-xs font-semibold">
                <span>How this decision was reached</span>
                <ItemFlagChips contribution={contribution} />
              </div>
              {trail.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">
                  {trailAbsence(contribution)}
                </p>
              ) : (
                <table className="w-full min-w-[520px] text-xs">
                  <thead>
                    <tr className="border-b text-2xs uppercase tracking-wide text-muted-foreground">
                      <th className="px-3 py-1.5 text-start font-medium">#</th>
                      <th className="px-2 py-1.5 text-start font-medium">
                        Question
                      </th>
                      <th className="px-2 py-1.5 text-start font-medium">
                        Answer
                      </th>
                      <th className="px-2 py-1.5 text-end font-medium">Took</th>
                      <th className="px-3 py-1.5 text-start font-medium">
                        From
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {trail.map((step) => (
                      <React.Fragment key={step.step}>
                        <tr
                          data-step={step.step}
                          data-testid={`trail-step-${contribution.key}-${step.kind}`}
                          className={
                            hasFooter(step) ? '' : 'border-b last:border-b-0'
                          }
                        >
                          <td className="px-3 py-1.5 tabular-nums">
                            {step.step}
                          </td>
                          <td className="px-2 py-1.5">
                            <span className="block" title={step.question}>
                              {step.question}
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            <span
                              data-testid={`trail-answer-${contribution.key}-${step.kind}`}
                              className={`inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium ${
                                ANSWER_CLASS[step.answer] ??
                                'bg-muted text-muted-foreground'
                              }`}
                            >
                              {ANSWER_LABEL[step.answer] ?? step.answer}
                            </span>
                          </td>
                          <td className="px-2 py-1.5 text-end font-medium tabular-nums">
                            {step.took}
                          </td>
                          <td
                            className="max-w-[160px] truncate px-3 py-1.5"
                            title={step.from ?? undefined}
                          >
                            {step.from ?? '-'}
                          </td>
                        </tr>
                        {hasFooter(step) && (
                          <tr className="border-b last:border-b-0">
                            <td />
                            <td colSpan={4} className="space-y-1 px-2 pb-1.5">
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
                                <p className="text-2xs text-muted-foreground">
                                  {step.note}
                                </p>
                              )}
                              {step.kind === 'pool' && step.pool && (
                                <PoolPile
                                  pool={step.pool}
                                  contributionKey={contribution.key}
                                />
                              )}
                              {(step.ahead?.length ?? 0) > 0 && (
                                <QueueLink
                                  step={step}
                                  contributionKey={contribution.key}
                                  onOpenQueue={
                                    contribution.product_id &&
                                    contribution.fulfilment_warehouse_id
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
              {/* AND WHAT ELSE COULD HAVE BEEN DONE (R36, AC-S3-14). Beneath the questions,
                  because it is the answer to the one they raise: five rungs were checked, and
                  this is when each of them would have landed the unit. Rendered only when the
                  server states options - a snapshot frozen before they existed has none, and
                  an empty table would read as "no option covers this line". */}
              {(contribution.options?.length ?? 0) > 0 && (
                <div className="border-t">
                  <p className="px-3 pb-1 pt-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Options
                  </p>
                  <BoardLadderOptionsTable
                    options={contribution.options ?? []}
                    contributionKey={contribution.key}
                  />
                </div>
              )}
            </div>
          </PopoverContent>
        </PopoverPortal>
      </Popover>
      {queueOpen &&
        contribution.product_id &&
        contribution.fulfilment_warehouse_id && (
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

/** A rung says something under itself when it has a sentence, a hint, a pile or a queue to name. */
function hasFooter(step: BoardTrailStep): boolean {
  return Boolean(
    step.why || step.note || step.pool || (step.ahead?.length ?? 0) > 0,
  );
}

/**
 * The item facts the ladder judged this line on, as chips beside the title.
 *
 * The captain: "where is the consideration of dealer hot selling / project hot selling /
 * discontinued, to see if we can take from BRW?" They were consulted on every line and never
 * printed. Nothing renders when the flags are absent (the ladder was not walked) or all clear -
 * an unflagged item is the ordinary case and needs no badge saying so.
 *
 * Amended 19 August 2026 (PLAN 3.3a): both a dealer and a project hot-selling chip may show
 * (dealer wins the pool, but both are stated - the flags are evidence, not a single verdict).
 * Own-location stock is never restricted by either flag any more; only the shared pool is.
 *
 * Amended again the same day: the captain, reading the trail, asked for plain words instead
 * of "abc classification" jargon, so a chip now reads "Cold at retail" / "Cold at project"
 * for a classified-but-not-hot class (at most the two class chips, never both a hot and a
 * cold chip for the same class), and "Not classified" when the item has no evidence at all.
 * The Proof button beside the chips is where the ranked number behind any of these lives.
 */
export function ItemFlagChips({
  contribution,
  idKey = contribution.key,
}: {
  contribution: BoardContribution;
  /** Test-id key. The cell dialog's header renders the same chips under its own key. */
  idKey?: string;
}) {
  const flags = contribution.item_flags;
  if (!flags) return null;
  const chips: Array<{
    key: string;
    label: string;
    title: string;
    tone: string;
  }> = [];
  if (flags.dealer_hot_selling) {
    const where = flags.dealer_hot_selling_where.join(', ');
    chips.push({
      key: 'dealer-hot-selling',
      label: 'Dealer hot-selling',
      title: where
        ? `Dealer hot-selling at ${where}. The shared pool is kept for retail, not offered.`
        : 'Dealer hot-selling. The shared pool is kept for retail, not offered.',
      tone: 'pending',
    });
  } else if (flags.dealer_classified) {
    chips.push({
      key: 'dealer-cold',
      label: 'Cold at retail',
      title:
        'Cold at retail: the shared pool is offered as it is for any ordinary item.',
      tone: 'draft',
    });
  }
  if (flags.project_hot_selling) {
    const where = flags.project_hot_selling_where.join(', ');
    chips.push({
      key: 'project-hot-selling',
      label: 'Project hot-selling',
      title: where
        ? `Project hot-selling at ${where}. The shared pool may be drawn while its availability stays positive.`
        : 'Project hot-selling. The shared pool may be drawn while its availability stays positive.',
      tone: 'pending',
    });
  } else if (flags.project_classified) {
    chips.push({
      key: 'project-cold',
      label: 'Cold at project',
      title:
        'Cold at project: the shared pool is offered as it is for any ordinary item.',
      tone: 'draft',
    });
  }
  if (flags.discontinued) {
    chips.push({
      key: 'discontinued',
      label: 'Discontinued',
      title: 'Discontinued: a Buy for it needs a reason.',
      tone: 'pending',
    });
  }
  if (!flags.retail_classification_available) {
    chips.push({
      key: 'not-classified',
      label: 'Not classified',
      title:
        'No retail or project deliveries of this item in the last 12 months, so hot-selling cannot be judged.',
      tone: 'unknown',
    });
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {chips.length > 0 && (
        <span
          data-testid={`trail-flags-${idKey}`}
          className="inline-flex flex-wrap gap-1"
        >
          {chips.map((chip) => (
            <span
              key={chip.key}
              data-testid={`trail-flag-${idKey}-${chip.key}`}
              title={chip.title}
              className={`inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium ${statusPillClass(chip.tone)}`}
            >
              {chip.label}
            </span>
          ))}
        </span>
      )}
      <ClassificationProofPopover
        productId={contribution.product_id}
        testId={idKey}
      />
    </span>
  );
}

/**
 * The pool's pile under rung 2, in AutoCount's vocabulary.
 *
 * The captain, on `Pool BRW | Had 0` beside an Inventory screen showing `Available 1`: "why it
 * shows 0?" `Had` is what the pool's own queue ahead of this line left; Available is the pile's
 * whole position. Both are here, with the subtraction between them, so the rung can be checked
 * against the stock screen. Seven fixed cells of arithmetic, so a plain table.
 */
function PoolPile({
  pool,
  contributionKey,
}: {
  pool: BoardTrailPool;
  contributionKey: string;
}) {
  const cells: Array<{ label: string; value: string; title?: string }> = [
    { label: 'On hand', value: pool.on_hand },
    {
      label: 'SO qty',
      value: pool.so_qty,
      title: 'Outstanding on every open sales order at this location',
    },
    {
      label: 'SPO qty',
      value: pool.spo_qty,
      title: 'On the water to this location',
    },
    {
      label: 'Available',
      value: pool.available,
      title: 'On hand - SO qty + SPO qty',
    },
    {
      label: 'Free',
      value: pool.free,
      title: 'On hand less reserved less confirmed holds',
    },
    {
      label: 'Claimed ahead',
      value: `${pool.claimed_ahead_qty} (${pool.claimed_ahead_lines} line${
        pool.claimed_ahead_lines === 1 ? '' : 's'
      })`,
      title: "By this location's own orders ranked ahead of this line",
    },
    {
      label: 'Left',
      value: pool.left,
      title: 'For this line, when the rung was reached',
    },
  ];
  return (
    <ScrollArea>
      <table
        data-testid={`trail-pool-${contributionKey}`}
        className="mt-0.5 text-2xs tabular-nums"
      >
        <thead>
          <tr className="text-muted-foreground">
            {cells.map((cell) => (
              <th
                key={cell.label}
                scope="col"
                title={cell.title}
                className="pe-3 text-end font-medium uppercase tracking-wide"
              >
                {cell.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {cells.map((cell) => (
              <td
                key={cell.label}
                data-testid={`trail-pool-${contributionKey}-${cell.label.toLowerCase().replace(/\s+/g, '-')}`}
                className="pe-3 text-end"
              >
                {cell.value}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
}

/**
 * The route to the whole queue - nothing else.
 *
 * This used to also name the top three lines ahead and count the rest by factor, but the
 * captain: "the explanation ... Ahead of this line ... is not needed, cause you already told me
 * how many lines ahead, that's fine" - the rung's own sentence already gives the count and the
 * reason. What is left is the one thing the sentence cannot be: a press away, because the
 * follow-up was "I need to know what is ahead of me to have the visibility, and why they are
 * ahead of me, meaning I need to know their rank also".
 */
function QueueLink({
  step,
  contributionKey,
  onOpenQueue,
}: {
  step: BoardTrailStep;
  contributionKey: string;
  /** Absent when the line's order states no location: there is no pile, so there is no queue. */
  onOpenQueue?: () => void;
}) {
  if (!onOpenQueue) return null;
  const ahead = step.ahead ?? [];
  return (
    <div className="pt-0.5">
      <button
        type="button"
        data-testid={`trail-queue-${contributionKey}`}
        className="text-2xs font-medium text-primary hover:underline"
        onClick={onOpenQueue}
      >
        {`View the queue (${step.ahead_lines ?? ahead.length} ahead)`}
      </button>
    </div>
  );
}

const ANSWER_LABEL: Record<string, string> = {
  yes: 'Yes',
  no: 'No',
};

const ANSWER_CLASS: Record<string, string> = {
  yes: 'bg-emerald-100 text-emerald-800',
  no: 'bg-muted text-muted-foreground',
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
  const stated = contribution.sources.find(
    (source) => source.kind === 'unplannable',
  );
  return (
    stated?.reason ??
    'No fulfilment location on the sales order line, so nothing can be sourced for it.'
  );
}

export default BoardTrailPopover;
