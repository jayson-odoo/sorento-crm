'use client';

import type { ReactNode } from 'react';
import { formatDate } from '@/lib/helpers';

/** Minimal fields for document-style sign-off (matches Excel footer + comments). */
export type PurchaseRequestSignoffFields = {
  approval_status?: string | null;
  requested_by?: string | null;
  /** Footer "Date" under Requested by = the request date (user-entered). */
  request_date?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  approval_comments?: string | null;
};

type Variant = 'detailCard' | 'publicCard';

function formatDateOrDash(value: string | null | undefined): string {
  if (value == null || value === '') return '—';
  try {
    return formatDate(new Date(value));
  } catch {
    return '—';
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

  if (variant === 'publicCard') {
    return (
      <div className="mt-8 pt-6 border-t border-border space-y-0">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
          <div className="py-2 border-b border-border/60">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Requested by</p>
            <p className="text-sm font-medium">{request.requested_by || '—'}</p>
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5 mt-3">Request date</p>
            <p className="text-sm font-medium">{formatDateOrDash(request.request_date)}</p>
          </div>
          <div className="py-2 border-b border-border/60">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">
              {hasDecision ? actorLabel : 'Approved by'}
            </p>
            <p className="text-sm font-medium">{hasDecision ? request.approved_by || '—' : '—'}</p>
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5 mt-3">
              {hasDecision ? dateLabel : 'Approved date'}
            </p>
            <p className="text-sm font-medium">{hasDecision ? formatDateOrDash(request.approved_at) : '—'}</p>
          </div>
          <div className="sm:col-span-2 py-2 border-b border-border/60 last:border-b-0">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">{commentsLabel}</p>
            <p className="text-sm font-medium whitespace-pre-wrap break-words">
              {comments || '—'}
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
            <p className="font-medium">{request.requested_by || '—'}</p>
            <p className="text-sm text-muted-foreground mt-3">Request date</p>
            <p className="font-medium">{formatDateOrDash(request.request_date)}</p>
          </>
        )}
      </div>
      <div>
        <p className="text-sm text-muted-foreground">{hasDecision ? actorLabel : 'Approved by'}</p>
        <p className="font-medium">{hasDecision ? request.approved_by || '—' : '—'}</p>
        <p className="text-sm text-muted-foreground mt-3">{hasDecision ? dateLabel : 'Approved date'}</p>
        <p className="font-medium">{hasDecision ? formatDateOrDash(request.approved_at) : '—'}</p>
      </div>
      <div className="sm:col-span-2">
        <p className="text-sm text-muted-foreground">{commentsLabel}</p>
        <p className="font-medium whitespace-pre-wrap break-words">{comments || '—'}</p>
      </div>
    </div>
  );
}
