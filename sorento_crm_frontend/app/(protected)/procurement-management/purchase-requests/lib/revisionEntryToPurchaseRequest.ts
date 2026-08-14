/**
 * One stored revision, shaped like a purchase request / sponsorship form
 * (round 6, 6.3/6.4).
 *
 * Same contract as the stock inquiry adapter: the snapshot is adapted back into
 * the entity shape the EXISTING document builders take, so a revision sheet is
 * the same document as the main export and there is never a second layout to
 * keep in step. Every printed value comes from the version's stored snapshot,
 * never from the live row.
 */

import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';

import type { PurchaseRequest, PurchaseRequestLine } from '../types/purchaseRequest.types';

/**
 * Never carried into a revision, even though the live row has a value.
 *
 * Matched to `PurchaseRequestPDFService._reader(req, snapshot)`, which reads a
 * revision page EXCLUSIVELY from the snapshot: a field the snapshot never
 * carried reads as empty, which is what the version had. The list is therefore
 * the stage output a revision invalidates (`_REQUEST_INVALIDATED` on the backend
 * adapter: approval status/comments/approver/date/signature), plus the live-only
 * text sibling the sheet renders, plus the void reason.
 *
 * `status` is handled separately below: the snapshot DOES carry it, but it holds
 * the SUPERSEDED version's status (the snapshot is written before the
 * post-revision restart), so neither document renders it.
 */
export const PURCHASE_REQUEST_REVISION_BLANK_FIELDS = [
  'approval_status',
  'approval_comments',
  'approved_at',
  'approved_by',
  'approval_signature_ref',
  'expected_po_date_text',
  'void_reason',
] as const;

/** A snapshotted numeric ("1200.00") back to a number, or null when it is not
 *  one - the line table formats numbers and must not print `NaN`. */
function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * `snapshot.products` as line rows.
 *
 * The stored order IS the order (a snapshot carries no `sort_order`), so it is
 * re-stamped by position - the document builders read lines in order.
 */
function snapshotLines(
  entry: FormRevisionEntry,
  snapshot: Record<string, unknown>,
  live: PurchaseRequest,
): PurchaseRequestLine[] {
  const products = Array.isArray(snapshot.products) ? snapshot.products : [];
  return products.map((raw, index) => {
    const item = (raw ?? {}) as Record<string, unknown>;
    return {
      id: `${entry.id}-line-${index}`,
      purchase_request_id: live.id,
      item_code: (item.item_code as string | null | undefined) ?? null,
      quantity: toNumber(item.quantity),
      unit_price: toNumber(item.unit_price),
      total: toNumber(item.total),
      remark: (item.remark as string | null | undefined) ?? null,
      sort_order: index,
    };
  });
}

export function revisionEntryToPurchaseRequest(
  entry: FormRevisionEntry,
  live: PurchaseRequest,
): PurchaseRequest {
  const snapshot = (entry.snapshot ?? {}) as Record<string, unknown>;
  // `products` is the line list, not a column - it is mapped onto `lines` below.
  const snapshotFields = { ...snapshot };
  delete snapshotFields.products;
  const merged: Record<string, unknown> = {
    // Identity comes from the live record - a revision is a version OF it.
    ...(live as unknown as Record<string, unknown>),
    ...snapshotFields,
    id: live.id,
    // The type decides which document is rendered at all, and a revision cannot
    // change it (it is not an editable field).
    request_type: live.request_type,
    // The number stays BARE here and the `-R2` suffix is derived from
    // `revision_no`, because the document builders render it through
    // `withRevisionSuffix` - writing a suffixed value would produce `-R2-R2`.
    request_number:
      (snapshot.request_number as string | null | undefined) ?? live.request_number,
    revision_no: entry.revision_no,
    // The "Date" beside the number is the date THIS version was submitted, not
    // the record's (the live `submitted_at` is not re-stamped by a revision).
    submitted_at: entry.submitted_at ?? live.submitted_at,
    lines: snapshotLines(entry, snapshot, live),
  };
  // Blanked AFTER the overlay, and only where the snapshot really is silent: the
  // rule is "the version never had this", not "hide it".
  for (const field of PURCHASE_REQUEST_REVISION_BLANK_FIELDS) {
    if (!(field in snapshot)) merged[field] = null;
  }
  merged.status = null;
  return merged as unknown as PurchaseRequest;
}
