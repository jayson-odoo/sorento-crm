'use client';

import * as React from 'react';
import { Check } from 'lucide-react';
import type { BoardContribution } from '../../_shared/types/fulfilmentPlanning.types';

/**
 * "This is already decided", small enough to be scanned rather than read.
 *
 * The grid and the list answer the same question two ways, so they carry the SAME marker:
 * a planner who has learnt the tick on one has learnt it on the other. It says which
 * revision decided it in its `title`, because the number is what the sales-order screen and
 * the confirmation dialog both quote - but the number is not printed on the face of a cell
 * that already carries a quantity, a source strip and up to three badges.
 *
 * A marker is shown ONLY when EVERY contribution it covers is decided. A cell where four of
 * eleven lines are confirmed is not a decided cell, and ticking it would be the screen
 * saying so.
 */
export function BoardDecidedMarker({ revisions }: { revisions: number[] }) {
  if (revisions.length === 0) return null;
  // One revision reads "Decided rev 3". A cell spanning several sales orders legitimately
  // holds several, and naming one of them would attribute the decision to the wrong order.
  const unique = Array.from(new Set(revisions)).sort((a, b) => a - b);
  const title = `Decided rev ${unique.join(', ')}`;
  return (
    <span
      data-testid="board-decided-marker"
      title={title}
      aria-label={title}
      className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-800"
    >
      <Check className="size-3" aria-hidden />
    </span>
  );
}

/**
 * The revisions that decided this set of rows, or NOTHING when any row is still open.
 *
 * `covered` is the server's own word for "an active decision holds this line" and the
 * revision travels with it, so this reads the payload rather than re-deriving the state
 * from the draft: a verdict a planner has ticked but not confirmed is not a decision.
 */
export function decidedRevisions(contributions: BoardContribution[]): number[] {
  if (contributions.length === 0) return [];
  const revisions: number[] = [];
  for (const entry of contributions) {
    if (!entry.covered || !entry.decision) return [];
    revisions.push(entry.decision.revision_no);
  }
  return revisions;
}
