'use client';

import { CalendarClock } from 'lucide-react';

import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useEffectiveUserId } from '@/hooks/useEffectiveUserId';
import type { ConversationSLATrackingDetail } from '@/app/(protected)/sla-management/conversation-sla-tracking/types/conversationSLATracking.types';
import ExtendDueDialog from '@/app/(protected)/sla-management/conversation-sla-tracking/components/ExtendDueDialog';

const EXTEND_PERM = 'sla_management.conversation_sla_tracking.extend';

/** Naive-UTC ISO resolution due for the active tracker (tz-safe, no Date round-trip). */
function resolutionDueIso(t: ConversationSLATrackingDetail): string | null {
  const due = t.due_at_resolution ?? t.resolution_due_at ?? null;
  if (due == null) return null;
  return due instanceof Date ? due.toISOString() : String(due);
}

/** Gear-dropdown item that opens the Extend SLA dialog. Extend is ASSIGNEE-ONLY
 * (consistent with conversation SLA): visible only when there is an active, unresolved
 * tracker, the user holds the extend permission, AND the user is the tracker's current
 * assignee. The backend enforces the same assignee-only rule (see _assert_can_extend),
 * so a non-assignee never sees a button that would 403. Reuses the SAME extend flow as
 * conversation SLA. Render inside the form's actions DropdownMenu, next to "Escalate SLA". */
export function SlaExtendMenuItem({
  activeTracker,
  onSelect,
}: {
  activeTracker: ConversationSLATrackingDetail | null | undefined;
  onSelect: () => void;
}) {
  const canExtend = useHasPermission(EXTEND_PERM);
  // Impersonation-aware: the acting user, not the NextAuth session user (which stays
  // the admin while impersonating). Otherwise the assignee gate is wrong all session.
  const currentUserId = useEffectiveUserId();
  const isAssignee =
    !!currentUserId &&
    !!activeTracker?.assigned_to_id &&
    String(activeTracker.assigned_to_id) === String(currentUserId);
  if (!activeTracker || activeTracker.is_resolved || !canExtend || !isAssignee) return null;
  return (
    <DropdownMenuItem
      onSelect={(e) => {
        e.preventDefault();
        onSelect();
      }}
    >
      <CalendarClock className="size-4" />
      Extend SLA
    </DropdownMenuItem>
  );
}

/** The controlled Extend dialog for a form entity - render as a sibling of the gear
 * menu (a dialog inside DropdownMenuContent would unmount on close). Wraps the shared
 * ExtendDueDialog, seeding it with the active tracker's resolution due + a label. */
export function SlaExtendDialog({
  activeTracker,
  label,
  open,
  onOpenChange,
  onExtended,
}: {
  activeTracker: ConversationSLATrackingDetail | null | undefined;
  label?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onExtended?: () => void;
}) {
  if (!activeTracker) return null;
  return (
    <ExtendDueDialog
      open={open}
      onOpenChange={onOpenChange}
      trackingId={activeTracker.id}
      currentDueAt={resolutionDueIso(activeTracker)}
      label={label}
      onExtended={onExtended}
    />
  );
}
