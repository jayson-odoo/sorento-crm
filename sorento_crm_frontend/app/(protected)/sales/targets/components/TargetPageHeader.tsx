'use client';

import { PageHeader } from '@/components/common/PageHeader';
import BackToList, { useBackToListHref } from '@/components/common/BackToList';
import { useSalesTarget } from '../hooks/useSalesTargets';

/**
 * The target record's page header (owner, 5 Nov: "if I am at dealer target, then I go back
 * should go back to dealer target tab"). Back to targets and the Targets crumb open the list
 * on the tab the record belongs to, its subject kind, so a direct link returns there too. The
 * list state the row click handed over rides along (`useBackToListHref`), the same way the
 * quotation page names its project tab (`project-sales/[projectId]/quotations/[quotationId]`).
 */
export default function TargetPageHeader({ id }: { id: string }) {
  const { data: target } = useSalesTarget(id);
  const listPath = target ? `/sales/targets?tab=${target.subject_kind}` : '/sales/targets';
  const listHref = useBackToListHref(listPath);
  return (
    <PageHeader
      title="Target"
      crumbs={[{ title: 'Sales' }, { title: 'Targets', path: listHref }, { title: 'Target' }]}
      actions={<BackToList listPath={listPath} label="Back to targets" />}
    />
  );
}
