'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuditLogs } from '@/hooks/useAuditLogs';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { AuditLogEntry } from '@/types/audit.types';

function formatChangeSummary(entry: AuditLogEntry): string {
  if (entry.action === 'INSERT') return 'Record created';
  if (entry.action === 'DELETE') return 'Record deleted';
  if (entry.action === 'UPDATE') {
    if (entry.description) return entry.description;
    const oldV = entry.old_values || {};
    const newV = entry.new_values || {};
    const keys = new Set([...Object.keys(oldV), ...Object.keys(newV)]);
    const changes: string[] = [];
    keys.forEach((key) => {
      const ov = oldV[key];
      const nv = newV[key];
      if (ov !== nv && (ov !== undefined || nv !== undefined)) {
        changes.push(`${key}: ${ov ?? '—'} → ${nv ?? '—'}`);
      }
    });
    if (changes.length === 0) return 'Updated';
    return changes.slice(0, 5).join('; ') + (changes.length > 5 ? '…' : '');
  }
  return entry.action;
}

interface AuditTrailProps {
  entityType: string;
  entityId: string;
  title?: string;
}

export default function AuditTrail({ entityType, entityId, title = 'Audit Trail' }: AuditTrailProps) {
  const { data, isLoading } = useAuditLogs(entityType, entityId);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }

  const entries = data?.data ?? [];
  const empty = data?.empty ?? true;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {empty ? (
          <p className="text-sm text-muted-foreground">No audit history for this record.</p>
        ) : (
          <ul className="space-y-4">
            {entries.map((entry) => (
              <li key={entry.id} className="border-b border-border/50 pb-3 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-baseline gap-2 text-sm">
                  <span className="font-medium capitalize">{entry.action.toLowerCase()}</span>
                  <span className="text-muted-foreground">
                    {formatDateTimeInMalaysia(entry.changed_at)}
                  </span>
                  {(entry.user_id && entry.user_id !== 'system') && (
                    <span className="text-muted-foreground">
                      by {entry.user_display_name ?? entry.user_id}
                    </span>
                  )}
                  {entry.user_id === 'system' && (
                    <span className="text-muted-foreground">by System</span>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {formatChangeSummary(entry)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
