'use client';

import type { ConversationSLATrackingDetail } from '@/app/(protected)/sla-management/conversation-sla-tracking/types/conversationSLATracking.types';
import { SlaEscalationBanner } from './SlaEscalationBanner';
import { SlaExtensionBanner } from './SlaExtensionBanner';

/**
 * In-form SLA banner for an entity detail page (PR / stock inquiry / complaint).
 * Renders the escalation banner (latest reason of the active stage) and, when the
 * active stage's deadline has been extended, the extension banner (latest `extend`
 * event reason + new deadline). The Extend action lives in the page's gear/actions
 * dropdown via SlaExtendMenuItem + SlaExtendDialog; this component is banner-only.
 * Both banners read the active (unresolved) tracker only, so they vanish the moment
 * the stage resolves (approve / reject / close). Renders nothing when there is no
 * active tracker.
 *
 * The extension banner states the LIVE clock (#1326): "until" is the tracker's own
 * `due_at_resolution`, the date the escalation job acts on, never the date stored on
 * the extend event. Tier and assignee are the ones recorded on the extend event, i.e.
 * who held the stage when it was extended, not who holds it now. An extension that a
 * later escalation replaced no longer governs the clock, so it is not shown.
 */
export function SlaActiveTrackerControls({
  activeTracker,
}: {
  activeTracker: ConversationSLATrackingDetail | null | undefined;
  /** @deprecated label/onExtended now belong to the gear-menu SlaExtendDialog. */
  label?: string;
  onExtended?: () => void;
}) {
  if (!activeTracker) return null;
  // Latest `extend` event of the current stage (the extend reason is not
  // denormalized onto the tracker row, unlike escalation_reason). event_at desc.
  const logs = activeTracker.event_logs ?? [];
  const at = (e: { event_at: Date | string }) => new Date(e.event_at).getTime();
  const latestExtend = logs
    .filter((e) => e.event_type === 'extend')
    .sort((a, b) => at(b) - at(a))[0];
  const extensionLive =
    !!latestExtend &&
    !logs.some((e) => e.event_type === 'escalation' && at(e) > at(latestExtend));
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
      {extensionLive && (
        <SlaExtensionBanner
          reason={latestExtend.reason}
          newDue={activeTracker.due_at_resolution}
          tier={latestExtend.to_tier}
          assignee={latestExtend.assigned_user_name}
          eventAt={latestExtend.event_at}
        />
      )}
    </div>
  );
}
