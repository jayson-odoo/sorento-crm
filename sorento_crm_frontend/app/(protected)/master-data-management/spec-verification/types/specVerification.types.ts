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

/** One key whose value moved out from under a stamp. */
export interface VerificationDiffEntry {
  spec_key: string;
  was: string | null;
  now: string | null;
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
 * One open exception, as the single verify's 409 reports it.
 *
 * Narrowed to what the refusal has to say: which key is unanswered. The full row,
 * with its proposal, is on the Specifications tab that raised the verify.
 */
export interface VerificationOpenException {
  spec_key: string;
  reason?: string | null;
}

export interface SpecVerificationCoverage {
  /** Keys this code holds a value for. */
  have: number;
  /** Keys the registry says apply to it. */
  applicable: number;
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
  | 'exceptions_open'
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
