'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import type { PlanningChangeReaction } from '../types/planningChange.types';

/**
 * The suggested reaction, as the verb the planner already knows from the board (PLAN section
 * 0's rule table). Its own small file - and not folded into the batch page - so the list page's
 * `Pending` column can wear the same pill without a second palette drifting from it.
 */
const REACTION_LABEL: Record<PlanningChangeReaction, string> = {
  keep: 'Keep',
  release: 'Release',
  replan: 'Replan',
  reduce: 'Reduce',
  retire: 'Retire',
};

/**
 * Colour follows what the verb DOES to the plan, reusing the existing palette rather than
 * inventing one: a hold that stands is the same affirmative blue as an approval, a hold given
 * back is the amber of something waiting, a line that runs the ladder again is the sky of a
 * change in flight, a reduction is the amber-toned review colour, and a line dropped from the
 * plan is the red a rejection wears.
 */
const PALETTE_KEY: Record<PlanningChangeReaction, string> = {
  keep: 'approved',
  release: 'pending',
  replan: 'submitted',
  reduce: 'in_review',
  retire: 'rejected',
};

export function ReactionPill({ reaction }: { reaction: PlanningChangeReaction }) {
  return (
    <span
      className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(PALETTE_KEY[reaction])}`}
      title={REACTION_LABEL[reaction]}
    >
      {REACTION_LABEL[reaction]}
    </span>
  );
}

export default ReactionPill;
