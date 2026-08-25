'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { COLOURS, LABELS } from '../../_shared/lib/supplyVocabulary';
import type { SupplyKind } from '../../_shared/lib/supplyVocabulary';
import { decisionStripTotals } from '../../_shared/lib/decisionStrip';
import type { BoardContribution, BoardDraft } from '../../_shared/types/fulfilmentPlanning.types';

/**
 * Suggested vs decided, per kind of supply, across the whole selection (AC-D2).
 *
 * Five cards in one fixed order, each carrying two figures. Numbers only: what a card means
 * is its label and its colour, both of which the legend directly above already states, and a
 * sentence under a card would be a feature explanation in the UI.
 *
 * A card whose two figures disagree carries the amber dot the board already uses for "this
 * moved". Pressing a card filters the grid to the cells carrying that kind on either side, so
 * "who bought what the pool could have covered" is two clicks rather than a scan.
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
        return (
          <button
            key={total.kind}
            type="button"
            data-testid={`decision-strip-${total.kind}`}
            aria-pressed={selected}
            onClick={() => onToggle(total.kind)}
            className={cn(
              'rounded-lg border p-2.5 text-start transition-colors hover:bg-accent',
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
