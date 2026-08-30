'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { COLOURS, LABELS } from '../../_shared/lib/supplyVocabulary';
import type { SupplyKind } from '../../_shared/lib/supplyVocabulary';
import { SupplyKindCard } from '../../_shared/components/SupplyKindCard';
import {
  decisionStripTotals,
  rejectedLineCount,
} from '../../_shared/lib/decisionStrip';
import { toMinor } from '../../_shared/lib/supplyComposition';
import type {
  BoardContribution,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

/**
 * Suggested vs decided, per kind of supply, across the whole selection (AC-D2).
 *
 * THE WALK, LEFT TO RIGHT: `own`, `incoming`, `borrow_order`, `borrow_incoming`, `shared`,
 * `buy` - ladder v7.1's own order of consideration, off `ORDER` (the captain, 30 Aug 2026:
 * left = first consideration, right = last option). The strip used to read own, pool, borrow,
 * borrow, buy, which offered the shared pool before anybody's own order and hid two of the
 * walk's steps inside their neighbours.
 *
 * Six or seven cards in that one fixed order, each carrying two figures. Numbers only: what a
 * card means is its label and its colour, both of which the legend directly above already
 * states, and a sentence under a card would be a feature explanation in the UI.
 *
 * A card whose two figures disagree carries the amber dot the board already uses for "this
 * moved". Pressing a card filters BOTH views to the lines carrying that kind on either side,
 * so "who bought what the pool could have covered" is two clicks rather than a scan.
 *
 * A card reading 0 and 0 is DISABLED rather than hidden: nothing on this board is that kind
 * of supply, so there is nothing to filter to, and a press that produced an empty board would
 * read as a broken filter. It keeps its place, because a card that came and went would move
 * every card beside it and the strip is read by glancing at a position.
 *
 * EXCEPT `borrow_other`, which is HIDDEN at 0 and 0. The other six are steps of the walk:
 * every one of them was asked about every line, so a zero there is an answer, and that
 * includes `borrow_incoming`, which reads 0 until S4 lands its candidates - a step nobody can
 * see is a step nobody knows was asked. `borrow_other` is not a step: ladder v7.1 retired
 * `cross_group_borrow` (another group's FREE stock is step 1's second half now and owes nobody
 * anything), so nothing composed today is that kind and the card only stands for what a
 * decision frozen under an older ladder carries. On a board with none it is a card about
 * nothing, and the grid narrows from seven columns to six so the six that remain fill the row.
 *
 * The rule this replaces hid `incoming` instead, on the reading that it was history. Under
 * v7.1 it is step 1's water half and one of the walk's live steps.
 */
export function DecisionStrip({
  contributions,
  draft,
  active,
  onToggle,
}: {
  contributions: BoardContribution[];
  draft: BoardDraft;
  /** The kind currently filtering the grid, or null. */
  active: SupplyKind | null;
  onToggle: (kind: SupplyKind) => void;
}) {
  const totals = React.useMemo(
    () =>
      decisionStripTotals(contributions, draft).filter(
        (total) =>
          total.kind !== 'borrow_other' ||
          toMinor(total.suggested) !== 0 ||
          toMinor(total.decided) !== 0,
      ),
    [contributions, draft],
  );
  // Purchasing refused these lines and they are back with CS (AC-RB2). Beside the cards
  // rather than on one, because a refusal is not a kind of supply - it is a line with no
  // supply decided at all.
  const rejected = React.useMemo(
    () => rejectedLineCount(contributions),
    [contributions],
  );

  return (
    <div data-testid="decision-strip" className="space-y-2">
      <div
        className={cn(
          // Seven cards do not fit a laptop row at `lg`, so the walk wraps to two rows of
          // four there and straightens out at `xl` (1280, the width this board is read at).
          'grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4',
          totals.length > 6 ? 'xl:grid-cols-7' : 'xl:grid-cols-6',
        )}
      >
        {totals.map((total) => {
          const selected = active === total.kind;
          // Nothing on this board is that kind of supply, so there is nothing to filter to.
          const empty =
            toMinor(total.suggested) === 0 && toMinor(total.decided) === 0;
          return (
            <SupplyKindCard
              key={total.kind}
              kind={total.kind}
              label={LABELS[total.kind]}
              swatchClass={COLOURS[total.kind].bar}
              selected={selected}
              disabled={empty}
              onClick={() => onToggle(total.kind)}
              testId={`decision-strip-${total.kind}`}
              // The two figures moved apart. The same amber the grid marks a change with,
              // and no word beside it: the pair of numbers under it is the explanation.
              mark={
                total.changed ? (
                  <span
                    data-testid={`decision-strip-changed-${total.kind}`}
                    aria-label="Suggested and decided differ"
                    className="size-1.5 shrink-0 rounded-full bg-amber-500"
                  />
                ) : null
              }
            >
              <span className="mt-1.5 flex items-baseline justify-between gap-2">
                <span className="text-[11px] text-muted-foreground">
                  Suggested
                </span>
                <span className="text-sm font-semibold tabular-nums">
                  {total.suggested}
                </span>
              </span>
              <span className="flex items-baseline justify-between gap-2">
                <span className="text-[11px] text-muted-foreground">
                  Decided
                </span>
                <span
                  className={cn(
                    'text-sm font-semibold tabular-nums',
                    COLOURS[total.kind].text,
                  )}
                >
                  {total.decided}
                </span>
              </span>
            </SupplyKindCard>
          );
        })}
      </div>
      {rejected > 0 ? (
        <span
          data-testid="decision-strip-rejected"
          className="inline-flex rounded bg-destructive/10 px-1.5 py-0.5 text-[11px] font-medium text-destructive"
        >
          {`${rejected} rejected`}
        </span>
      ) : null}
    </div>
  );
}
