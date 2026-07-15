'use client';

import { AlertCircle } from 'lucide-react';

import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { PersonLink } from './PersonLink';

/**
 * Red alert banner shown at the top of an entity detail page when the form is
 * rejected, surfacing WHO rejected it, WHEN, and WHY. Mirrors the amber
 * SlaEscalationBanner placement (top, under the header) and the portal's
 * destructive rejection styling, so internal staff see the reason without
 * scrolling.
 *
 * When `rejectedByName` is present the copy reads
 * "Rejected by {PersonLink} · {when} — {reason}" — the name links to
 * `wa.me/{digits}` when `rejectedByWaPhone` resolves, else plain text (FB-1).
 * With no rejecter it falls back to today's "Rejected — {reason}" copy.
 *
 * Render only when the entity is actually rejected — caller gates on the status
 * field. Renders nothing if no reason text is present.
 */
export function RejectionReasonBanner({
  reason,
  rejectedByName,
  rejectedByWaPhone,
  rejectedAt,
}: {
  reason?: string | null;
  rejectedByName?: string | null;
  rejectedByWaPhone?: string | null;
  rejectedAt?: string | null;
}) {
  if (!reason || !reason.trim()) return null;
  const who = rejectedByName?.trim();
  const when = rejectedAt ? formatDateTimeInMalaysia(rejectedAt) : '';
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0">
        {who ? (
          <span className="font-medium">
            Rejected by <PersonLink name={rejectedByName} waPhone={rejectedByWaPhone} />
            {when ? ` · ${when}` : ''}
          </span>
        ) : (
          <span className="font-medium">Rejected</span>
        )}
        <span> — {reason.trim()}</span>
      </p>
    </div>
  );
}
