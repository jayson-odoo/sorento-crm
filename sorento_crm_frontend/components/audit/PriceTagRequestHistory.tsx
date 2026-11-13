'use client';

import * as React from 'react';
import AuditTrail from '@/components/audit/AuditTrail';
import { usePriceTagRequestHistory } from '@/hooks/usePriceTagRequestHistory';

/**
 * STANDARD-HISTORY wave 5 (AC-W5-5): one price tag request's history in the ONE history
 * component, for the CRM request page's History tab.
 */
export default function PriceTagRequestHistory({ requestId }: { requestId: string | undefined }) {
  const history = usePriceTagRequestHistory(requestId);
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
