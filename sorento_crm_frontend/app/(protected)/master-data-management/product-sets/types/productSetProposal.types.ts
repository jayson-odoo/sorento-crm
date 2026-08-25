/**
 * Seeding product sets: what the catalogue proposes, and what a person accepts.
 *
 * 47 two-piece families exist across Sorento and Mocha, and 23 of them have no
 * bare code at all. Typing ~94 sets by hand is the work this screen removes, but
 * the pass never writes: it derives candidates from the code shape and a person
 * ticks the ones that are right. The role labels in this feature's own design
 * came out inverted at the start, which is the argument against a regex that
 * writes by itself.
 *
 * UAC group H: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
 */

/** One SKU the pass believes belongs in the set. Addressed by code; no UUID reaches the UI. */
export interface ProductSetProposalMember {
  product_code: string;
  description: string | null;
  /** Live, read at propose time from the catalogue - never a stored snapshot. */
  list_price: number | null;
  quantity: number;
  /**
   * The price basis. Sorento parks the whole assembly's list price on one member
   * - the pedestal reads 1180.00 while the cistern reads 0.00 - so the pass ticks
   * the anchor and leaves the rest untouched.
   */
  contributes_to_price: boolean;
  sort_order: number;
  is_discontinued: boolean;
}

/** One candidate set. Never written until somebody ticks it. */
export interface ProductSetProposal {
  id: string;
  /**
   * The prefix and number the members share, e.g. `SRTWC8608`. Two candidates
   * with the same family are the same assembly in different trap variants, so
   * the review screen shows them together.
   */
  family_key: string;
  /** The code the flyer prints: the anchor's code with its role letter removed. */
  set_code: string;
  name: string;
  members: ProductSetProposalMember[];
  /** Sum over the ticked members. Null - never 0.00 - when nothing is ticked. */
  computed_price: number | null;
}

export interface ProductSetProposalBatch {
  id: string;
  company_name: string | null;
  created_at: string;
  created_by_name: string | null;
  family_count: number;
  proposal_count: number;
  proposals: ProductSetProposal[];
}

/** What one apply did. A refusal names the set code, because that is what the reviewer ticked. */
export interface ApplyProposalsResult {
  applied: { proposal_id: string; set_code: string }[];
  refused: { proposal_id: string; set_code: string; reason: string }[];
}
