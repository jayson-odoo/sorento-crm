/**
 * The proposal review, built once and consumed twice by design: extraction from
 * pasted text on the product record today, and milestone 2's supplier acceptance,
 * which sits in the `(auth)` route group and could not import a component that lived
 * under `(protected)`.
 */
export { SpecProposalReview, proposalBadgeText } from './SpecProposalReview';
export type {
  SpecProposal,
  SpecProposalKind,
  SpecProposalReviewProps,
  SpecProposalScalar,
  SpecProposalValue,
} from './types';
