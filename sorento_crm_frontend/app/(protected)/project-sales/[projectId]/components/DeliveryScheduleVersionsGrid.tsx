'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useDeliveryScheduleMutations,
  useDeliveryScheduleVersions,
} from '../../_shared/hooks/useDeliverySchedules';
import type {
  DeliverySchedule,
  DeliveryScheduleVersionSummary,
} from '../../_shared/types/deliverySchedule.types';
import {
  demoVersionSummaries,
  useDemoScheduleState,
} from '../delivery-schedules/_demo/scheduleDemo';
import { ReconciliationBadge } from './DeliverySchedulesPanel';

/**
 * The version history of one schedule.
 *
 * Every revision the customer sends is a new version of the same commitment, never an
 * overwrite (AC-G1), so the older ones stay openable: "what did they ask for before the
 * delay" is the question the whole versioning exists to answer.
 */
export function DeliveryScheduleVersionsGrid({
  projectId,
  schedule,
  canEdit = false,
}: {
  projectId: string;
  schedule: DeliverySchedule;
  canEdit?: boolean;
}) {
  const demo = useDemoScheduleState();
  const live = useDeliveryScheduleVersions(demo ? undefined : schedule.id);
  const { removeVersion } = useDeliveryScheduleMutations(projectId);
  const [pendingDelete, setPendingDelete] =
    React.useState<DeliveryScheduleVersionSummary | null>(null);

  const rows = React.useMemo<DeliveryScheduleVersionSummary[]>(
    () => (demo ? demoVersionSummaries() : (live.data ?? [])),
    [demo, live.data],
  );
  const isLoading = demo ? false : live.isLoading;
  const isError = demo ? false : live.isError;

  const columns = React.useMemo<ColumnDef<DeliveryScheduleVersionSummary>[]>(
    () => [
      {
        accessorKey: 'version_no',
        header: ({ column }) => <DataGridColumnHeader title="Version" column={column} />,
        cell: ({ row }) => <span>{`v${row.original.version_no}`}</span>,
        size: 80,
      },
      {
        accessorKey: 'revision_label',
        header: ({ column }) => <DataGridColumnHeader title="Revision" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.revision_label ?? ''}>
            {row.original.revision_label ?? 'No revision label'}
          </span>
        ),
        size: 220,
      },
      {
        accessorKey: 'issuer_party_label',
        header: ({ column }) => <DataGridColumnHeader title="Issued by" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.issuer_party_label ?? ''}>
            {row.original.issuer_party_label ?? '-'}
          </span>
        ),
        size: 200,
      },
      {
        accessorKey: 'schedule_date',
        header: ({ column }) => <DataGridColumnHeader title="Dated" column={column} />,
        cell: ({ row }) =>
          row.original.schedule_date
            ? formatDateInMalaysia(row.original.schedule_date)
            : 'Not dated',
        size: 130,
      },
      {
        id: 'reconciliation',
        header: ({ column }) => (
          <DataGridColumnHeader title="Reconciliation" column={column} />
        ),
        cell: ({ row }) => (
          <ReconciliationBadge
            reconciled={row.original.reconciled_columns}
            total={row.original.total_columns}
          />
        ),
        size: 190,
      },
      {
        accessorKey: 'confirmed_at',
        header: ({ column }) => <DataGridColumnHeader title="Confirmed" column={column} />,
        cell: ({ row }) =>
          row.original.confirmed_at
            ? formatDateInMalaysia(row.original.confirmed_at)
            : 'Not yet',
        size: 130,
      },
      {
        id: 'open',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button asChild size="sm" variant="outline">
              <Link
                href={`/project-sales/${projectId}/delivery-schedules/${row.original.id}`}
              >
                Open
              </Link>
            </Button>
            {canEdit && (
              <Button
                type="button"
                mode="icon"
                variant="ghost"
                size="sm"
                aria-label={`Delete version ${row.original.version_no}`}
                title="Delete this version"
                onClick={() => setPendingDelete(row.original)}
              >
                <Trash2 className="size-3.5 text-destructive" />
              </Button>
            )}
          </div>
        ),
        size: canEdit ? 130 : 90,
      },
    ],
    [projectId, canEdit],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
    columnResizeMode: 'onChange',
  });

  if (isError) {
    return (
      <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-4 text-center text-xs text-destructive">
        The version history could not be loaded.
      </p>
    );
  }

  if (!isLoading && rows.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
        No versions on record. Upload the schedule to open version 1.
      </p>
    );
  }

  return (
    <>
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <DataGridTable />
      </DataGrid>

      <ConfirmDeleteDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(next) => !next && setPendingDelete(null)}
        title="Confirm delete"
        description={
          pendingDelete
            ? `Delete version ${pendingDelete.version_no}${
                pendingDelete.revision_label ? ` (${pendingDelete.revision_label})` : ''
              }? This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (!pendingDelete) return;
          await removeVersion.mutateAsync(pendingDelete.id);
        }}
        onSuccess={() => setPendingDelete(null)}
        successMessage="Schedule version deleted"
      />
    </>
  );
}
