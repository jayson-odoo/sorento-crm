'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { COLOURS, LABELS } from '../../_shared/lib/supplyVocabulary';
import type { SupplyKind } from '../../_shared/lib/supplyVocabulary';
import { decisionStripTotals } from '../../_shared/lib/decisionStrip';
import { toMinor } from '../../_shared/lib/supplyComposition';
import type { BoardContribution, BoardDraft } from '../../_shared/types/fulfilmentPlanning.types';

/**
 * Suggested vs decided, per kind of supply, across the whole selection (AC-D2).
 *
 * Six cards in one fixed order (`ORDER`), each carrying two figures. Numbers only: what a card
 * means is its label and its colour, both of which the legend directly above already states,
 * and a sentence under a card would be a feature explanation in the UI.
 *
 * A card whose two figures disagree carries the amber dot the board already uses for "this
 * moved". Pressing a card filters BOTH views to the lines carrying that kind on either side,
 * so "who bought what the pool could have covered" is two clicks rather than a scan.
 *
 * A card reading 0 and 0 is DISABLED rather than hidden: nothing on this board is that kind
 * of supply, so there is nothing to filter to, and a press that produced an empty board would
 * read as a broken filter. It keeps its place, because a card that came and went would move
 * every card beside it and the strip is read by glancing at a position.
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
    () => decisionStripTotals(contributions, draft),
    [contributions, draft],
  );

  return (
    <div
      data-testid="decision-strip"
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6"
    >
      {totals.map((total) => {
        const selected = active === total.kind;
        // Nothing on this board is that kind of supply, so there is nothing to filter to.
        const empty = toMinor(total.suggested) === 0 && toMinor(total.decided) === 0;
        return (
          <button
            key={total.kind}
            type="button"
            data-testid={`decision-strip-${total.kind}`}
            aria-pressed={selected}
            disabled={empty}
            onClick={() => onToggle(total.kind)}
            className={cn(
              'rounded-lg border p-2.5 text-start transition-colors',
              empty ? 'opacity-60' : 'hover:bg-accent',
              selected ? 'border-primary bg-accent' : 'border-border',
            )}
          >
            <span className="flex items-center gap-1.5">
              <span
                data-kind={total.kind}
                aria-hidden
                className={cn('size-2.5 shrink-0 rounded-sm', COLOURS[total.kind].bar)}
              />
              <span className="min-w-0 truncate text-xs font-medium" title={LABELS[total.kind]}>
                {LABELS[total.kind]}
              </span>
              {/* The two figures moved apart. The same amber the grid marks a change with,
                  and no word beside it: the pair of numbers under it is the explanation. */}
              {total.changed ? (
                <span
                  data-testid={`decision-strip-changed-${total.kind}`}
                  aria-label="Suggested and decided differ"
                  className="size-1.5 shrink-0 rounded-full bg-amber-500"
                />
              ) : null}
            </span>
            <span className="mt-1.5 flex items-baseline justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">Suggested</span>
              <span className="text-sm font-semibold tabular-nums">{total.suggested}</span>
            </span>
            <span className="flex items-baseline justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">Decided</span>
              <span
                className={cn('text-sm font-semibold tabular-nums', COLOURS[total.kind].text)}
              >
                {total.decided}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
