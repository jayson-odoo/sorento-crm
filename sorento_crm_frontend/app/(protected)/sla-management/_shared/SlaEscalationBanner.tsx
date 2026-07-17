'use client';

import { AlertTriangle } from 'lucide-react';

import { PersonLink } from '@/components/common/PersonLink';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

/**
 * Shows the LATEST escalation reason of the form's CURRENT (active, unresolved)
 * SLA stage tracker. Because it reads the active tracker's `escalation_reason`
 * field (overwritten on every escalation), it always reflects the most recent
 * escalation — and disappears automatically when the stage resolves and the next
 * stage spawns (a fresh tracker with no escalation). Renders nothing if the
 * current stage has not been escalated.
 *
 * Both people are linked to wa.me when resolvable (PersonLink): the CURRENT
 * assignee ("now assigned to …", who to chase now) and, when known, the
 * escalated-FROM owner (who missed the action at the prior tier). WHEN =
 * `escalatedAt` in Malaysia time.
 */
export function SlaEscalationBanner({
  reason,
  tier,
  assignee,
  assigneeWaPhone,
  escalatedFromName,
  escalatedFromWaPhone,
  escalatedAt,
}: {
  reason?: string | null;
  tier?: number | null;
  assignee?: string | null;
  assigneeWaPhone?: string | null;
  escalatedFromName?: string | null;
  escalatedFromWaPhone?: string | null;
  escalatedAt?: string | Date | null;
}) {
  if (!reason || !reason.trim()) return null;
  // Stored as "manual: <reason>" / "auto: <reason>"; show the clean text.
  const clean = reason.replace(/^(manual|auto)(\s+escalation)?:?\s*/i, '').trim() || reason.trim();
  const when = escalatedAt ? formatDateTimeInMalaysia(escalatedAt) : '';
  const fromName = escalatedFromName?.trim();
  // tier + when render as plain text; the two names render as links (PersonLink).
  const metaPrefix = [typeof tier === 'number' ? `tier ${tier}` : null, when || null]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0">
        <span className="font-medium">
          SLA escalated{metaPrefix ? ` — ${metaPrefix}` : ''}
          {assignee ? (
            <>
              {' · now assigned to '}
              <PersonLink name={assignee} waPhone={assigneeWaPhone} />
            </>
          ) : null}
          {fromName ? (
            <>
              {' · escalated from '}
              <PersonLink name={escalatedFromName} waPhone={escalatedFromWaPhone} />
            </>
          ) : null}
        </span>
        <span> — {clean}</span>
      </p>
    </div>
  );
}
