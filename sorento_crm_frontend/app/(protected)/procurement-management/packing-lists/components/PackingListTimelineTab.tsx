'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { AuditLog } from '@/app/(protected)/system-management/audit-logs/types/auditLog.types';
import ClearanceDeliveryCard from './ClearanceDeliveryCard';
import { usePackingListRecord } from '../[id]/components/packing-list-context';
import { usePackingListHistory } from '../hooks/usePackingLists';

/**
 * How far the container has got, checkpoint by checkpoint, and what has been done to it.
 *
 * The "Origin" card that used to sit above this is gone: where a container came from is a
 * whole tab of its own now (Proforma invoices), and a one-line summary of it here was the
 * only place on the page that answered the question in a sentence rather than in figures.
 *
 * History is the audit trail (R17). A conversion pushed past the container's planned volume
 * writes its reason here as an entry - "Converted over capacity: ... Reason: ..." - rather
 * than into Notes, which is the operator's own field and was being filled with a sentence
 * nobody typed.
 */
export function PackingListTimelineTab() {
  const { packingList, packingListId } = usePackingListRecord();
  const history = usePackingListHistory(packingListId);
  if (!packingList) return null;

  const entries = history.data?.data ?? [];

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Clearance &amp; Delivery</CardTitle>
        </CardHeader>
        <CardContent>
          <ClearanceDeliveryCard packingList={packingList} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent>
          {history.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-5 w-1/2" />
            </div>
          ) : history.isError ? (
            <p className="text-sm text-muted-foreground">
              {history.error instanceof Error
                ? history.error.message
                : 'Failed to load this container history.'}
            </p>
          ) : entries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing has been recorded against this container yet.
            </p>
          ) : (
            <ul className="space-y-3">
              {entries.map((entry) => (
                <li
                  key={entry.id}
                  className="flex flex-col gap-0.5 border-b pb-3 last:border-0 last:pb-0"
                >
                  <span className="text-sm break-words">{entryText(entry)}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTimeInMalaysia(entry.changed_at)}
                    {entry.user_display_name ? ` · ${entry.user_display_name}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** The stored sentence where the write left one, else what kind of change it was. */
function entryText(entry: AuditLog): string {
  if (entry.description) return entry.description;
  switch (entry.action) {
    case 'CREATE':
    case 'INSERT':
      return 'Container created';
    case 'DELETE':
      return 'Container deleted';
    default:
      return 'Container updated';
  }
}

export default PackingListTimelineTab;
