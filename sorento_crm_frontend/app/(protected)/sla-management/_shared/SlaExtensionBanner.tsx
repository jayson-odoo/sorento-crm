'use client';

import { CalendarClock } from 'lucide-react';
import { formatDateTime, parseDateTimeAsUTC } from '@/lib/helpers';

/**
 * Shows the LATEST extension reason of the form's CURRENT (active, unresolved)
 * SLA stage tracker — mirrors {@link SlaEscalationBanner}, but sourced from the
 * tracker's `extend` event logs (the extend reason is not denormalized onto the
 * tracker row the way `escalation_reason` is). Because it reads the active
 * tracker only, it disappears automatically the moment the stage resolves
 * (approve / reject / close) and the tracker becomes resolved — and a freshly
 * spawned next stage carries no `extend` event, so nothing shows there either.
 * Renders nothing if the current stage has never been extended.
 */
export function SlaExtensionBanner({
  reason,
  newDue,
  tier,
  assignee,
}: {
  reason?: string | null;
  newDue?: string | Date | null;
  tier?: number | null;
  assignee?: string | null;
}) {
  if (!reason || !reason.trim()) return null;
  const clean = reason.trim();
  const until = newDue ? formatDateTime(parseDateTimeAsUTC(newDue)) : null;
  const meta = [
    typeof tier === 'number' ? `tier ${tier}` : null,
    assignee ? `assigned to ${assignee}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className="flex items-start gap-2 rounded-md border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:border-sky-700/60 dark:bg-sky-950/40 dark:text-sky-200">
      <CalendarClock className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0">
        <span className="font-medium">
          SLA deadline extended{until ? ` until ${until}` : ''}
          {meta ? ` — ${meta}` : ''}
        </span>
        <span> — {clean}</span>
      </p>
    </div>
  );
}
