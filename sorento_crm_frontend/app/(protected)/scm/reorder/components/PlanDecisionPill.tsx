'use client';

import { cn } from '@/lib/utils';
import type { PlanPillReading } from '../lib/planEdits';

/**
 * The Decision column, and nothing else on the collapsed row (plan 4.3, C6).
 *
 * It used to be a control: a loud Accept button carrying the whole mixture, a pencil that
 * opened a three-input popover, and a skip X, all inside a 340px cell. Deciding now happens
 * in the expanded row where the numbers behind the decision are visible, so the cell is back
 * to answering one question - where is this row up to - and the mixture rides beside it so
 * reading down the column still says what was decided, not only that something was.
 *
 * Five states, and each is a different fact: Suggested (nobody has touched it, the engine's
 * mix stands), Unsaved (a draft edit is on it), Saved (persisted), Confirmed (already in a
 * draft purchase order), Skipped (deliberately nothing).
 */
const TONE: Record<PlanPillReading['state'], string> = {
  suggested: 'border-border bg-muted/40 text-muted-foreground',
  unsaved: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  saved: 'border-primary/40 bg-primary/10 text-primary',
  confirmed: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  skipped: 'border-destructive/30 bg-destructive/5 text-destructive',
};

export function PlanDecisionPill({ reading }: { reading: PlanPillReading }) {
  const sameWord = reading.mix === reading.label;
  return (
    <span
      className="flex min-w-0 items-center gap-1.5"
      data-testid={`decision-pill-${reading.state}`}
    >
      <span
        className={cn(
          'inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-2xs font-medium',
          TONE[reading.state],
        )}
      >
        {reading.label}
      </span>
      {/* Skipped says one word, not the same word twice. */}
      {sameWord ? null : (
        <span className="min-w-0 truncate text-xs text-muted-foreground" title={reading.mix}>
          {reading.mix}
        </span>
      )}
    </span>
  );
}
