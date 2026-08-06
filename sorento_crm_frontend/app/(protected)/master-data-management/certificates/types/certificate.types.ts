/**
 * Certificate register - frontend types (Phase 1 prototype).
 *
 * A certificate is an identity (scheme + certifying body + number) with a chain
 * of revisions, one per issue. Products link to the identity, so a renewal does
 * not churn coverage. Validity is always DERIVED from the current revision's
 * dates and is never a stored status.
 *
 * Spec: documentation/plans/certificates/certificate-register-acceptance-criteria.md
 * (groups SCH / VAL / REV / COV / DUP / FE).
 */

/** Certification scheme, e.g. `PPS` or `SPAN`. Extracted free text, not an enum on the backend. */
export type CertificateScheme = string;

/** SCH-7 / LIF-4: exactly two values. No validity value is ever a status. */
export type CertificateStatus = 'active' | 'archived';

/** VAL-1..VAL-5: derived from the current revision, never stored. */
export type CertificateValidityState =
  | 'valid'
  | 'expiring_soon'
  | 'expired'
  | 'not_yet_valid'
  | 'unknown';

/** Where a row came from: extracted by the document reader, or added by a person. */
/**
 * A review reason as the backend records it: an object carrying a machine-readable
 * `code` plus whatever context the rule captured. A bare string is tolerated so an
 * older payload or a direct code does not crash the renderer.
 */
export type CertificateReviewReason = string | { code: string; [key: string]: unknown };

export type CertificateSource = 'ai' | 'manual';

/**
 * The file behind a revision. `is_removed` covers REV-5: the attachment was
 * trashed but the revision row still renders with its dates.
 */
export interface CertificateRevisionFile {
  filename: string;
  /** Signed URL, resolved server-side. Null when the file is gone (never a broken URL). */
  preview_url: string | null;
  download_url: string | null;
  is_removed: boolean;
}

export interface CertificateRevision {
  id: string;
  revision_no: number;
  issued_at: string | null;
  valid_from: string | null;
  valid_until: string | null;
  is_current: boolean;
  source: CertificateSource;
  needs_review: boolean;
  /** Machine-readable reason codes (RVW-1), rendered through `reviewReasonLabel`. */
  review_reasons: CertificateReviewReason[];
  /** Extracted product strings that matched nothing (RVW-3). */
  unmatched_products: string[];
  /** Inherited by the projection rows for this revision (SEC-3). */
  // Emitted by CertificateRevisionResponse. `access_levels` is null when the
  // revision has no attachment; the signed urls are present only for the current
  // revision, so superseded rows render the filename without controls.
  attachment_filename?: string | null;
  attachment_is_deleted?: boolean | null;
  preview_url?: string | null;
  download_url?: string | null;
  access_levels: string[] | null;
  created_at: string;
}

export interface CertificateProduct {
  /** `certificate_products` row id - used for unlink only, never rendered. */
  id: string;
  product_id: string;
  product_code: string;
  product_name: string;
  /** COV-2 / FE-7: rendered as colour, never as a per-row text badge. */
  source: CertificateSource;
}

/** One expiry reminder that actually went out for this certificate (REM-3/REM-5). */
export interface CertificateReminder {
  id: string;
  days_before: number;
  sent_at: string;
  recipient_count: number;
}

/** Minimal shape of the certificate a near-match points at (DUP-3). */
export interface CertificateRef {
  id: string;
  scheme: CertificateScheme;
  certificate_number: string;
}

export interface Certificate {
  id: string;
  scheme: CertificateScheme;
  certifying_body: string;
  certificate_number: string;
  issuer: string | null;
  title: string | null;
  status: CertificateStatus;

  /* Derived validity - computed from `current_revision`, never stored (VAL). */
  validity_state: CertificateValidityState;
  is_expired: boolean;
  valid_from: string | null;
  valid_until: string | null;
  days_until_expiry: number | null;

  covered_product_count: number;
  needs_review: boolean;
  review_reasons: CertificateReviewReason[];

  /** DUP-2: set when a trigram probe found a near match. Never auto-merged. */
  possible_duplicate_of_certificate_id: string | null;
  /** Resolved label for the above, so the UI never renders an id. */
  possible_duplicate_of: CertificateRef | null;

  current_revision: CertificateRevision | null;

  /* Detail-only collections. Absent (or empty) on list rows. */
  revisions?: CertificateRevision[];
  products?: CertificateProduct[];
  unmatched_products?: string[];
  reminders?: CertificateReminder[];

  created_at: string;
  updated_at: string;
}

/**
 * Create / edit payload. The identity fields live on `certificates`; the three
 * date fields are applied to the CURRENT revision (dates live on the revision).
 * A human edit that fixes a flagged field clears `needs_review` (RVW-4).
 */
export interface CertificateFormData {
  scheme: string;
  certifying_body: string;
  certificate_number: string;
  issuer?: string | null;
  title?: string | null;
  status: CertificateStatus;
  issued_at?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
}
