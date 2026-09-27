'use client';

/**
 * The Sales Opportunities action set (Phase 3 fix B2; fix round 2 F6): the stage moves named
 * by `available_transitions`, then Delete (D7).
 *
 * A stage item runs immediately (Qualify, say) or opens the lost/won dialog the detail page
 * owns - `onTransition` is how the caller tells the two apart. This hook only decides WHETHER
 * the items render (`canEdit`) and WHERE they sit (before Delete); the dialog and the fields
 * it needs (lost reasons, the sales-order picker) stay on the detail page that already holds
 * that data.
 */

import { ArrowRight, Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { SALES_OPPORTUNITIES_KEY, SALES_OPPORTUNITY_KEY } from './hooks/useSalesOpportunities';
import type { SalesOpportunityTransition } from './types/salesOpportunity.types';

interface OpportunityRef {
  id: string;
  title: string;
}

export interface UseSalesOpportunityActionsOptions {
  onDeleted?: () => void;
  surface?: 'inline' | 'toast';
  /** The stage moves offered right now (F6) - rendered as secondary gear items, before
   *  Delete. Pass `[]` (the default) to offer none, e.g. without edit permission. */
  transitions?: SalesOpportunityTransition[];
  /** Runs a stage move. The caller decides by `transition.key`: Lost/Won open a dialog
   *  first, anything else (Qualify) fires straight away. */
  onTransition?: (transition: SalesOpportunityTransition) => void;
  /** Disables the stage items while an edit session is open. */
  transitionsDisabled?: boolean;
}

export function useSalesOpportunityActions(
  opportunity: OpportunityRef | undefined | null,
  {
    onDeleted,
    surface = 'inline',
    transitions = [],
    onTransition,
    transitionsDisabled,
  }: UseSalesOpportunityActionsOptions = {},
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

  transitions.forEach((transition) => {
    actions.push({
      key: `sales_opportunity.stage.${transition.to_status_id}`,
      label: transition.label,
      icon: ArrowRight,
      kind: 'secondary',
      disabled: transitionsDisabled,
      run: () => onTransition?.(transition),
    });
  });

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
