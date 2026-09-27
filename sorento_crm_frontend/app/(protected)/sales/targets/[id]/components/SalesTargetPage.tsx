'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { useHasPermission } from '@/hooks/usePermissions';
import { todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import { useSalesTarget, useSalesTargets } from '../../hooks/useSalesTargets';
import { useSalesTargetActions } from '../../actions';
import { SalesTargetDetail } from './SalesTargetDetail';

/**
 * The target page's access and header actions (S1-23): what the reader may do (the
 * `sales.targets.*` slugs), Duplicate (a header button beside Edit), the deferred Delete in
 * the row menu, and prev/next across the targets of the same kind active today, the list the
 * reader came from. The form itself is `SalesTargetDetail`.
 */
export function SalesTargetPage({ id }: { id: string }) {
  const router = useRouter();
  const canEdit = useHasPermission('sales.targets.edit');
  const canOpenAgent = useHasPermission('master_data.sales_agents.view');
  const { data: target } = useSalesTarget(id);
  const { actions, pending, duplicateButton } = useSalesTargetActions(target, {
    onDeleted: () => router.push('/sales/targets'),
  });
  const { data: list } = useSalesTargets(
    { on: todayMalaysiaYyyyMmDd(), subject: target?.subject_kind ?? 'agent' },
    !!target,
  );

  const ids = useMemo(() => {
    const seen: string[] = [];
    for (const row of list?.rows ?? []) {
      if (row.target_id && !seen.includes(row.target_id))
        seen.push(row.target_id);
    }
    return seen;
  }, [list]);
  const index = ids.indexOf(id);

  return (
    <SalesTargetDetail
      id={id}
      readOnly={!canEdit}
      canOpenAgent={canOpenAgent}
      actions={actions}
      pendingAction={pending}
      secondary={duplicateButton}
      pager={
        <RecordNavigation
          index={index >= 0 ? index + 1 : null}
          total={ids.length}
          hasPrevious={index > 0}
          hasNext={index >= 0 && index < ids.length - 1}
          onPrevious={() => router.push(`/sales/targets/${ids[index - 1]}`)}
          onNext={() => router.push(`/sales/targets/${ids[index + 1]}`)}
          ariaLabel="target"
        />
      }
    />
  );
}
