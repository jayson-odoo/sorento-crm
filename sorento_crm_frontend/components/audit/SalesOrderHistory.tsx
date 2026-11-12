'use client';

import * as React from 'react';
import AuditTrail from '@/components/audit/AuditTrail';
import { useSalesOrderHistory } from '@/hooks/useSalesOrderHistory';

/**
 * STANDARD-HISTORY wave 2 (AC-SH-W2-6): one sales order's history in the ONE history
 * component, for the SCM page (`source="scm"`, the core SO id), the project page and the
 * fulfilment board (`source="project"`, the project SO id).
 */
export default function SalesOrderHistory({
  source,
  id,
}: {
  source: 'project' | 'scm';
  id: string | undefined;
}) {
  const history = useSalesOrderHistory(source, id);
  return (
    <AuditTrail
      title="History"
      entries={history.data?.events ?? []}
      isLoading={history.isLoading}
      isError={history.isError}
      onRetry={() => void history.refetch()}
    />
  );
}
