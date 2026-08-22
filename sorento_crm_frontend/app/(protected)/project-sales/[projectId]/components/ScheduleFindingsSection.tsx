'use client';

import * as React from 'react';
import { CheckCircle2, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ProjectSalesOrderFinding } from '../../_shared/types/projectSalesOrder.types';
import { SalesOrderAcknowledgeDialog } from './SalesOrderAcknowledgeDialog';

/**
 * The (PO, schedule) pair's OWN findings - a schedule column for a product not on the PO
 * at all, a phase from another project, an un-mapped column, the whole document's total
 * mismatch. None of these name a PO line, so none of them belong to any one of the sales
 * orders this pair drafted (see `SODraftFinding`'s own docstring on the backend); showing
 * one on an order's own page read as a contradiction when that order does not even carry
 * the product in question.
 *
 * Renders nothing at all once every finding here is cleared - unlike the order's own
 * Blocking/Warnings cards, an empty state here would tell every draft's reader about a
 * concern that is not theirs to act on.
 */
export function ScheduleFindingsSection({
  findings,
  canEdit,
  onAcknowledge,
}: {
  findings: ProjectSalesOrderFinding[];
  canEdit: boolean;
  onAcknowledge: (findingId: string, reason: string) => Promise<unknown>;
}) {
  const [acknowledging, setAcknowledging] = React.useState<ProjectSalesOrderFinding | null>(
    null,
  );
  const open = findings.filter((finding) => !finding.acknowledged_at);

  if (open.length === 0) return null;

  return (
    <>
      <Card className="border-amber-500/40">
        <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <TriangleAlert className="size-4 shrink-0 text-amber-600" aria-hidden />
            <span className="break-words">Schedule / PO findings</span>
          </CardTitle>
          <Badge variant="warning" appearance="light">
            {`${open.length} on this purchase order`}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-2">
          {findings.map((finding) => {
            const acknowledged = Boolean(finding.acknowledged_at);
            return (
              <div
                key={finding.id}
                className={`rounded-lg border px-3 py-2.5 ${
                  acknowledged ? 'border-border' : 'border-amber-500/40 bg-amber-500/5'
                }`}
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <p className="break-words text-sm">{finding.detail}</p>
                    {acknowledged && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <CheckCircle2 className="size-3.5" aria-hidden />
                        {finding.acknowledged_by_name
                          ? `Cleared by ${finding.acknowledged_by_name}`
                          : 'Acknowledged'}
                      </span>
                    )}
                    {acknowledged && finding.acknowledged_reason && (
                      <p className="break-words rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">
                        {finding.acknowledged_reason}
                      </p>
                    )}
                  </div>
                  {!acknowledged && canEdit && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="shrink-0"
                      onClick={() => setAcknowledging(finding)}
                    >
                      Clear with a reason
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {acknowledging && (
        <SalesOrderAcknowledgeDialog
          finding={acknowledging}
          onDone={() => setAcknowledging(null)}
          onConfirm={(reason) => onAcknowledge(acknowledging.id, reason)}
          submitting={false}
        />
      )}
    </>
  );
}
