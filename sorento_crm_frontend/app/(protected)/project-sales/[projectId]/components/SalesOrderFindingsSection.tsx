'use client';

import * as React from 'react';
import { CheckCircle2, Info, OctagonAlert, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ProjectSalesOrderFinding } from '../../_shared/types/projectSalesOrder.types';

/**
 * The two tier gate.
 *
 * Blocking findings sit at the top, in their own destructive card, each anchored to the line
 * it concerns: nothing about them is collapsible and nothing about them is a code, because
 * the backend already wrote the sentence. Warnings sit underneath and publish once a reason
 * is recorded. Both sections render even when empty, so "nothing is blocking" is a statement
 * rather than an absence.
 */
export function SalesOrderFindingsSection({
  findings,
  canEdit,
  onAcknowledge,
  onFocusLine,
}: {
  findings: ProjectSalesOrderFinding[];
  canEdit: boolean;
  onAcknowledge: (finding: ProjectSalesOrderFinding) => void;
  onFocusLine: (lineId: string) => void;
}) {
  const hard = findings.filter((finding) => finding.severity === 'hard');
  const warn = findings.filter((finding) => finding.severity === 'warn');
  const info = findings.filter((finding) => finding.severity === 'info');

  // Acknowledged is `acknowledged_at`, which is what the backend's own gate reads. The
  // name beside it is a display field and is absent whenever the acknowledger no longer
  // resolves, which would silently turn a cleared finding back into a blocking one.
  const blocking = hard.filter((finding) => !finding.acknowledged_at);
  const unreasonedWarnings = warn.filter((finding) => !finding.acknowledged_at);

  return (
    <div className="space-y-4">
      <Card className={blocking.length > 0 ? 'border-destructive/50' : undefined}>
        <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <OctagonAlert
              className={`size-4 shrink-0 ${blocking.length > 0 ? 'text-destructive' : 'text-muted-foreground'}`}
              aria-hidden
            />
            <span className="break-words">Blocking</span>
          </CardTitle>
          {blocking.length > 0 && (
            <Badge variant="destructive" appearance="light">
              {`${blocking.length} stop${blocking.length === 1 ? '' : 's'} publishing`}
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {hard.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              Nothing is blocking this sales order.
            </p>
          ) : (
            hard.map((finding) => (
              <FindingRow
                key={finding.id}
                finding={finding}
                canEdit={canEdit}
                tone="hard"
                onAcknowledge={onAcknowledge}
                onFocusLine={onFocusLine}
              />
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <TriangleAlert className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="break-words">Warnings</span>
          </CardTitle>
          {unreasonedWarnings.length > 0 && (
            <Badge variant="warning" appearance="light">
              {`${unreasonedWarnings.length} without a reason`}
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {warn.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              No warnings on this sales order.
            </p>
          ) : (
            warn.map((finding) => (
              <FindingRow
                key={finding.id}
                finding={finding}
                canEdit={canEdit}
                tone="warn"
                onAcknowledge={onAcknowledge}
                onFocusLine={onFocusLine}
              />
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <Info className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="break-words">For information</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {info.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              Nothing else to note.
            </p>
          ) : (
            info.map((finding) => (
              <FindingRow
                key={finding.id}
                finding={finding}
                canEdit={false}
                tone="info"
                onAcknowledge={onAcknowledge}
                onFocusLine={onFocusLine}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FindingRow({
  finding,
  canEdit,
  tone,
  onAcknowledge,
  onFocusLine,
}: {
  finding: ProjectSalesOrderFinding;
  canEdit: boolean;
  tone: 'hard' | 'warn' | 'info';
  onAcknowledge: (finding: ProjectSalesOrderFinding) => void;
  onFocusLine: (lineId: string) => void;
}) {
  // Same keying as the section above: the timestamp decides, the name only labels.
  const acknowledged = Boolean(finding.acknowledged_at);
  const border =
    tone === 'hard' && !acknowledged
      ? 'border-destructive/50 bg-destructive/5'
      : 'border-border';

  return (
    <div className={`rounded-lg border ${border} px-3 py-2.5`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="break-words text-sm">{finding.detail}</p>
          <div className="flex flex-wrap items-center gap-2">
            {finding.line_no != null && finding.line_id && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onFocusLine(finding.line_id as string)}
              >
                {`Show line ${finding.line_no}`}
              </Button>
            )}
            {finding.line_no != null && !finding.line_id && (
              <Badge variant="outline" size="sm">{`Line ${finding.line_no}`}</Badge>
            )}
            {acknowledged && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <CheckCircle2 className="size-3.5" aria-hidden />
                {finding.acknowledged_by_name
                  ? `Cleared by ${finding.acknowledged_by_name}`
                  : 'Acknowledged'}
              </span>
            )}
          </div>
          {acknowledged && finding.acknowledged_reason && (
            <p className="break-words rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">
              {finding.acknowledged_reason}
            </p>
          )}
        </div>

        {tone !== 'info' && !acknowledged && canEdit && (
          <Button
            type="button"
            size="sm"
            variant={tone === 'hard' ? 'outline' : 'primary'}
            className="shrink-0"
            onClick={() => onAcknowledge(finding)}
          >
            {tone === 'hard' ? 'Override with a reason' : 'Clear with a reason'}
          </Button>
        )}
      </div>
    </div>
  );
}
