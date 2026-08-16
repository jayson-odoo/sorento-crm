/**
 * The shapes the proposal review is handed, and the shape it hands back.
 *
 * Deliberately free of every backend type in `productSpec.types.ts`, for the same
 * reason `components/spec-table/types.ts` is: this folder is rendered by the product
 * page today and by milestone 2's supplier acceptance screen, which sits in the
 * `(auth)` route group with a different service layer and a different principal. A
 * component that knew `ProductSpecDetail` would drag that whole module in.
 */

/** Everything a proposed value is allowed to be, matching the stored JSON. */
export type SpecProposalScalar = string | number | boolean;

/**
 * One value, or the several a multi-value key holds.
 *
 * A two-tone finish is one proposal carrying a LIST, because that is what derivation
 * stores for the keys it allows more than one of - so accepting the proposal stores
 * exactly what a re-derivation of the same words would. Scalar everywhere else.
 */
export type SpecProposalValue = SpecProposalScalar | SpecProposalScalar[];

/**
 * How a proposal stands against what the product already holds.
 *
 * Computed SERVER-SIDE and carried here as data (AC-B.3), never re-decided in the
 * browser: milestone 2's supplier review reads the same field off a different
 * endpoint, and two copies of the rule would disagree the first time either moved.
 * A proposal equal to the stored value is not a kind at all - it never arrives.
 */
export type SpecProposalKind = 'new' | 'change' | 'conflict';

/** One key the text says something about, judged against what is stored. */
export interface SpecProposal {
  spec_key: string;
  label: string;
  /** The registry's type, for callers that render the value themselves. */
  data_type: string;
  value: SpecProposalValue;
  unit: string | null;
  /** The exact words the value was read from. */
  evidence: string;
  kind: SpecProposalKind;
  /** What the product holds now. Null on a `new` proposal, by definition. */
  stored_value: SpecProposalValue | null;
  stored_unit: string | null;
  /** derived | flyer | code | category | human | supplier, or null when unstamped. */
  stored_source: string | null;
}

export interface SpecProposalReviewProps {
  proposals: SpecProposal[];
  /** The ticked keys. Held by the CALLER, so a multi-product review can lift it. */
  selectedKeys: string[];
  onSelectionChange: (keys: string[]) => void;
  /** True while the caller is writing: the rows stay readable, the ticks freeze. */
  disabled?: boolean;
}
