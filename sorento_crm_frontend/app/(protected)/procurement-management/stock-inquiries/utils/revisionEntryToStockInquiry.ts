/**
 * One stored revision, shaped like a stock inquiry (round 6, 6.3/6.4).
 *
 * The point is the FORMAT GUARANTEE: a revision export must be the same document
 * as the main export, so instead of a second layout for history, the snapshot is
 * adapted back into the entity shape `buildFormRows` already takes. One layout,
 * one place to change it.
 *
 * The rule every value follows is the backend's: a value printed for a revision
 * comes from that version's STORED SNAPSHOT, never from the live row. The
 * document exists to show the form as it was, so reading the current row would
 * defeat it.
 */

import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import { withRevisionSuffix } from '@/lib/document-number';

import type { StockInquiryDetail } from '../types/stockInquiry.types';

/**
 * Never carried into a revision, even though the live row has a value.
 *
 * Matched field-for-field to `StockInquiryPDFService._revision_rows`, which
 * prints these only when the SNAPSHOT itself holds them - and the snapshot never
 * does (they are not in `PortalService._editable_fields('stock_inquiry')`).
 * Printing today's purchasing reply under an "as it was" heading would report
 * the answer to a question the contact has since changed.
 *
 * `status` is separate: the snapshot DOES carry it, but it is written before the
 * post-revision status restart is applied, so it holds the superseded version's
 * status and would read as wrong information. The backend never renders it
 * either (see `pdf_revision_support`), so neither does this.
 */
export const STOCK_INQUIRY_REVISION_BLANK_FIELDS = [
  'purchasing_response',
  'last_responded_by',
  'last_responded_by_name',
  'last_responded_at',
  'rejection_reason',
  'reopen_reason',
  'void_reason',
] as const;

export function revisionEntryToStockInquiry(
  entry: FormRevisionEntry,
  live: StockInquiryDetail,
): StockInquiryDetail {
  const snapshot = (entry.snapshot ?? {}) as Record<string, unknown>;
  const merged: Record<string, unknown> = {
    // Identity comes from the live record - a revision is a version OF it, not a
    // different record.
    ...(live as unknown as Record<string, unknown>),
    // Everything the version stored wins over today's values.
    ...snapshot,
    id: live.id,
    // `SI-26-0184-R2`: the number as at this version, suffixed exactly as every
    // other surface renders it (UAC N1/N4). Written out rather than derived
    // because `buildFormRows` prints `inquiry_number` verbatim.
    inquiry_number: withRevisionSuffix(
      (snapshot.inquiry_number as string | null | undefined) ?? live.inquiry_number,
      entry.revision_no,
    ),
    revision_no: entry.revision_no,
    // The "Date" row means the date THIS version was submitted, not the date the
    // record was created (same choice the PDF makes on a revision page).
    created_at: entry.submitted_at ?? live.created_at,
  };
  // Blanked AFTER the overlay, so a snapshot that starts carrying one of these
  // keeps it: the rule is "the version never had this", not "hide it".
  for (const field of STOCK_INQUIRY_REVISION_BLANK_FIELDS) {
    if (!(field in snapshot)) merged[field] = null;
  }
  merged.status = null;
  return merged as unknown as StockInquiryDetail;
}
