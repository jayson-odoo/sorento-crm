'use client';

import { CalendarClock } from 'lucide-react';

import { PersonLink } from '@/components/common/PersonLink';
import { formatDateTime, formatDateTimeInMalaysia, parseDateTimeAsUTC } from '@/lib/helpers';

/**
 * Shows the LATEST extension reason of the form's CURRENT (active, unresolved)
 * SLA stage tracker — mirrors {@link SlaEscalationBanner}, but sourced from the
 * tracker's `extend` event logs (the extend reason is not denormalized onto the
 * tracker row the way `escalation_reason` is). Because it reads the active
 * tracker only, it disappears automatically the moment the stage resolves
 * (approve / reject / close) and the tracker becomes resolved — and a freshly
 * spawned next stage carries no `extend` event, so nothing shows there either.
 * Renders nothing if the current stage has never been extended.
 *
 * WHO = the current assignee, linked to wa.me when resolvable (PersonLink).
 * WHEN = the extend event time (`eventAt`) in Malaysia time. The new due date
 * keeps its existing `formatDateTime` rendering.
 */
export function SlaExtensionBanner({
  reason,
  newDue,
  tier,
  assignee,
  assigneeWaPhone,
  eventAt,
}: {
  reason?: string | null;
  newDue?: string | Date | null;
  tier?: number | null;
  assignee?: string | null;
  assigneeWaPhone?: string | null;
  eventAt?: string | Date | null;
}) {
  if (!reason || !reason.trim()) return null;
  const clean = reason.trim();
  const until = newDue ? formatDateTime(parseDateTimeAsUTC(newDue)) : null;
  const when = eventAt ? formatDateTimeInMalaysia(eventAt) : '';
  const assigneeName = assignee?.trim();
  const meta = [typeof tier === 'number' ? `tier ${tier}` : null, when || null]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className="flex items-start gap-2 rounded-md border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:border-sky-700/60 dark:bg-sky-950/40 dark:text-sky-200">
      <CalendarClock className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0">
        <span className="font-medium">
          SLA deadline extended{until ? ` until ${until}` : ''}
          {meta ? ` — ${meta}` : ''}
          {assigneeName ? (
            <>
              {' · assigned to '}
              <PersonLink name={assignee} waPhone={assigneeWaPhone} />
            </>
          ) : null}
        </span>
        <span> — {clean}</span>
      </p>
    </div>
  );
}
