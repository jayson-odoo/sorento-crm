/**
 * The editable spec table, built once and consumed twice by design: the product
 * record's Specifications tab today, and milestone 2's supplier portal, which sits in
 * the `(auth)` route group and could not import a component that lived under
 * `(protected)`.
 */
export { SpecTable } from './SpecTable';
export { SpecValueCell } from './SpecValueCell';
export { SpecSourceBadge, SOURCE_LABEL } from './SpecSourceBadge';
export { AddSpecificationDialog, toSpecKey } from './AddSpecificationDialog';
export type { SimilarKeyMatch, SpecDataType } from './AddSpecificationDialog';
export { buildSpecTableRows, CONFLICT_REASON } from './specTableModel';
export type {
  StoredSpecProvenance,
  StoredSpecValue,
  SpecConflict,
} from './specTableModel';
export { findVocabularyMatch, normaliseVocabulary } from './specVocabulary';
export type { VocabularyMatch } from './specVocabulary';
export type {
  SpecKeyDefinition,
  SpecScalar,
  SpecTableCallbacks,
  SpecTableRow,
} from './types';
