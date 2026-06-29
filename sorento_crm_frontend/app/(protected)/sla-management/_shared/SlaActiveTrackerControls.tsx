'use client';

import type { ConversationSLATrackingDetail } from '@/app/(protected)/sla-management/conversation-sla-tracking/types/conversationSLATracking.types';
import { SlaEscalationBanner } from './SlaEscalationBanner';

/**
 * In-form SLA banner for an entity detail page (PR / stock inquiry / complaint).
 * Renders the escalation banner (latest reason of the active stage). The Extend
 * action now lives in the page's gear/actions dropdown via SlaExtendMenuItem +
 * SlaExtendDialog (so it sits next to "Escalate SLA"); this component is banner-only.
 * Renders nothing when there is no active tracker.
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
  return (
    <SlaEscalationBanner
      reason={activeTracker.escalation_reason}
      tier={activeTracker.current_tier}
      assignee={activeTracker.assigned_user_name}
    />
  );
}
