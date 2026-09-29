'use client';

import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useCostPriceChangeSetHistory } from '../../hooks/useCostPriceChangeSets';

const ACTION_LABELS: Record<string, string> = {
  COST_SET_UPLOAD: 'Uploaded',
  COST_SET_SUBMIT: 'Submitted for verification',
  COST_SET_RETURN: 'Returned to submitter',
  COST_SET_APPLY: 'Applied',
  COST_LINE_MAP: 'Mapped a line',
  COST_LINE_SKIP: 'Skipped a line',
  COST_LINE_DECISION: 'Decided a line',
};

/** No action code ever reaches the screen; an action added later reads as a plain update. */
const actionLabel = (action: string) => ACTION_LABELS[action] ?? 'Updated';

/** AC-AU-04: newest first, actor, time, one-line summary. */
export function CostPriceHistoryTab({ setId }: { setId: string }) {
  const { data, isLoading } = useCostPriceChangeSetHistory(setId);
  const events = data?.data ?? [];

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <Card>
        <div className="p-8 text-center text-sm text-muted-foreground">Nothing recorded yet.</div>
      </Card>
    );
  }

  return (
    <ol className="space-y-2">
      {events.map((event, index) => (
        <li key={`${event.action}-${event.at}-${index}`} className="rounded-lg border border-border bg-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">{actionLabel(event.action)}</span>
            <span className="text-xs text-muted-foreground">{formatDateTimeInMalaysia(event.at)}</span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{event.summary}</p>
          <p className="mt-1 text-xs text-muted-foreground">{event.actor_name}</p>
        </li>
      ))}
    </ol>
  );
}

export default CostPriceHistoryTab;
