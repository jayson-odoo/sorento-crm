'use client';

import { History } from 'lucide-react';

import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { withRevisionSuffix } from '@/lib/document-number';

/**
 * Banner shown at the top of an office detail page when the contact has revised
 * their submission (UAC H1). Sibling of {@link RejectionReasonBanner} and
 * {@link VoidBanner} and deliberately built on the same shape (icon + one
 * sentence, same rounded border box, same placement under the header) so the
 * three read as one family.
 *
 * Amber, not red: a revision is not an error and not an annulment, it is new
 * work arriving. Renders nothing at revision 0 - the caller may mount it
 * unconditionally.
 */
export interface RevisionBannerProps {
  /** Denormalized counter on the entity. 0 (or missing) renders nothing. */
  revisionNo?: number | null;
  /** Base document number, bare. The `-R{n}` suffix is derived here (UAC N2). */
  documentNumber?: string | null;
  /** When the latest revision landed (naive UTC from the backend). */
  revisedAt?: string | null;
  /** Contact who sent it, already resolved to a display name (no UUIDs). */
  revisedByName?: string | null;
  /** The reason they gave, verbatim (UAC D2). */
  reason?: string | null;
  /** Where the flow restarted, human readable (e.g. "Project Sales"). */
  restartedAtLabel?: string | null;
}

export function RevisionBanner({
  revisionNo,
  documentNumber,
  revisedAt,
  revisedByName,
  reason,
  restartedAtLabel,
}: RevisionBannerProps) {
  const rev = Number(revisionNo ?? 0);
  if (!Number.isFinite(rev) || rev <= 0) return null;

  const number = withRevisionSuffix(documentNumber, rev);
  const when = revisedAt ? formatDateTimeInMalaysia(revisedAt) : '';
  const who = (revisedByName ?? '').trim();
  const why = (reason ?? '').trim();
  const restarted = (restartedAtLabel ?? '').trim();

  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
    >
      <History className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0 break-words">
        <span className="font-medium">
          Revision {rev}
          {number ? ` (${number})` : ''}
        </span>
        {when ? <span> · {when}</span> : null}
        {who ? (
          <>
            {' by '}
            <span className="font-medium">{who}</span>
          </>
        ) : null}
        {why ? <span> - {why}</span> : null}
        {restarted ? <span> Work restarted at {restarted}.</span> : null}
      </p>
    </div>
  );
}
