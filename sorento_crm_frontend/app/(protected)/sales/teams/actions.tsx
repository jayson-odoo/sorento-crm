'use client';

/**
 * The Sales Teams action set (D15): Delete.
 *
 * Edit is the team page's primary button and the list's row click opens the team, so
 * neither belongs in this menu. Delete asks nothing (D7): it parks `sales_team.delete` on the
 * server for the hard-delete window and the countdown takes over the primary button, or a
 * toast over the list. The agents themselves are never deleted with a team (UAC S6-3).
 */

import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';

interface TeamRef {
  id: string;
  name: string;
}

export interface UseSalesTeamActionsOptions {
  onDeleted?: () => void;
  surface?: 'inline' | 'toast';
}

export function useSalesTeamActions(
  team: TeamRef | undefined | null,
  { onDeleted, surface = 'inline' }: UseSalesTeamActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('sales.teams.delete');

  const deletion = useDeferredAction({
    actionKey: 'sales_team.delete',
    entityType: 'sales_team',
    entityId: team?.id,
    verb: 'Deleting',
    subject: team?.name ?? '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Sales team deleted',
    invalidateKeys: [['sales-teams'], ['sales-team-agent-options']],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!team) return { actions, dialogs: null, pending: null };

  if (canDelete) {
    actions.push({
      key: 'sales_team.delete',
      label: 'Delete team',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    });
  }

  return { actions, dialogs: null, pending: deletion.countdown };
}

/** The list row's "..." cell - the same items the team page's gear shows. */
export function SalesTeamRowActions({ team }: { team: TeamRef }) {
  const { actions } = useSalesTeamActions(team, { surface: 'toast' });
  if (actions.length === 0) return null;
  return <RowActionsMenu actions={actions} ariaLabel="sales team" />;
}
