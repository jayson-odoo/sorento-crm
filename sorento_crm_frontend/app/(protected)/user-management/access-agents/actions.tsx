'use client';

/**
 * The Access Agents action set (D15): Delete.
 *
 * Edit is the record page's primary button (a modal) and the row click opens the
 * record, so neither belongs in the menu.
 */

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import type { AccessAgent } from './types/accessAgent.types';
import AccessAgentDeleteDialog from './components/access-agent-delete-dialog';

export interface UseAccessAgentActionsOptions {
  onDeleted?: () => void;
}

export function useAccessAgentActions(
  accessAgent: AccessAgent | undefined | null,
  { onDeleted }: UseAccessAgentActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('user_management.access_agents.delete');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!accessAgent) return { actions, dialogs: null };

  if (canDelete) {
    actions.push({
      key: 'access_agent.delete',
      label: 'Delete access agent',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const dialogs = (
    <AccessAgentDeleteDialog
      open={deleteOpen}
      closeDialog={() => setDeleteOpen(false)}
      accessAgent={accessAgent}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function AccessAgentRowActions({ accessAgent }: { accessAgent: AccessAgent }) {
  const { actions, dialogs } = useAccessAgentActions(accessAgent);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="access agent" />
      {dialogs}
    </>
  );
}
