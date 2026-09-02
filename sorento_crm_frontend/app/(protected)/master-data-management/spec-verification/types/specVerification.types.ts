/**
 * Types for the spec verification worklist (PR 3).
 *
 * Field names are the wire shape, snake_case, exactly as the API contract at the
 * top of `services/specVerificationService.ts` documents it.
 */
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';

/**
 * Derived, never stored (AC-D.2). A manual withdrawal reads `unverified`, not
 * `needs_reverify`, because a withdrawal has no diff to re-check.
 */
export type VerificationState = 'unverified' | 'verified' | 'needs_reverify';

/**
 * One side of a diff row: the stored spec ENTRY, exactly as `spec.values` holds it.
 *
 * The diff carries the raw entries rather than scalars, because that is what the
 * write path compared. Render it with `readableEntry` from `@/lib/spec-readable` -
 * a scalar formatter renders the literal `[object Object]`.
 */
export interface VerificationDiffValue {
  value: string | number | boolean | null;
  unit?: string | null;
}

/** One key whose value moved out from under a stamp. Null means the key was absent. */
export interface VerificationDiffEntry {
  spec_key: string;
  was: VerificationDiffValue | null;
  now: VerificationDiffValue | null;
}

export interface VerificationBlock {
  state: VerificationState;
  verified_by_name: string | null;
  verified_at: string | null;
  invalidated_at: string | null;
  /** `values_changed` (the system did it) or `manual_unverify` (a person did it). */
  invalidated_reason: string | null;
  invalidated_by_name: string | null;
  invalidated_diff: { changed: VerificationDiffEntry[] } | null;
}

/**
 * One applicable key, and what this code says for it. `value` is null when unfilled.
 *
 * The stored ENTRY again, not a scalar - `readableEntry` renders it, the same reader
 * the invalidation diff uses.
 */
export interface SpecVerificationCoverageItem {
  spec_key: string;
  label: string;
  value: VerificationDiffValue | null;
}

export interface SpecVerificationCoverage {
  /** Keys this code holds a value for. */
  have: number;
  /** Keys the registry says apply to it. */
  applicable: number;
  /** The denominator itemised, sorted by label: what the Coverage cell opens. */
  items: SpecVerificationCoverageItem[];
}

export interface SpecVerificationRow {
  /** The copy of the code in the caller's company scope; drives the row-click route. */
  product_id: string;
  product_code: string;
  product_name: string;
  class_label: string | null;
  brand_name: string | null;
  is_discontinued: boolean;
  coverage: SpecVerificationCoverage;
  /**
   * Derivation's own count of open catalogue exceptions for this code. Rendered as
   * a warning pill in the Coverage cell, "{n} need a human" (AC-F.4, design-language
   * D11) - the reason detail stays internal derivation data, so the pill and its
   * hover card carry only the count.
   */
  open_exceptions: number;
  /** Echoed back on verify so the same-transaction guard applies from the list (AC-D.24). */
  values_hash: string;
  verification: VerificationBlock;
}

/** Counts the same set the list does, minus the `state` filter, so the progress line stays honest. */
export interface SpecVerificationSummary {
  total: number;
  verified: number;
  needs_reverify: number;
  unverified: number;
}

export interface SpecVerificationWorklistResponse {
  data: SpecVerificationRow[];
  pagination: { total: number; page: number; limit: number };
  summary: SpecVerificationSummary;
  /**
   * The class filter's own options: distinct, sorted, never null, and computed
   * before the class and state filters so filtering to a class does not empty the
   * dropdown that did the filtering.
   */
  classes: string[];
}

export type SpecVerificationWorklistParams = DataGridApiFetchParams & {
  /** Empty string means no state filter. */
  state?: VerificationState | '';
  /** Empty string means no class filter. */
  class_label?: string;
  include_discontinued?: boolean;
};

export type VerifyOutcome =
  | 'verified'
  | 'already_verified'
  | 'values_changed'
  | 'not_found';

export type UnverifyOutcome = 'unverified' | 'no_change';

export interface VerifyItem {
  product_code: string;
  values_hash: string;
}

export interface VerifyBulkResult {
  product_code: string;
  outcome: VerifyOutcome;
  /** Present when the row must refresh: the hash the server now holds. */
  values_hash?: string;
  verification?: VerificationBlock;
}

export interface VerifyBulkResponse {
  results: VerifyBulkResult[];
  counts: { verified: number; skipped: number };
}

export interface VerifyResponse {
  product_code: string;
  outcome: 'verified' | 'already_verified';
  verification: VerificationBlock;
  values_hash: string;
}

export interface UnverifyBulkResult {
  product_code: string;
  outcome: UnverifyOutcome;
  verification?: VerificationBlock;
}

export interface UnverifyBulkResponse {
  results: UnverifyBulkResult[];
  counts: { unverified: number; no_change: number };
}

export interface UnverifyResponse {
  product_code: string;
  outcome: UnverifyOutcome;
  verification: VerificationBlock;
}
