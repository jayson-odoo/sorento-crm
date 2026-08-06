/**
 * Display helpers for the certificate register: labels for the derived validity
 * states, review reason codes and access levels, plus the source colour scheme
 * used by the covered-products list (FE-7 - colour, never a per-row word).
 *
 * Pills themselves come from `lib/status-pill.ts` (LIF-3: no bespoke colour map).
 */
import type {
  CertificateReviewReason,
  CertificateSource,
  CertificateStatus,
  CertificateValidityState,
} from '../types/certificate.types';

export const VALIDITY_STATE_LABELS: Record<CertificateValidityState, string> = {
  valid: 'Valid',
  expiring_soon: 'Expiring soon',
  expired: 'Expired',
  not_yet_valid: 'Not yet valid',
  unknown: 'Unknown',
};

export const STATUS_LABELS: Record<CertificateStatus, string> = {
  active: 'Active',
  archived: 'Archived',
};

/** RVW-1 reason codes. Unknown codes fall back to a de-slugged version. */
const REVIEW_REASON_LABELS: Record<string, string> = {
  // Keys must match the codes in certificate_service.py exactly. A mismatch is
  // invisible: the label just falls through to the de-slugged code.
  missing_required_field: 'A required field could not be read',
  unmatched_products: 'Some product codes matched nothing',
  no_product_coverage: 'No product is covered by this certificate',
  valid_until_not_after_valid_from: 'Expiry date is not after the issue date',
  expired_at_ingest: 'Already expired when it was filed',
  implausible_validity_span: 'Validity span is longer than this document type allows',
  possible_duplicate: 'Closely matches an existing certificate',
  backfilled_from_filename: 'Dates read from the file name, not the document',
  no_revision_on_file: 'No document has been filed against this certificate',
};

/**
 * The backend records each review reason as an OBJECT carrying a `code` plus
 * whatever context the rule captured (for example the offending span), not as a
 * bare string. Accept both: a plain string still renders, so a caller passing a
 * code directly is not a crash.
 */
export function reviewReasonLabel(reason: CertificateReviewReason): string {
  const code = typeof reason === 'string' ? reason : (reason?.code ?? '');
  if (!code) return 'Needs review';
  const known = REVIEW_REASON_LABELS[code];
  if (known) {
    // `missing_required_field` carries WHICH field; without it the message is
    // useless to whoever has to fix the row.
    const field = typeof reason === 'object' && reason !== null ? reason.field : undefined;
    return field ? `${known}: ${String(field)}` : known;
  }
  const words = String(code).replace(/[_-]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Human label for an access level code. Phase 2 swaps this for the shared
 * `accessLevelNameMap` once the detail response is live.
 */
export function accessLevelLabel(code: string): string {
  // `access_levels` arrives as raw JSON off the attachment, so a non-string
  // element is possible; String() keeps a bad row from taking the page down
  // (same reason reviewReasonLabel coerces).
  const words = String(code ?? '').replace(/[_-]+/g, ' ').trim();
  return words.replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * How a covered-product link got there, rendered as a shared status pill
 * (lib/status-pill) so it matches every other pill in the system rather than a
 * per-feature colour scheme.
 */
export const SOURCE_LABELS: Record<CertificateSource, string> = {
  ai: 'From document',
  manual: 'Confirmed',
};

/** Filter option values. `attention` is the validity-scoped default (FE-3). */
export const VALIDITY_FILTER_ALL = 'all';
export const VALIDITY_FILTER_ATTENTION = 'attention';

export const VALIDITY_FILTER_OPTIONS = [
  { value: VALIDITY_FILTER_ATTENTION, label: 'Needs attention (expiring + expired)' },
  { value: VALIDITY_FILTER_ALL, label: 'Any validity' },
  { value: 'valid', label: VALIDITY_STATE_LABELS.valid },
  { value: 'expiring_soon', label: VALIDITY_STATE_LABELS.expiring_soon },
  { value: 'expired', label: VALIDITY_STATE_LABELS.expired },
  { value: 'not_yet_valid', label: VALIDITY_STATE_LABELS.not_yet_valid },
  { value: 'unknown', label: VALIDITY_STATE_LABELS.unknown },
];

/**
 * Schemes offered in the filter. Extracted free text on the backend; a fixed
 * list is enough while the register only carries the two live schemes.
 */
export const SCHEME_FILTER_OPTIONS = [
  { value: 'all', label: 'All schemes' },
  { value: 'PPS', label: 'PPS' },
  { value: 'SPAN', label: 'SPAN' },
];

export const STATUS_FILTER_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'all', label: 'All statuses' },
];

export const EXPIRING_WITHIN_OPTIONS = [
  { value: 'any', label: 'Any expiry date' },
  { value: '7', label: 'Expiring within 7 days' },
  { value: '30', label: 'Expiring within 30 days' },
  { value: '90', label: 'Expiring within 90 days' },
];

export const NEEDS_REVIEW_OPTIONS = [
  { value: 'any', label: 'Reviewed and unreviewed' },
  { value: 'true', label: 'Needs review only' },
];
