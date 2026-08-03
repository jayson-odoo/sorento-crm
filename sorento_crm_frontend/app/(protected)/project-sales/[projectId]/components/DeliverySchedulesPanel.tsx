'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import Link from 'next/link';
import { CalendarClock, CheckCircle2, TriangleAlert, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
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

  type Row = (typeof rows)[number];

  const columns = React.useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: 'po_number',
        accessorFn: (row) => row.po_number ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Against PO" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium" title={row.original.po_number ?? ''}>
            {row.original.po_number ?? '-'}
          </span>
        ),
        size: 160,
        meta: { headerTitle: 'Against PO' },
      },
      {
        id: 'reconciliation',
        accessorFn: (row) => row.reconciled_columns - row.total_columns,
        header: ({ column }) => <DataGridColumnHeader title="Reconciled" column={column} />,
        cell: ({ row }) => (
          <ReconciliationBadge
            reconciled={row.original.reconciled_columns}
            total={row.original.total_columns}
          />
        ),
        size: 210,
        meta: { headerTitle: 'Reconciled' },
      },
      {
        id: 'confirmed',
        accessorFn: (row) => (row.confirmed_at ? 1 : 0),
        header: ({ column }) => <DataGridColumnHeader title="Confirmed" column={column} />,
        cell: ({ row }) =>
          row.original.confirmed_at ? (
            <Badge variant="success" appearance="light" className="gap-1 text-[11px]">
              <CheckCircle2 className="size-3" aria-hidden />
              Confirmed
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="light" className="text-[11px]">
              Not confirmed
            </Badge>
          ),
        size: 140,
        meta: { headerTitle: 'Confirmed' },
      },
      {
        id: 'version',
        accessorFn: (row) => row.latest_version_no ?? 1,
        header: ({ column }) => <DataGridColumnHeader title="Version" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm">
            {`v${row.original.latest_version_no ?? 1} of ${row.original.version_count}`}
          </span>
        ),
        size: 120,
        meta: { headerTitle: 'Version' },
      },
      {
        id: 'revision',
        accessorFn: (row) => row.latest_revision_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Revision" column={column} />,
        cell: ({ row }) =>
          row.original.latest_revision_label ? (
            <span className="truncate text-sm" title={row.original.latest_revision_label}>
              {row.original.latest_revision_label}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 160,
        meta: { headerTitle: 'Revision' },
      },
      {
        id: 'issuer',
        accessorFn: (row) => row.issuer_party_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Issued by" column={column} />,
        cell: ({ row }) =>
          row.original.issuer_party_label ? (
            <span className="truncate text-sm" title={row.original.issuer_party_label}>
              {row.original.issuer_party_label}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 180,
        meta: { headerTitle: 'Issued by' },
      },
      {
        id: 'schedule_date',
        accessorFn: (row) => row.schedule_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Dated" column={column} />,
        cell: ({ row }) =>
          row.original.schedule_date ? (
            <span className="truncate text-sm">
              {formatDateInMalaysia(row.original.schedule_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 120,
        meta: { headerTitle: 'Dated' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) =>
          row.original.latest_version_id ? (
            <div
              className="flex justify-end"
              onClick={(event) => event.stopPropagation()}
            >
              <Button asChild size="sm" variant="outline">
                <Link
                  href={`/project-sales/${project.id}/delivery-schedules/${row.original.latest_version_id}`}
                >
                  {row.original.confirmed_at ? 'Open' : 'Review'}
                </Link>
              </Button>
            </div>
          ) : null,
        size: 110,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [project.id],
  );

  const open = rows.find((row) => row.id === openId) ?? null;

  return (
    <>
      <PanelDataGrid
        title="Delivery schedules"
        toolbar={
          <>
            {rows.length > 0 && (
              <Badge variant="secondary" appearance="light" className="gap-1">
                <CalendarClock className="size-3" aria-hidden />
                {`${rows.length} schedule${rows.length === 1 ? '' : 's'}`}
              </Badge>
            )}
            {unreconciled > 0 && (
              <Badge variant="warning" appearance="light" className="gap-1">
                <TriangleAlert className="size-3" aria-hidden />
                {`${unreconciled} column${unreconciled === 1 ? '' : 's'} to reconcile`}
              </Badge>
            )}
            {awaitingConfirm > 0 && (
              <Badge variant="secondary" appearance="light">
                {`${awaitingConfirm} not confirmed yet`}
              </Badge>
            )}
            {project.can_edit && (
              <Button
                type="button"
                size="sm"
                disabled={!hasPurchaseOrder}
                title={
                  hasPurchaseOrder
                    ? undefined
                    : 'A schedule is checked against a PO, so record the PO first'
                }
                onClick={() => setUploading(true)}
              >
                <Upload className="size-4" aria-hidden />
                Upload a schedule
              </Button>
            )}
          </>
        }
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        listingKey="projects.projects.view::project-delivery-schedules"
        isLoading={view.isLoading}
        error={view.isError ? view.error : undefined}
        emptyTitle="No delivery schedule yet"
        onRowClick={(row) => setOpenId((previous) => (previous === row.id ? null : row.id))}
      />

      {open && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              {open.po_number ?? 'Schedule versions'}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DeliveryScheduleVersionsGrid projectId={project.id} schedule={open} />
          </CardContent>
        </Card>
      )}

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
