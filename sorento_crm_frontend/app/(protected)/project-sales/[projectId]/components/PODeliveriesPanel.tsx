'use client';

import * as React from 'react';
import Link from 'next/link';
import type { ColumnDef } from '@tanstack/react-table';
import { Columns3, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DatePicker } from '@/components/ui/date-picker';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useChangeAreaDate } from '../../_shared/hooks/usePoProgress';
import type { POProgress, POProgressArea } from '../../_shared/types/poProgress.types';
import type { SalesOrderStatus } from '../../_shared/types/projectSalesOrder.types';
import { formatUnits } from './POLinesProgressGrid';
import { SalesOrderStatusPill } from './SalesOrderStatusPill';

/** A local calendar day as `YYYY-MM-DD`, never through UTC (which can move it a day). */
export function isoDay(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${value.getFullYear()}-${month}-${day}`;
}

function fromIsoDay(value: string | null): Date | undefined {
  if (!value) return undefined;
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

/**
 * PO page, Deliveries tab (AC-D1 to AC-D4): one row per area of the confirmed schedule.
 * The date is changed where it is shown (Q2a): click it, pick the new one. Draft sales
 * order lines on the area follow and a published one gets an amendment proposed; the
 * toast says which, with Undo.
 */
export function PODeliveriesPanel({
  projectId,
  poId,
  progress,
  isLoading,
  error,
  canEdit,
  onUpload,
}: {
  projectId: string;
  poId: string;
  progress: POProgress | undefined;
  isLoading: boolean;
  error?: unknown;
  canEdit: boolean;
  onUpload: () => void;
}) {
  const [editing, setEditing] = React.useState<string | null>(null);
  const change = useChangeAreaDate(projectId, poId);
  const rows = React.useMemo(() => progress?.areas ?? [], [progress]);
  const scheduleVersionId = progress?.schedule_version_id ?? null;

  const moveArea = React.useCallback(
    (area: POProgressArea, next: Date | undefined) => {
      if (!next) return;
      const day = isoDay(next);
      setEditing(null);
      if (day === area.delivery_date) return;
      change.mutate({ phaseId: area.phase_id, body: { delivery_date: day } });
    },
    [change],
  );

  const columns = React.useMemo<ColumnDef<POProgressArea>[]>(
    () => [
      {
        id: 'area_group',
        accessorFn: (row) => row.area_group,
        header: ({ column }) => <DataGridColumnHeader title="Area" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium" title={row.original.area_group}>
            {row.original.area_group}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Area' },
      },
      {
        id: 'label',
        accessorFn: (row) => row.label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Levels" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm" title={row.original.label ?? ''}>
            {row.original.label || `Part ${row.original.sequence}`}
          </span>
        ),
        size: 170,
        meta: { headerTitle: 'Levels' },
      },
      {
        id: 'delivery_date',
        accessorFn: (row) => row.delivery_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Delivery date" column={column} />,
        cell: ({ row }) => {
          const area = row.original;
          const label = [area.area_group, area.label].filter(Boolean).join(' ');
          if (canEdit && editing === area.phase_id) {
            return (
              <div onClick={(event) => event.stopPropagation()}>
                <DatePicker
                  value={fromIsoDay(area.delivery_date)}
                  onChange={(next) => moveArea(area, next)}
                  required
                  ariaLabel={`Delivery date of ${label}`}
                  inputClassName="h-8"
                />
              </div>
            );
          }
          const shown = area.delivery_date ? formatDateInMalaysia(area.delivery_date) : 'No date';
          return canEdit ? (
            <button
              type="button"
              className="truncate rounded px-1 text-sm text-primary hover:underline disabled:opacity-50"
              disabled={change.isPending}
              onClick={(event) => {
                event.stopPropagation();
                setEditing(area.phase_id);
              }}
              aria-label={`Change the delivery date of ${label}, now ${shown}`}
            >
              {shown}
            </button>
          ) : (
            <span className="truncate text-sm">{shown}</span>
          );
        },
        size: 230,
        meta: { headerTitle: 'Delivery date' },
      },
      {
        id: 'units',
        accessorFn: (row) => Number(row.units),
        header: ({ column }) => <DataGridColumnHeader title="Units" column={column} />,
        cell: ({ row }) => (
          <span className="block text-right text-sm tabular-nums">
            {formatUnits(row.original.units)}
          </span>
        ),
        size: 100,
        meta: { headerTitle: 'Units' },
      },
      {
        id: 'delivered',
        accessorFn: (row) => Number(row.delivered),
        header: ({ column }) => <DataGridColumnHeader title="Delivered" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-right text-sm tabular-nums">
            {`${formatUnits(row.original.delivered)} of ${formatUnits(row.original.units)}`}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Delivered' },
      },
      {
        id: 'sales_orders',
        accessorFn: (row) => row.sales_orders.map((order) => order.provisional_ref).join(' '),
        header: ({ column }) => <DataGridColumnHeader title="Sales order" column={column} />,
        cell: ({ row }) =>
          row.original.sales_orders.length === 0 ? (
            <span className="text-muted-foreground">Not built yet</span>
          ) : (
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              {row.original.sales_orders.map((order) => (
                <span key={order.id} className="flex items-center gap-1">
                  <Link
                    href={`/project-sales/${projectId}/sales-orders/${order.id}`}
                    className="text-sm text-primary hover:underline"
                    onClick={(event) => event.stopPropagation()}
                  >
                    {order.provisional_ref}
                  </Link>
                  <SalesOrderStatusPill status={order.status as SalesOrderStatus} />
                </span>
              ))}
            </div>
          ),
        size: 260,
        meta: { headerTitle: 'Sales order' },
      },
    ],
    [canEdit, change.isPending, editing, moveArea, projectId],
  );

  return (
    <PanelDataGrid
      toolbar={({ table }) => (
        <div className="flex w-full flex-wrap items-center gap-2">
          {scheduleVersionId && (
            <Button asChild size="sm" variant="outline">
              <Link href={`/project-sales/${projectId}/delivery-schedules/${scheduleVersionId}`}>
                By product
              </Link>
            </Button>
          )}
          <div className="flex flex-wrap items-center gap-2 sm:ms-auto">
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1.5">
                  <Columns3 className="size-4" aria-hidden />
                  Columns
                </Button>
              }
            />
            {canEdit && (
              <Button type="button" size="sm" variant="outline" onClick={onUpload}>
                <Upload className="size-4" aria-hidden />
                {scheduleVersionId ? 'Upload revised schedule' : 'Upload delivery schedule'}
              </Button>
            )}
          </div>
        </div>
      )}
      columns={columns}
      rows={rows}
      getRowId={(row) => row.phase_id}
      listingKey="projects.projects.view::po-deliveries"
      isLoading={isLoading}
      error={error}
      emptyTitle="No confirmed delivery schedule yet"
      emptyBody="Areas and their dates appear here once a delivery schedule for this PO is confirmed."
      sortable
      pageSize={25}
    />
  );
}
