import type { ReactNode } from 'react';

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
 *
 * The first three are decisions waiting to be made; the last two are answers
 * already given, and they are here because the flyer batch (AC-D.2) SHOWS them.
 * Pasted-text extraction drops an `unchanged` proposal on the floor and never
 * sends one, which is right for a box somebody just typed into. A flyer batch is
 * read once and applied more than once, so "this flyer says nothing new about
 * this product" and "somebody removed this spec from this product" are the two
 * answers a reviewer most needs to see - and the second apply of the same batch
 * is only evidence of anything if the rows it refused are on screen.
 *
 * `unchanged` and `suppressed` are never selectable: there is nothing to write.
 */
export type SpecProposalKind = 'new' | 'change' | 'conflict' | 'unchanged' | 'suppressed';

/**
 * Which kinds may be ticked when the caller says nothing.
 *
 * Everything that HAS a value to write. `unchanged` and `suppressed` are absent
 * on every surface - the first would write what is already there and the second
 * would overturn a removal - so they are the floor rather than a default.
 *
 * `conflict` is in here because a caller looking at ONE product may overrule the
 * person who set the value: that is the pasted-text panel, where somebody is
 * reading one card against one product and can see exactly what they are
 * replacing. A bulk apply over two hundred products narrows this - see
 * `selectableKinds` below - because nobody read two hundred conflicts.
 */
export const DEFAULT_SELECTABLE_KINDS: readonly SpecProposalKind[] = [
  'new',
  'change',
  'conflict',
];

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
  /**
   * What the product holds now. Null on a `new` proposal, by definition, and on
   * a `suppressed` one - a tombstone is the absence of a value, not a value.
   */
  stored_value: SpecProposalValue | null;
  stored_unit: string | null;
  /** derived | flyer | code | category | human | supplier, or null when unstamped. */
  stored_source: string | null;
  /**
   * The key's vocabulary, when it has a closed one. Carried as DATA so an
   * in-place editor can render its dropdown without a call of its own, and
   * absent (rather than empty) when the key takes free text - "there is no
   * list" and "the list is empty" are different instructions to a widget.
   */
  allowed_values?: string[] | null;
  /** True once a person has corrected this row's value before applying it. */
  edited?: boolean;
}

export interface SpecProposalReviewProps {
  proposals: SpecProposal[];
  /** The ticked keys. Held by the CALLER, so a multi-product review can lift it. */
  selectedKeys: string[];
  onSelectionChange: (keys: string[]) => void;
  /** True while the caller is writing: the rows stay readable, the ticks freeze. */
  disabled?: boolean;
  /**
   * Which kinds this surface may tick. `DEFAULT_SELECTABLE_KINDS` when omitted.
   *
   * A prop rather than a second component, and never a rule this file decides
   * alone. `unchanged` and `suppressed` are refused whatever is passed - there
   * is nothing to write for either.
   */
  selectableKinds?: readonly SpecProposalKind[];
  /**
   * The Value cell, when the surface wants its own.
   *
   * Handed the default cell so the caller can return it unchanged for every row
   * it is not editing, which is what keeps the read rendering in ONE place: an
   * in-place editor is a swap of one row's cell, not a second way of showing a
   * value. This component owns no editing state of its own - the caller holds
   * which row is open, and this stays product-blind and service-free.
   */
  renderValue?: (proposal: SpecProposal, defaultCell: ReactNode) => ReactNode;
  /**
   * A trailing actions column, when the surface has row actions (edit, dismiss).
   *
   * The column exists only when this is given, so the surfaces that have no row
   * actions render exactly the table they rendered before.
   */
  rowActions?: (proposal: SpecProposal) => ReactNode;
}
