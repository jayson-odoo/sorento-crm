'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuditLogs } from '@/hooks/useAuditLogs';
import { actorDisplay } from '@/lib/audit-actor';
import { appealWording } from '@/lib/submission-status';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  auditFieldChanges,
  auditFieldLabel,
  formatAuditValue,
  auditTrailHeadings,
  resubmittedSummary,
  type AuditFieldChange,
  type AuditTrailHeading,
} from '@/lib/audit-fields';
import type { AuditLogEntry } from '@/types/audit.types';

// The backend summarises a status move ("status: rejected → submitted"); that line leads,
// so the raw field it already describes is not listed a second time.
const STATUS_SUMMARY_KEYS = ['status', 'approval_status', 'order_status'];

function summaryCovers(change: AuditFieldChange, entry: AuditLogEntry, summary: string): boolean {
  // The status-engine summary names the labels: "Status: Draft → Submitted".
  if (change.key === 'status_id') return /^Status(:| changed to)/.test(summary);
  if (!STATUS_SUMMARY_KEYS.includes(change.key)) return false;
  const to = entry.new_values?.[change.key];
  // The backend prints a cleared value as "None".
  return summary.endsWith(`→ ${to == null ? 'None' : formatAuditValue(to)}`);
}

type ChangeLine = { text: string } | { label: string; before: string; after: string };

/**
 * What one audit row changed, one line per field. An empty list means the row changed
 * nothing a reader can see (only bookkeeping fields), and the row is not shown.
 * `childName` is set for a child row (a product line on its complaint's trail).
 * `own` is set for the record's own row: its status lines say appealed, not resubmitted
 * (owner, 28 Oct 2026, every form).
 */
function collectChangeLines(
  entry: AuditLogEntry,
  childName: string | null,
  heading: AuditTrailHeading | undefined,
  own: boolean,
): ChangeLine[] {
  if (entry.action === 'INSERT') return [{ text: childName ? `${childName} added` : 'Record created' }];
  if (entry.action === 'DELETE') return [{ text: childName ? `${childName} removed` : 'Record deleted' }];
  const summary = entry.description?.trim() || '';
  if (entry.action !== 'UPDATE') return [{ text: summary || entry.action }];
  const prefix = childName ? `${childName}: ` : '';
  // A past resubmit's "rejected → submitted" reads as what it is called today.
  const resubmit = heading === 'Appealed' ? resubmittedSummary(summary) : summary;
  // Only a status move is reworded: an undo row's summary quotes the reason as typed.
  const statusMove = /^(status|approval_status|order_status)(:|\s+changed to)\s/i.test(summary);
  const shown = own && statusMove ? appealWording(resubmit) : resubmit;
  const lines: ChangeLine[] = summary ? [{ text: `${prefix}${shown}` }] : [];
  for (const change of auditFieldChanges(entry.old_values, entry.new_values)) {
    if (summary && summaryCovers(change, entry, summary)) continue;
    const statusLine = own && STATUS_SUMMARY_KEYS.includes(change.key);
    lines.push(
      change.kind === 'line'
        ? { text: `${prefix}${statusLine ? appealWording(change.text) : change.text}` }
        : { label: `${prefix}${change.label}`, before: change.before, after: change.after },
    );
  }
  return lines;
}

const TRAIL_LIMIT = 200;

interface AuditTrailProps {
  entityType: string;
  entityId: string;
  title?: string;
}

export default function AuditTrail({ entityType, entityId, title = 'Audit Trail' }: AuditTrailProps) {
  // Child rows share the page, so a record's trail reads more than the default 50.
  const { data, isLoading } = useAuditLogs(entityType, entityId, 1, TRAIL_LIMIT);

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
  const isChild = (entry: AuditLogEntry) =>
    entry.entity_type !== entityType || entry.entity_id !== entityId;
  // Rejected / Appealed come from the record's own history, never a child row's status.
  const headings = auditTrailHeadings(entries.filter((entry) => !isChild(entry)));
  const rows = entries
    .map((entry) => {
      const childName = isChild(entry) ? entry.entity_label || auditFieldLabel(entry.entity_type) : null;
      const heading = headings.get(entry.id);
      return { entry, heading, lines: collectChangeLines(entry, childName, heading, !childName) };
    })
    .filter((row) => row.lines.length > 0);
  const empty = data?.empty ?? true;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {empty ? (
          <p className="text-sm text-muted-foreground">No audit history for this record.</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No field changes to show.</p>
        ) : (
          <ul className="space-y-4">
            {rows.map(({ entry, heading, lines }) => (
              <li
                key={entry.id}
                data-audit-entry="1"
                className="border-b border-border/50 pb-3 last:border-0 last:pb-0"
              >
                <div className="flex flex-wrap items-baseline gap-2 text-sm">
                  <span data-testid="audit-action" className="font-medium capitalize">
                    {heading ?? entry.action.toLowerCase()}
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
