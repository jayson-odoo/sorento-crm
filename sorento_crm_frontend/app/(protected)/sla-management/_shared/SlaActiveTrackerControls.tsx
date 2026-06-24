'use client';

import { useSession } from 'next-auth/react';

import type { ConversationSLATrackingDetail } from '@/app/(protected)/sla-management/conversation-sla-tracking/types/conversationSLATracking.types';
import ExtendDueButton from '@/app/(protected)/sla-management/conversation-sla-tracking/components/ExtendDueButton';
import { SlaEscalationBanner } from './SlaEscalationBanner';

/**
 * In-form SLA controls for an entity detail page (PR / stock inquiry / complaint).
 * Renders the escalation banner (latest reason of the active stage) plus the
 * assignee-only Extend action, so both stay in sync across the three detail pages
 * and never drift. Renders nothing useful when there is no active tracker.
 *
 * Gating for Extend (PLAN-sla-extend-deadline UAC-1):
 *   unresolved AND has a resolution deadline AND current user is the assignee AND
 *   no pending takeover. Assignee-equality uses `assigned_to_id` from the active
 *   tracker vs the session user id.
 */
export function SlaActiveTrackerControls({
  activeTracker,
  label,
  onExtended,
}: {
  activeTracker: ConversationSLATrackingDetail | null | undefined;
  label?: string;
  onExtended?: () => void;
}) {
  const { data: session } = useSession();
  const currentUserId = session?.user?.id ?? null;

  if (!activeTracker) return null;

  const resolutionDue =
    activeTracker.due_at_resolution ?? activeTracker.resolution_due_at ?? null;
  const dueIso =
    resolutionDue == null
      ? null
      : resolutionDue instanceof Date
        ? resolutionDue.toISOString()
        : String(resolutionDue);

  const isAssignee =
    !!currentUserId &&
    !!activeTracker.assigned_to_id &&
    String(activeTracker.assigned_to_id) === String(currentUserId);

  return (
    <div className="space-y-2">
      <SlaEscalationBanner
        reason={activeTracker.escalation_reason}
        tier={activeTracker.current_tier}
        assignee={activeTracker.assigned_user_name}
      />
      <ExtendDueButton
        trackingId={activeTracker.id}
        currentDueAt={dueIso}
        isResolved={!!activeTracker.is_resolved}
        isAssignee={isAssignee}
        unknownDuePolicy="require"
        label={label}
        onExtended={onExtended}
        variant="outline"
      />
    </div>
  );
}
