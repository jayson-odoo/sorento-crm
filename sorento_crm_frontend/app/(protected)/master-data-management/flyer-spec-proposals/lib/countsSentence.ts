import type { FlyerSpecBatch } from '../services/flyerSpecProposalService';

/**
 * What a finished pass found, in one sentence.
 *
 * Written once and read on both surfaces - the section on the dealer kit's
 * reading page and the header of the review screen - because they are the same
 * claim about the same batch, and two copies of it would disagree the first time
 * either was edited.
 *
 * Every kind is named, including the two that ask nothing of the reader. A
 * sentence that reported only the actionable ones would say "3 values" over a
 * batch of forty, which reads as a flyer the system barely understood.
 *
 * The product count carries "(M via a family card)" when a sibling picked up
 * its reading from another product's card rather than its own
 * (PLAN-flyer-family-proposals.md, AC-B.2) - never a second line, so the two
 * surfaces that render this sentence cannot show one without the other.
 */
export function proposalCountsSentence(batch: FlyerSpecBatch): string {
  const values = `${batch.proposal_count} specification value${batch.proposal_count === 1 ? '' : 's'}`;
  const products = `${batch.product_count} product${batch.product_count === 1 ? '' : 's'}${
    batch.viaCount > 0 ? ` (${batch.viaCount} via a family card)` : ''
  }`;
  const parts = [
    `${batch.new_count} new`,
    `${batch.change_count} change what the master says`,
    `${batch.conflict_count} conflict with a value a person set`,
    `${batch.unchanged_count} unchanged`,
    `${batch.suppressed_count} suppressed`,
  ];
  return `This flyer states ${values} across ${products}: ${parts.join(', ')}.`;
}
