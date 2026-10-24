'use client';

import * as React from 'react';
import type { ColumnDef, ExpandedState } from '@tanstack/react-table';
import { ChevronDown, ChevronRight, Columns3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { POProgress, POProgressLine } from '../../_shared/types/poProgress.types';
import type { SalesOrderStatus } from '../../_shared/types/projectSalesOrder.types';
import { SalesOrderStatusPill } from './SalesOrderStatusPill';

export function formatUnits(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0);
  if (Number.isNaN(amount)) return String(value);
  return amount.toLocaleString('en-MY', { maximumFractionDigits: 2 });
}

/** "894 not scheduled" / "1,835 more than ordered", or null when the schedule agrees. */
export function describeScheduleGap(line: POProgressLine): string | null {
  const gap = Number(line.schedule_gap);
  if (!gap) return null;
  return gap < 0
    ? `${formatUnits(Math.abs(gap))} not scheduled`
    : `${formatUnits(gap)} more than ordered`;
}

type Filter = 'all' | 'outstanding' | 'differs';

/**
 * PO page, Lines tab (AC-L1 to AC-L3): what was ordered, what the confirmed schedule
 * plans, what AutoCount says went out, and what is still to deliver, per line. A line the
 * schedule disagrees with is an amber row and a filter, not a separate list. Expanding a
 * line lists its deliveries.
 */
export function POLinesProgressGrid({
  progress,
  isLoading,
  error,
}: {
  progress: POProgress | undefined;
  isLoading: boolean;
  error?: unknown;
}) {
  const [expanded, setExpanded] = React.useState<ExpandedState>({});
  const [filter, setFilter] = React.useState<Filter>('all');
  const lines = React.useMemo(() => progress?.lines ?? [], [progress]);
  const differs = lines.filter((line) => Number(line.schedule_gap) !== 0).length;
  const outstanding = lines.filter((line) => Number(line.outstanding) > 0).length;
  const rows = React.useMemo(
    () =>
      filter === 'outstanding'
        ? lines.filter((line) => Number(line.outstanding) > 0)
        : filter === 'differs'
          ? lines.filter((line) => Number(line.schedule_gap) !== 0)
          : lines,
    [filter, lines],
  );

  const columns = React.useMemo<ColumnDef<POProgressLine>[]>(
    () => [
      {
        id: 'expand',
        header: () => <span className="sr-only">Deliveries</span>,
        cell: ({ row }) => (
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            className="size-6"
            onClick={(event) => {
              event.stopPropagation();
              row.toggleExpanded();
            }}
            aria-label={
              row.getIsExpanded()
                ? `Hide the deliveries of line ${row.original.line_no}`
                : `Show the deliveries of line ${row.original.line_no}`
            }
          >
            {row.getIsExpanded() ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </Button>
        ),
        size: 44,
        enableHiding: false,
        enableSorting: false,
        enableResizing: false,
        meta: {
          headerTitle: 'Deliveries',
          expandedContent: (line: POProgressLine) => <LineDeliveries line={line} />,
        },
      },
      {
        id: 'line_no',
        accessorFn: (row) => row.line_no,
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => <span className="text-sm tabular-nums">{row.original.line_no}</span>,
        size: 56,
        meta: { headerTitle: '#' },
      },
      {
        id: 'product',
        accessorFn: (row) => row.product_code ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0">
            <span className="block truncate text-sm font-medium" title={row.original.product_code ?? ''}>
              {row.original.product_code || '-'}
            </span>
            <span
              className="block truncate text-xs text-muted-foreground"
              title={row.original.description ?? ''}
            >
              {row.original.description}
            </span>
          </div>
        ),
        size: 320,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'ordered',
        accessorFn: (row) => Number(row.ordered),
        header: ({ column }) => <DataGridColumnHeader title="Ordered" column={column} />,
        cell: ({ row }) => (
          <span className="block text-right text-sm tabular-nums">
            {formatUnits(row.original.ordered)}
          </span>
        ),
        size: 110,
        meta: { headerTitle: 'Ordered' },
      },
      {
        id: 'scheduled',
        accessorFn: (row) => Number(row.scheduled),
        header: ({ column }) => <DataGridColumnHeader title="Scheduled" column={column} />,
        cell: ({ row }) => {
          const gap = describeScheduleGap(row.original);
          return (
            <span className="block text-right text-sm tabular-nums">
              {formatUnits(row.original.scheduled)}
              {gap && (
                <span className="block truncate text-xs text-amber-700 dark:text-amber-400" title={gap}>
                  {gap}
                </span>
              )}
            </span>
          );
        },
        size: 150,
        meta: { headerTitle: 'Scheduled' },
      },
      {
        id: 'delivered',
        accessorFn: (row) => Number(row.delivered),
        header: ({ column }) => <DataGridColumnHeader title="Delivered" column={column} />,
        cell: ({ row }) => (
          <span className="block text-right text-sm tabular-nums">
            {formatUnits(row.original.delivered)}
          </span>
        ),
        size: 110,
        meta: { headerTitle: 'Delivered' },
      },
      {
        id: 'outstanding',
        accessorFn: (row) => Number(row.outstanding),
        header: ({ column }) => <DataGridColumnHeader title="Outstanding" column={column} />,
        cell: ({ row }) => (
          <span className="block text-right text-sm font-semibold tabular-nums">
            {formatUnits(row.original.outstanding)}
          </span>
        ),
        size: 120,
        meta: { headerTitle: 'Outstanding' },
      },
      {
        id: 'next_delivery_date',
        accessorFn: (row) => row.next_delivery_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Next delivery" column={column} />,
        cell: ({ row }) =>
          row.original.next_delivery_date ? (
            <span className="truncate text-sm">
              {formatDateInMalaysia(row.original.next_delivery_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 130,
        meta: { headerTitle: 'Next delivery' },
      },
    ],
    [],
  );

  const chips: { id: Filter; label: string }[] = [
    { id: 'all', label: `All (${lines.length})` },
    { id: 'outstanding', label: `Still to deliver (${outstanding})` },
    { id: 'differs', label: `Schedule differs (${differs})` },
  ];

  return (
    <>
      <div className="hidden sm:block">
        <PanelDataGrid
          toolbar={({ table }) => (
            <div className="flex w-full flex-wrap items-center gap-2">
              {chips.map((chip) => (
                <Button
                  key={chip.id}
                  type="button"
                  size="sm"
                  variant={filter === chip.id ? 'primary' : 'outline'}
                  aria-pressed={filter === chip.id}
                  onClick={() => setFilter(chip.id)}
                >
                  {chip.label}
                </Button>
              ))}
              <div className="sm:ms-auto">
                <DataGridColumnVisibility
                  table={table}
                  trigger={
                    <Button variant="outline" size="sm" className="gap-1.5">
                      <Columns3 className="size-4" aria-hidden />
                      Columns
                    </Button>
                  }
                />
              </div>
            </div>
          )}
          columns={columns}
          rows={rows}
          getRowId={(row) => row.key}
          listingKey="projects.projects.view::po-lines-progress"
          isLoading={isLoading}
          error={error}
          emptyTitle={filter === 'all' ? 'No lines on this PO yet' : 'No line matches this filter'}
          emptyBody={
            filter === 'all'
              ? 'Lines come from the confirmed PO document, or from the lines keyed in by hand.'
              : undefined
          }
          searchPlaceholder="Search lines"
          searchOf={(row) => [row.product_code, row.description].filter(Boolean).join(' ')}
          sortable
          pageResetKey={filter}
          pageSize={25}
          expanded={expanded}
          onExpandedChange={setExpanded}
          rowClassName={(row) =>
            Number(row.schedule_gap) !== 0 ? 'bg-amber-50 dark:bg-amber-950/20' : undefined
          }
        />
      </div>

      {/* 375: one card per line, the three numbers people ask for. */}
      <div className="space-y-2 sm:hidden" data-testid="po-lines-cards">
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <Button
              key={chip.id}
              type="button"
              size="sm"
              variant={filter === chip.id ? 'primary' : 'outline'}
              aria-pressed={filter === chip.id}
              onClick={() => setFilter(chip.id)}
            >
              {chip.label}
            </Button>
          ))}
        </div>
        {rows.length === 0 && !isLoading ? (
          <div className="rounded-lg border px-4 py-8 text-center">
            <h3 className="text-sm font-semibold">
              {filter === 'all' ? 'No lines on this PO yet' : 'No line matches this filter'}
            </h3>
          </div>
        ) : (
          rows.map((line) => (
            <div
              key={line.key}
              className={`rounded-lg border p-3 ${
                Number(line.schedule_gap) !== 0 ? 'bg-amber-50 dark:bg-amber-950/20' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{line.product_code || '-'}</span>
                <span className="text-xs text-muted-foreground">#{line.line_no}</span>
              </div>
              <p className="truncate text-xs text-muted-foreground" title={line.description ?? ''}>
                {line.description}
              </p>
              <dl className="mt-2 grid grid-cols-3 gap-1 text-xs">
                <CardFact label="Ordered" value={formatUnits(line.ordered)} />
                <CardFact label="Delivered" value={formatUnits(line.delivered)} />
                <CardFact label="Outstanding" value={formatUnits(line.outstanding)} strong />
              </dl>
            </div>
          ))
        )}
      </div>
    </>
  );
}

function CardFact({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <dt className="text-2xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={strong ? 'font-semibold' : undefined}>{value}</dd>
    </div>
  );
}

function LineDeliveries({ line }: { line: POProgressLine }) {
  if (line.deliveries.length === 0) {
    return (
      <p className="px-4 py-3 text-sm text-muted-foreground">
        No sales order carries this line yet. Its deliveries appear once sales orders are built.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid={`line-deliveries-${line.line_no}`}>
        <thead>
          <tr className="text-xs text-muted-foreground">
            <th className="px-4 py-1.5 text-left font-medium">Delivery</th>
            <th className="px-4 py-1.5 text-left font-medium">Area</th>
            <th className="px-4 py-1.5 text-right font-medium">Units</th>
            <th className="px-4 py-1.5 text-right font-medium">Delivered</th>
            <th className="px-4 py-1.5 text-left font-medium">Sales order</th>
          </tr>
        </thead>
        <tbody>
          {line.deliveries.map((delivery, index) => (
            <tr key={`${delivery.sales_order_id}-${index}`} className="border-t border-border/60">
              <td className="px-4 py-1.5">
                {delivery.delivery_date ? formatDateInMalaysia(delivery.delivery_date) : '-'}
              </td>
              <td className="px-4 py-1.5">
                {[delivery.area_group, delivery.label].filter(Boolean).join(', ') || '-'}
              </td>
              <td className="px-4 py-1.5 text-right tabular-nums">{formatUnits(delivery.units)}</td>
              <td className="px-4 py-1.5 text-right tabular-nums">
                {formatUnits(delivery.delivered)}
              </td>
              <td className="px-4 py-1.5">
                <span className="me-2">{delivery.provisional_ref}</span>
                <SalesOrderStatusPill status={delivery.sales_order_status as SalesOrderStatus} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

