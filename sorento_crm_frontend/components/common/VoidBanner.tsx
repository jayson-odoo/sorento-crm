'use client';

import { Ban } from 'lucide-react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

/**
 * Gray / muted banner shown at the top of a form detail page when the form is
 * VOIDED, surfacing WHO voided it, WHEN (Malaysia time), and WHY. Mirrors the
 * placement of {@link RejectionReasonBanner} (top, under the header) but is
 * deliberately neutral gray — voiding is an administrative annulment, not an
 * error or rejection, so it must NOT read as destructive/red.
 *
 * Render only when the form is actually voided — the caller gates on
 * `status === 'voided'`. Renders nothing if `voided` is false.
 *
 * PersonLink (wa.me) is not present in this repo, so the actor renders as bold
 * plain text; swap to <PersonLink> when the form-banner-person-links feature lands.
 */
export interface VoidBannerProps {
  /** Whether the form is voided — caller passes `status === 'voided'`. */
  voided: boolean;
  voidedByName?: string | null;
  voidedAt?: string | null;
  voidReason?: string | null;
}

export function VoidBanner({
  voided,
  voidedByName,
  voidedAt,
  voidReason,
}: VoidBannerProps) {
  if (!voided) return null;

  const who = (voidedByName ?? '').trim();
  const when = voidedAt ? formatDateTimeInMalaysia(voidedAt) : '';
  const reason = (voidReason ?? '').trim();

  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-gray-300 bg-gray-100 px-3 py-2 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-800/60 dark:text-gray-300"
    >
      <Ban className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0">
        <span className="font-medium">Voided</span>
        {who ? (
          <>
            {' by '}
            <span className="font-medium">{who}</span>
          </>
        ) : null}
        {when ? <span> · {when}</span> : null}
        {reason ? <span> — {reason}</span> : null}
      </p>
    </div>
  );
}
