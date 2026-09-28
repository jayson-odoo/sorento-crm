'use client';

import { Button } from '@/components/ui/button';
import { useApplyCostPriceChangeSet, useSubmitCostPriceChangeSet } from '../../hooks/useCostPriceChangeSets';
import type { CostPriceChangeSetDetail } from '../../types/costPrice.types';

/**
 * With the setting on, a staff draft always goes through Submit, never straight to Apply
 * (AC-S2-04) - driven by the set's own workflow, not by whether Submit happens to be
 * enabled right now, so a blocked draft still shows Submit (disabled) rather than silently
 * falling back to the Apply button verification-off sets use.
 */
export function isSubmitWorkflow(changeSet: CostPriceChangeSetDetail): boolean {
  return changeSet.verification_enabled && changeSet.status === 'draft' && changeSet.channel === 'staff_upload';
}

/**
 * The set's one call to action: "Apply N changes", or "Submit for verification" on the
 * submit workflow. Driven only by `actions` from the detail (contract 1.4) - the FE never
 * re-derives the four-eyes rule. The page header (round 6 R1, primary top right) renders
 * it; round 7 R1 removed the sticky footer bar, so this is the page's one Apply.
 */
export function CostPriceApplyButton({ changeSet }: { changeSet: CostPriceChangeSetDetail }) {
  const submit = useSubmitCostPriceChangeSet(changeSet.id);
  const apply = useApplyCostPriceChangeSet(changeSet.id);
  const actions = changeSet.actions;

  if (changeSet.status === 'applied') return null;
  if (isSubmitWorkflow(changeSet)) {
    return (
      <Button
        onClick={() => void submit.mutateAsync()}
        disabled={!actions.can_submit || submit.isPending}
        title={actions.apply_blocked_reason ?? undefined}
      >
        Submit for verification
      </Button>
    );
  }
  return (
    <Button
      onClick={() => void apply.mutateAsync()}
      disabled={!actions.can_apply || apply.isPending}
      title={actions.apply_blocked_reason ?? undefined}
    >
      Apply {actions.apply_count} {actions.apply_count === 1 ? 'change' : 'changes'}
    </Button>
  );
}

export default CostPriceApplyButton;
