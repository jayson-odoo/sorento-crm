'use client';

/**
 * The Access Agents action set (D15): Delete.
 *
 * Edit is the record page's primary button (a modal) and the row click opens the
 * record, so neither belongs in the menu.
 */

import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import type { AccessAgent } from './types/accessAgent.types';

export interface UseAccessAgentActionsOptions {
  onDeleted?: () => void;
  /**
   * The record page shows the countdown in place of its primary button; a list
   * row has nowhere to put one, so it travels to a toast (S6-06, S6-07).
   */
  surface?: 'inline' | 'toast';
}

export function useAccessAgentActions(
  accessAgent: AccessAgent | undefined | null,
  { onDeleted, surface = 'inline' }: UseAccessAgentActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('user_management.access_agents.delete');

  // Delete asks nothing (D7): the countdown takes the primary button's place on
  // the record, or the toast's on a list row, and Cancel is the way back.
  const deletion = useDeferredAction({
    actionKey: 'access_agent.delete',
    entityType: 'access_agent',
    entityId: accessAgent?.id,
    verb: 'Deleting',
    subject: accessAgent ? `${accessAgent.name} (${accessAgent.code})` : '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Access agent deleted',
    invalidateKeys: [['access-agents']],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!accessAgent) return { actions, dialogs: null, pending: null };

  if (canDelete) {
    actions.push({
      key: 'access_agent.delete',
      label: 'Delete access agent',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    });
  }

  return { actions, dialogs: null, pending: deletion.countdown };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function AccessAgentRowActions({ accessAgent }: { accessAgent: AccessAgent }) {
  const { actions } = useAccessAgentActions(accessAgent, { surface: 'toast' });

  if (actions.length === 0) return null;

  return <RowActionsMenu actions={actions} ariaLabel="access agent" />;
}
