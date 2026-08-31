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

import { ExternalLink, Trash2, UserRound } from 'lucide-react';

import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useSyncAssigneeFromRespond } from './hooks/useConversationSLATracking';

/** What both surfaces can hand over: a list row carries exactly this much. */
const RESPOND_IO_INBOX_BASE_URL = 'https://app.respond.io/space/364817/inbox';

export interface ConversationSlaActionTarget {
  id: string;
  respond_io_id?: string | null;
  contact?: { respond_io_id?: string | null } | null;
  contact_name?: string | null;
  contact_phone?: string | null;
}

export interface UseConversationSlaActionsOptions {
  /** Where to go once the tracking is gone (the record page returns to the list). */
  onDeleted?: () => void;
  /**
   * The record page shows the countdown in place of its primary button; a list
   * row has nowhere to put one, so it travels to a toast (S6-06, S6-07).
   */
  surface?: 'inline' | 'toast';
}

export function useConversationSlaActions(
  tracking: ConversationSlaActionTarget | null | undefined,
  { onDeleted, surface = 'inline' }: UseConversationSlaActionsOptions = {},
): RecordActionSet {
  const syncAssignee = useSyncAssigneeFromRespond();

  // The reader's identifier for the record: the contact's name, falling back to
  // their phone number, and only "this tracking record" when Respond.io has
  // resolved neither (a bare id would violate the no-UUIDs-in-UI rule).
  const subject = tracking?.contact_name || tracking?.contact_phone || 'this tracking record';

  // Delete asks nothing (D7). It parks the deletion for ten seconds; the record
  // page shows the countdown where its primary button stood, a list row leaves
  // it to the toast, and Cancel is the way back either way.
  const deletion = useDeferredAction({
    actionKey: 'sla_tracking.delete',
    entityType: 'sla_tracking',
    entityId: tracking?.id,
    verb: 'Deleting',
    subject,
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Tracking deleted',
    // The dashboard counts these records, so it is stale the moment one goes. The
    // immediate mutation refetched both.
    invalidateKeys: [['conversation-sla-tracking'], ['sla-tracking-dashboard-metrics']],
    onCommitted: onDeleted,
  });

  if (!tracking) return { actions: [], dialogs: null, pending: null };

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
      run: () => {
        window.open(inboxUrl, '_blank', 'noopener,noreferrer');
      },
    });
  }

  actions.push({
    key: 'conversation_sla.delete',
    label: 'Delete tracking',
    icon: Trash2,
    kind: 'destructive',
    disabled: deletion.isPending,
    run: deletion.start,
  });

  return { actions, dialogs: null, pending: deletion.countdown };
}
