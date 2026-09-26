'use client';

/**
 * The Sales Opportunities action set (Phase 3 fix B2): Delete.
 *
 * Same shape as `sales/teams/actions.tsx`: Delete asks nothing (D7). It parks
 * `sales_opportunity.delete` on the server for the hard-delete window and the countdown takes
 * over the primary button, or a toast over the list.
 */

import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { SALES_OPPORTUNITIES_KEY, SALES_OPPORTUNITY_KEY } from './hooks/useSalesOpportunities';

interface OpportunityRef {
  id: string;
  title: string;
}

export interface UseSalesOpportunityActionsOptions {
  onDeleted?: () => void;
  surface?: 'inline' | 'toast';
}

export function useSalesOpportunityActions(
  opportunity: OpportunityRef | undefined | null,
  { onDeleted, surface = 'inline' }: UseSalesOpportunityActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('sales.opportunities.delete');

  const deletion = useDeferredAction({
    actionKey: 'sales_opportunity.delete',
    entityType: 'sales_opportunity',
    entityId: opportunity?.id,
    verb: 'Deleting',
    subject: opportunity?.title ?? '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Sales opportunity deleted',
    invalidateKeys: [SALES_OPPORTUNITIES_KEY, SALES_OPPORTUNITY_KEY],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!opportunity) return { actions, dialogs: null, pending: null };

  if (canDelete) {
    actions.push({
      key: 'sales_opportunity.delete',
      label: 'Delete opportunity',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    });
  }

  return { actions, dialogs: null, pending: deletion.countdown };
}

/** The list row's "..." cell - the same items the opportunity page's gear shows. */
export function SalesOpportunityRowActions({ opportunity }: { opportunity: OpportunityRef }) {
  const { actions } = useSalesOpportunityActions(opportunity, { surface: 'toast' });
  if (actions.length === 0) return null;
  return <RowActionsMenu actions={actions} ariaLabel="sales opportunity" />;
}
