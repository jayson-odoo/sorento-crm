'use client';

import type { ReactNode } from 'react';
import { formatDate } from '@/lib/helpers';

/** Minimal fields for document-style sign-off (matches Excel footer + comments). */
export type PurchaseRequestSignoffFields = {
  approval_status?: string | null;
  requested_by?: string | null;
  /** Resolved live contact name when the requestor FK is set; falls back to
   *  `requested_by` (point-in-time label) when absent. */
  requested_by_contact_name?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  approval_comments?: string | null;
};

/**
 * `decision`: the four-box sign-off the order change notice reads (Decision, Name, Date,
 * Remarks), over the same approval columns; "Pending" until a decision exists.
 */
type Variant = 'detailCard' | 'publicCard' | 'decision';

function formatDateOrDash(value: string | null | undefined): string {
  if (value == null || value === '') return '-';
  try {
    return formatDate(new Date(value));
  } catch {
    return '-';
  }
}

/**
 * Requested by / date and Approved or Rejected by / date / comments (same underlying columns as Excel).
 */
export function PurchaseRequestSignoffFooter({
  request,
  variant = 'detailCard',
  /** When set (e.g. edit form), render editable requested by / date instead of read-only text. */
  renderRequestedColumn,
}: {
  request: PurchaseRequestSignoffFields;
  variant?: Variant;
  renderRequestedColumn?: () => ReactNode;
}) {
  const isRejected = request.approval_status === 'rejected';
  const isApproved = request.approval_status === 'approved';
  const hasDecision = isRejected || isApproved;

  const actorLabel = isRejected ? 'Rejected by' : 'Approved by';
  const dateLabel = isRejected ? 'Rejected date' : 'Approved date';
  const commentsLabel = isRejected ? 'Rejection comments' : 'Approval comments';

  const comments = (request.approval_comments ?? '').trim();
  // D9: resolve the contact's live name when the requestor FK is set; the stored
  // text stays the point-in-time record and the fallback for legacy FK-less rows.
  const requestedByLabel = request.requested_by_contact_name || request.requested_by || '-';

  if (variant === 'decision') {
    const decision = isApproved ? 'Approved' : isRejected ? 'Rejected' : 'Pending';
    const boxes: Array<[string, string]> = [
      ['Decision', decision],
      ['Name', hasDecision ? request.approved_by || '-' : '-'],
      ['Date', hasDecision ? formatDateOrDash(request.approved_at) : '-'],
      ['Remarks', hasDecision ? comments || '-' : '-'],
    ];
    return (
      <div className="mt-8 grid grid-cols-1 gap-x-10 gap-y-4 border-t border-border pt-6 sm:grid-cols-2">
        {boxes.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="min-h-9 whitespace-pre-wrap break-words py-2 text-sm">{value}</p>
          </div>
        ))}
      </div>
    );
  }

  if (variant === 'publicCard') {
    return (
      <div className="mt-8 pt-6 border-t border-border space-y-0">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
          <div className="py-2 border-b border-border/60">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Requested by</p>
            <p className="text-sm font-medium">{requestedByLabel}</p>
          </div>
          <div className="py-2 border-b border-border/60">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">
              {hasDecision ? actorLabel : 'Approved by'}
            </p>
            <p className="text-sm font-medium">{hasDecision ? request.approved_by || '-' : '-'}</p>
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5 mt-3">
              {hasDecision ? dateLabel : 'Approved date'}
            </p>
            <p className="text-sm font-medium">{hasDecision ? formatDateOrDash(request.approved_at) : '-'}</p>
          </div>
          <div className="sm:col-span-2 py-2 border-b border-border/60 last:border-b-0">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">{commentsLabel}</p>
            <p className="text-sm font-medium whitespace-pre-wrap break-words">
              {comments || '-'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 gap-8 pt-6 border-t border-border">
      <div>
        {renderRequestedColumn ? (
          <div className="space-y-4">{renderRequestedColumn()}</div>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">Requested by</p>
            <p className="font-medium">{requestedByLabel}</p>
          </>
        )}
      </div>
      <div>
        <p className="text-sm text-muted-foreground">{hasDecision ? actorLabel : 'Approved by'}</p>
        <p className="font-medium">{hasDecision ? request.approved_by || '-' : '-'}</p>
        <p className="text-sm text-muted-foreground mt-3">{hasDecision ? dateLabel : 'Approved date'}</p>
        <p className="font-medium">{hasDecision ? formatDateOrDash(request.approved_at) : '-'}</p>
      </div>
      <div className="sm:col-span-2">
        <p className="text-sm text-muted-foreground">{commentsLabel}</p>
        <p className="font-medium whitespace-pre-wrap break-words">{comments || '-'}</p>
      </div>
    </div>
  );
}
