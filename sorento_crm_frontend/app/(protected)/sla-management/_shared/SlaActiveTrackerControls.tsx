'use client';

import type { ConversationSLATrackingDetail } from '@/app/(protected)/sla-management/conversation-sla-tracking/types/conversationSLATracking.types';
import { parseDateTimeAsUTC } from '@/lib/helpers';
import { SlaEscalationBanner } from './SlaEscalationBanner';
import { SlaExtensionBanner } from './SlaExtensionBanner';
import { SlaWaitingBanner } from './SlaWaitingBanner';

/**
 * The split-clock breach rule, mirrored from the backend's `is_overdue`: before
 * responding the response deadline gates, after responding only the resolution deadline
 * does (the one Extend moves). Used ONLY to word the prompt - the server owns the guard,
 * so a mismatch here costs a sentence, never a wrong permission.
 */
function isOverdue(tracker: ConversationSLATrackingDetail): boolean {
  const now = Date.now();
  // The type says Date, the wire says naive-UTC string. Both arrive in practice, so
  // normalise rather than trust either.
  const at = (value?: string | Date | null) => {
    if (!value) return null;
    return value instanceof Date ? value.getTime() : parseDateTimeAsUTC(value).getTime();
  };
  const due = at(tracker.due_at);
  const dueResolution = at(tracker.due_at_resolution);
  if (tracker.is_resolved) return false;
  if (!tracker.is_responded && due !== null && due < now) return true;
  return dueResolution !== null && dueResolution < now;
}

/**
 * In-form SLA banner for an entity detail page (PR / stock inquiry / complaint).
 * Renders the escalation banner (latest reason of the active stage) and, when the
 * active stage's deadline has been extended, the extension banner (latest `extend`
 * event reason + new deadline). The Extend action lives in the page's gear/actions
 * dropdown via SlaExtendMenuItem + SlaExtendDialog; this component is banner-only.
 * Both banners read the active (unresolved) tracker only, so they vanish the moment
 * the stage resolves (approve / reject / close). Renders nothing when there is no
 * active tracker.
 */
export function SlaActiveTrackerControls({
  activeTracker,
  onWaitingChanged,
}: {
  activeTracker: ConversationSLATrackingDetail | null | undefined;
  /** Called after a waiting change so the page refetches the tracker (the banner reads
   *  it) - the same two-query lesson the handling lock taught: a change that touches one
   *  banner must refresh whatever else reads the tracker. */
  onWaitingChanged?: () => void;
  /** @deprecated label/onExtended now belong to the gear-menu SlaExtendDialog. */
  label?: string;
  onExtended?: () => void;
}) {
  if (!activeTracker) return null;
  // Latest `extend` event of the current stage (the extend reason is not
  // denormalized onto the tracker row, unlike escalation_reason). event_at desc.
  const latestExtend = (activeTracker.event_logs ?? [])
    .filter((e) => e.event_type === 'extend')
    .sort((a, b) => new Date(b.event_at).getTime() - new Date(a.event_at).getTime())[0];
  return (
    <div className="flex flex-col gap-2">
      <SlaEscalationBanner
        reason={activeTracker.escalation_reason}
        tier={activeTracker.current_tier}
        assignee={activeTracker.assigned_user_name}
        assigneeWaPhone={activeTracker.assigned_user_wa_phone}
        escalatedFromName={activeTracker.escalated_from_name}
        escalatedFromWaPhone={activeTracker.escalated_from_wa_phone}
        escalatedAt={activeTracker.escalated_at}
      />
      <SlaWaitingBanner
        trackingId={activeTracker.id}
        party={activeTracker.waiting_on_party}
        partyLabel={activeTracker.waiting_on_party_label}
        reason={activeTracker.waiting_on_reason}
        waitingSince={activeTracker.waiting_since}
        overdue={isOverdue(activeTracker)}
        onChanged={onWaitingChanged}
      />
      {latestExtend && (
        <SlaExtensionBanner
          reason={latestExtend.reason}
          newDue={latestExtend.due_at ?? activeTracker.due_at_resolution}
          tier={activeTracker.current_tier}
          assignee={activeTracker.assigned_user_name}
          assigneeWaPhone={activeTracker.assigned_user_wa_phone}
          eventAt={latestExtend.event_at}
        />
      )}
    </div>
  );
}
