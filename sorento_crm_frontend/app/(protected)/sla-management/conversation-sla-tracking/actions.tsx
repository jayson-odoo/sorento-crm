'use client';

/**
 * The Conversation SLA Tracking action set (D15).
 *
 * These are the actions that need nothing but the row: its id, and the
 * Respond.io contact it belongs to. Both the list row's "..." and the record's
 * gear render them, in this order, so an action cannot be reachable from one
 * surface and missing from the other.
 *
 * The record's gear carries MORE than this, and deliberately: escalate, the test
 * overrides, mark responded/resolved and reopen all read the fetched tracking
 * (its tier, whether it is responded, what the policy allows) and drive dialogs
 * that live on that page. A list row holds none of that, so those verbs stay
 * where the data is.
 */

import { useState } from 'react';
import { ExternalLink, Trash2, UserRound } from 'lucide-react';

import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import {
  useDeleteConversationSLATracking,
  useSyncAssigneeFromRespond,
} from './hooks/useConversationSLATracking';

/** What both surfaces can hand over: a list row carries exactly this much. */
const RESPOND_IO_INBOX_BASE_URL = 'https://app.respond.io/space/364817/inbox';

export interface ConversationSlaActionTarget {
  id: string;
  respond_io_id?: string | null;
  contact?: { respond_io_id?: string | null } | null;
}

export interface UseConversationSlaActionsOptions {
  /** Where to go once the tracking is gone (the record page returns to the list). */
  onDeleted?: () => void;
}

export function useConversationSlaActions(
  tracking: ConversationSlaActionTarget | null | undefined,
  { onDeleted }: UseConversationSlaActionsOptions = {},
): RecordActionSet {
  const syncAssignee = useSyncAssigneeFromRespond();
  const remove = useDeleteConversationSLATracking();
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (!tracking) return { actions: [] };

  const respondIoId = tracking.respond_io_id ?? tracking.contact?.respond_io_id ?? null;
  const inboxUrl = respondIoId ? `${RESPOND_IO_INBOX_BASE_URL}/${respondIoId}` : null;

  const actions: RecordAction[] = [
    {
      key: 'conversation_sla.sync_assignee',
      label: 'Sync assignee',
      icon: UserRound,
      disabled: syncAssignee.isPending,
      run: () => syncAssignee.mutate(tracking.id),
    },
  ];

  if (inboxUrl) {
    actions.push({
      key: 'conversation_sla.open_conversation',
      label: 'Open conversation',
      icon: ExternalLink,
      run: () => window.open(inboxUrl, '_blank', 'noopener,noreferrer'),
    });
  }

  actions.push({
    key: 'conversation_sla.delete',
    label: 'Delete tracking',
    icon: Trash2,
    kind: 'destructive',
    disabled: remove.isPending,
    run: () => setDeleteOpen(true),
  });

  const dialogs = (
    <ConfirmDeleteDialog
      open={deleteOpen}
      onOpenChange={setDeleteOpen}
      title="Delete conversation SLA tracking"
      description="This deletes the tracking record and its event log. This action cannot be undone."
      successMessage="Tracking deleted"
      onDelete={async () => {
        await remove.mutateAsync(tracking.id);
      }}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}
