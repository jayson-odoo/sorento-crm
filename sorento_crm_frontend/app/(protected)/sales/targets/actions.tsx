'use client';

/**
 * The target record's actions (D15, S1-23): Duplicate, then Delete, in the gear dropdown.
 *
 * The record adds Edit ahead of these (the S1 hand test of 27 Sep, F2 and F4: Edit lives in
 * the gear, beside the pager, never as a button of its own). Delete asks nothing
 * (D7): it parks `sales_target.delete` on the server for the hard-delete window and the
 * countdown takes over the primary button. A team target's children go with it (FK cascade),
 * so the countdown names them: "Deleting North FY26 H2 and 2 agent targets" (plan 3.8).
 */

import { useRouter } from 'next/navigation';
import { Copy, Trash2 } from 'lucide-react';
import type {
  RecordAction,
  RecordActionSet,
} from '@/components/common/recordActions';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useDuplicateSalesTarget } from './hooks/useSalesTargets';

interface TargetRef {
  id: string;
  name: string;
  child_count: number;
}

/** "North FY26 H2 and 2 agent targets", or the name alone. */
export function deleteSubject(target: TargetRef): string {
  if (!target.child_count) return target.name;
  const noun = target.child_count === 1 ? 'agent target' : 'agent targets';
  return `${target.name} and ${target.child_count} ${noun}`;
}

export function useSalesTargetActions(
  target: TargetRef | undefined | null,
  { onDeleted }: { onDeleted?: () => void } = {},
): RecordActionSet {
  const router = useRouter();
  const canEdit = useHasPermission('sales.targets.edit');
  const canDelete = useHasPermission('sales.targets.delete');
  const duplicate = useDuplicateSalesTarget();

  const deletion = useDeferredAction({
    actionKey: 'sales_target.delete',
    entityType: 'sales_target',
    entityId: target?.id,
    verb: 'Deleting',
    subject: target ? deleteSubject(target) : '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Target deleted',
    invalidateKeys: [['sales-targets'], ['sales-target'], ['sales-teams']],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!target) return { actions, dialogs: null, pending: null };

  const runDuplicate = async () => {
    try {
      const copy = await duplicate.mutateAsync(target.id);
      router.push(`/sales/targets/${copy.id}`);
    } catch {
      // The hook toasted the reason; the page stays on the source target.
    }
  };
  // Hidden while a delete counts down: the record on its way out offers only Cancel.
  if (canEdit && !deletion.countdown) {
    actions.push({
      key: 'sales_target.duplicate',
      label: 'Duplicate',
      icon: Copy,
      disabled: duplicate.isPending,
      run: runDuplicate,
    });
  }

  if (canDelete) {
    actions.push({
      key: 'sales_target.delete',
      label: 'Delete target',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    });
  }

  return {
    actions,
    dialogs: null,
    pending: deletion.countdown,
  };
}
