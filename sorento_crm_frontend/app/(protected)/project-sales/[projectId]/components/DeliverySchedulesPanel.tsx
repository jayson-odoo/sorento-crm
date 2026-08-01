'use client';

import * as React from 'react';
import Link from 'next/link';
import { CalendarClock, CheckCircle2, TriangleAlert, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { usePurchaseOrders } from '../../_shared/hooks/useProjects';
import { useDeliverySchedules } from '../../_shared/hooks/useDeliverySchedules';
import type { Project } from '../../_shared/types/project.types';
import {
  demoScheduleListState,
  useDemoScheduleState,
} from '../delivery-schedules/_demo/scheduleDemo';
import { DeliveryScheduleUploadDialog } from './DeliveryScheduleUploadDialog';
import { DeliveryScheduleVersionsGrid } from './DeliveryScheduleVersionsGrid';

/**
 * Delivery schedules (P6, contract section 4).
 *
 * A schedule is a matrix the customer drew, and reviewing it is a wide, document-centric job,
 * so this tab does not try to be the review surface. It answers "which schedules do we hold,
 * against which PO, and which of them still has a column that does not add up", and sends the
 * reviewer to a full-width screen to do the work.
 *
 * A revision is a NEW VERSION of the same schedule, never an overwrite (AC-G1), which is why
 * a schedule expands into its version history rather than showing one state.
 */
export function DeliverySchedulesPanel({ project }: { project: Project }) {
  const demo = useDemoScheduleState();
  const live = useDeliverySchedules(demo ? undefined : project.id);
  const view = demo ? demoScheduleListState(demo) : live;

  const purchaseOrders = usePurchaseOrders(demo ? undefined : project.id);
  const hasPurchaseOrder = demo ? true : (purchaseOrders.data ?? []).length > 0;

  const [uploading, setUploading] = React.useState(false);
  const [openId, setOpenId] = React.useState<string | null>(null);

  const rows = React.useMemo(() => view.data ?? [], [view.data]);

  // Land on the first schedule so the tab is not an accordion the user must open to see
  // anything: most projects carry one schedule and that click buys nothing.
  React.useEffect(() => {
    if (!openId && rows.length > 0) setOpenId(rows[0].id);
  }, [openId, rows]);

  const unreconciled = rows.reduce(
    (sum, row) => sum + Math.max(0, row.total_columns - row.reconciled_columns),
    0,
  );
  const awaitingConfirm = rows.filter((row) => !row.confirmed_at).length;

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-sm">Delivery schedules</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              What the customer asked for, when, checked column by column against the PO.
            </p>
          </div>
          {project.can_edit && (
            <Button
              type="button"
              size="sm"
              disabled={!hasPurchaseOrder}
              onClick={() => setUploading(true)}
            >
              <Upload className="size-4" aria-hidden />
              Upload a schedule
            </Button>
          )}
        </CardHeader>

        <CardContent className="space-y-3">
          {rows.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline" className="gap-1">
                <CalendarClock className="size-3" aria-hidden />
                {`${rows.length} schedule${rows.length === 1 ? '' : 's'}`}
              </Badge>
              {unreconciled > 0 && (
                <Badge variant="warning" appearance="light" className="gap-1">
                  <TriangleAlert className="size-3" aria-hidden />
                  {`${unreconciled} column${unreconciled === 1 ? '' : 's'} to reconcile`}
                </Badge>
              )}
              {awaitingConfirm > 0 && (
                <Badge variant="secondary">
                  {`${awaitingConfirm} not confirmed yet`}
                </Badge>
              )}
            </div>
          )}

          {view.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : view.isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8 text-center">
              <h3 className="text-sm font-semibold text-destructive">
                Delivery schedules could not be loaded
              </h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {view.error instanceof Error ? view.error.message : 'Try again shortly.'}
              </p>
            </div>
          ) : rows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
              <h3 className="text-sm font-semibold">No delivery schedule yet</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {hasPurchaseOrder
                  ? 'Upload the schedule the customer sent. Choose the PO it belongs to and it is checked against that PO, column by column.'
                  : 'A schedule is checked against a PO, so record the PO on the POs tab first.'}
              </p>
              {project.can_edit && hasPurchaseOrder && (
                <Button type="button" className="mt-4" onClick={() => setUploading(true)}>
                  <Upload className="size-4" aria-hidden />
                  Upload the first schedule
                </Button>
              )}
            </div>
          ) : (
            <ul className="space-y-2">
              {rows.map((schedule) => (
                <li key={schedule.id} className="rounded-lg border border-border">
                  <div className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-start sm:gap-3">
                    <button
                      type="button"
                      onClick={() =>
                        setOpenId((previous) =>
                          previous === schedule.id ? null : schedule.id,
                        )
                      }
                      aria-expanded={openId === schedule.id}
                      className="min-w-0 flex-1 text-left"
                    >
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span
                          className="truncate text-sm font-medium"
                          title={schedule.po_number ?? 'PO not named yet'}
                        >
                          {schedule.po_number ?? 'PO not named yet'}
                        </span>
                        <ReconciliationBadge
                          reconciled={schedule.reconciled_columns}
                          total={schedule.total_columns}
                        />
                        {schedule.confirmed_at ? (
                          <Badge variant="success" appearance="light" className="gap-1 text-[11px]">
                            <CheckCircle2 className="size-3" aria-hidden />
                            Confirmed
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[11px]">
                            Not confirmed
                          </Badge>
                        )}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                        <span>
                          {`v${schedule.latest_version_no ?? 1} of ${schedule.version_count}`}
                        </span>
                        {schedule.latest_revision_label && (
                          <span
                            className="truncate"
                            title={schedule.latest_revision_label}
                          >
                            {schedule.latest_revision_label}
                          </span>
                        )}
                        {schedule.issuer_party_label && (
                          <span className="truncate" title={schedule.issuer_party_label}>
                            Issued by {schedule.issuer_party_label}
                          </span>
                        )}
                        {schedule.schedule_date && (
                          <span>{formatDateInMalaysia(schedule.schedule_date)}</span>
                        )}
                      </span>
                    </button>

                    {schedule.latest_version_id && (
                      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                        <Button asChild size="sm" variant="outline">
                          <Link
                            href={`/project-sales/${project.id}/delivery-schedules/${schedule.latest_version_id}`}
                          >
                            {schedule.confirmed_at ? 'Open' : 'Review'}
                          </Link>
                        </Button>
                      </div>
                    )}
                  </div>

                  {openId === schedule.id && (
                    <div className="border-t border-border p-3">
                      <DeliveryScheduleVersionsGrid
                        projectId={project.id}
                        schedule={schedule}
                      />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {uploading && (
        <DeliveryScheduleUploadDialog
          project={project}
          schedules={rows}
          onDone={() => setUploading(false)}
        />
      )}
    </>
  );
}

/**
 * The one number that says whether there is work left. "4 of 6" rather than a pass or fail:
 * measured on the real documents, 29 of 37 and 35 of 38 columns reconciled on the first pass,
 * so a fail badge would sit on almost every schedule and stop meaning anything.
 */
export function ReconciliationBadge({
  reconciled,
  total,
}: {
  reconciled: number;
  total: number;
}) {
  if (total <= 0) {
    return (
      <Badge variant="outline" className="text-[11px]">
        No columns read yet
      </Badge>
    );
  }
  if (reconciled >= total) {
    return (
      <Badge variant="success" appearance="light" className="text-[11px]">
        {`All ${total} columns reconciled`}
      </Badge>
    );
  }
  return (
    <Badge variant="warning" appearance="light" className="text-[11px]">
      {`${reconciled} of ${total} columns reconciled`}
    </Badge>
  );
}
