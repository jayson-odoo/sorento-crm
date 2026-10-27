'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuditLogs } from '@/hooks/useAuditLogs';
import { actorDisplay } from '@/lib/audit-actor';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  auditFieldChanges,
  auditFieldLabel,
  formatAuditValue,
  isAuditResubmit,
  type AuditFieldChange,
} from '@/lib/audit-fields';
import type { AuditLogEntry } from '@/types/audit.types';

// The backend summarises a status move ("status: rejected → submitted"); that line leads,
// so the raw field it already describes is not listed a second time.
const STATUS_SUMMARY_KEYS = ['status', 'approval_status', 'order_status'];

function summaryCovers(change: AuditFieldChange, entry: AuditLogEntry, summary: string): boolean {
  if (change.key === 'status_id') return true;
  if (!STATUS_SUMMARY_KEYS.includes(change.key)) return false;
  return summary.endsWith(`→ ${formatAuditValue(entry.new_values?.[change.key])}`);
}

type ChangeLine = { text: string } | { label: string; before: string; after: string };

/**
 * What one audit row changed, one line per field. An empty list means the row changed
 * nothing a reader can see (only bookkeeping fields), and the row is not shown.
 * `childName` is set for a child row (a product line on its complaint's trail).
 */
function collectChangeLines(entry: AuditLogEntry, childName: string | null): ChangeLine[] {
  if (entry.action === 'INSERT') return [{ text: childName ? `${childName} added` : 'Record created' }];
  if (entry.action === 'DELETE') return [{ text: childName ? `${childName} removed` : 'Record deleted' }];
  const summary = entry.description?.trim() || '';
  if (entry.action !== 'UPDATE') return [{ text: summary || entry.action }];
  const prefix = childName ? `${childName}: ` : '';
  const lines: ChangeLine[] = summary ? [{ text: `${prefix}${summary}` }] : [];
  for (const change of auditFieldChanges(entry.old_values, entry.new_values)) {
    if (summary && summaryCovers(change, entry, summary)) continue;
    lines.push(
      change.kind === 'line'
        ? { text: `${prefix}${change.text}` }
        : { label: `${prefix}${change.label}`, before: change.before, after: change.after },
    );
  }
  return lines;
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

  const rows = (data?.data ?? [])
    .map((entry) => {
      const isChild = entry.entity_type !== entityType || entry.entity_id !== entityId;
      const childName = isChild ? entry.entity_label || auditFieldLabel(entry.entity_type) : null;
      return { entry, lines: collectChangeLines(entry, childName) };
    })
    .filter((row) => row.lines.length > 0);
  const empty = rows.length === 0;

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
            {rows.map(({ entry, lines }) => (
              <li
                key={entry.id}
                data-audit-entry="1"
                className="border-b border-border/50 pb-3 last:border-0 last:pb-0"
              >
                <div className="flex flex-wrap items-baseline gap-2 text-sm">
                  <span data-testid="audit-action" className="font-medium capitalize">
                    {isAuditResubmit(entry) ? 'Resubmitted' : entry.action.toLowerCase()}
                  </span>
                  <span className="text-muted-foreground">
                    {formatDateTimeInMalaysia(entry.changed_at)}
                  </span>
                  <span className="text-muted-foreground">by {actorDisplay(entry)}</span>
                </div>
                <ul className="mt-1.5 list-none space-y-1.5 text-sm text-muted-foreground">
                  {lines.map((line, idx) => (
                    <li
                      key={idx}
                      data-testid="audit-change-line"
                      className="break-words border-l-2 border-border/50 pl-2"
                    >
                      {'text' in line ? (
                        line.text
                      ) : (
                        <details>
                          <summary className="cursor-pointer">{line.label} changed</summary>
                          <div className="mt-1 space-y-1">
                            <div className="text-xs font-medium">Before</div>
                            <p data-testid="audit-before" className="whitespace-pre-wrap">
                              {line.before}
                            </p>
                            <div className="text-xs font-medium">After</div>
                            <p data-testid="audit-after" className="whitespace-pre-wrap text-foreground">
                              {line.after}
                            </p>
                          </div>
                        </details>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
