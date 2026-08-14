'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { ArrowLeft, CheckCircle2, Truck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useSearchParams } from 'next/navigation';
import { useSalesOrder } from '../../../hooks/useSalesOrders';
import SalesOrderNavigation from '../../components/SalesOrderNavigation';
import { fmtDate, fmtInt } from '../../../lib/format';
import type { SalesOrder, SalesOrderLine } from '../../../types/scm.types';

/**
 * The sales-order detail, built to mirror `PurchaseOrderDetail` section for section: the
 * same header shape, the same summary grid, the same lines DataGrid, and the same "always
 * render every section, with an explicit empty state" rule.
 *
 * Mirrored deliberately rather than reinvented. These two screens are one click apart in the
 * same menu and they answer the same question about opposite sides of the book, so a planner
 * who has learnt where a figure lives on one has learnt it on the other. Where they differ,
 * they differ because the DOMAIN differs - a sales order is delivered rather than received,
 * so the goods-receipt panel becomes a delivery panel - never because they were written on
 * different days.
 */

type BadgeDef = { variant: 'secondary' | 'primary' | 'warning' | 'success'; label: string };

function titleCase(v: string): string {
  return v.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_BADGE: Record<string, BadgeDef> = {
  open: { variant: 'primary', label: 'Open' },
  partially_delivered: { variant: 'warning', label: 'Partially delivered' },
  delivered: { variant: 'success', label: 'Delivered' },
  closed: { variant: 'secondary', label: 'Closed' },
  cancelled: { variant: 'secondary', label: 'Cancelled' },
};

const statusBadge = (s: string): BadgeDef =>
  STATUS_BADGE[s] ?? { variant: 'secondary', label: titleCase(s) };

/** Where the order came from. `history` is its own answer because "Manual" would claim
 *  somebody keyed a 2020 order by hand. Mirrors the purchase-order side's `import`. */
const SOURCE_LABELS: Record<string, string> = {
  inquiry: 'Order inquiry sheet',
  upload: 'Outstanding upload',
  history: 'Absorbed history',
  manual: 'Manual',
};

const PRIORITY_LABELS: Record<string, string> = {
  urgent: 'Urgent',
  high: 'High',
  normal: 'Normal',
  low: 'Low',
};

/** Is this order still owed to the customer? The counterpart of the PO screen's "On order".
 *  Derived from the OPEN line count rather than the status alone, because an order can sit
 *  in an open status with every line closed. */
const countsAsCommitted = (so: SalesOrder) =>
  (so.open_line_count ?? 0) > 0 && so.committed_qty > 0;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export function SalesOrderDetail({ id }: { id: string }) {
  const { data, isLoading, isError } = useSalesOrder(id);
  const searchParams = useSearchParams();
  const listSearch = searchParams.toString();

  const lines = useMemo<SalesOrderLine[]>(() => data?.lines ?? [], [data]);

  const columns = useMemo<ColumnDef<SalesOrderLine>[]>(
    () => [
      {
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="SKU" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col">
            <span className="font-medium">{row.original.sku}</span>
            <span
              className="truncate text-xs text-muted-foreground"
              title={row.original.product_name}
            >
              {row.original.product_name}
            </span>
          </div>
        ),
        size: 260,
        meta: { headerTitle: 'SKU' },
      },
      {
        accessorKey: 'qty_ordered',
        header: ({ column }) => <DataGridColumnHeader title="Qty ordered" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty_ordered),
        size: 130,
        meta: {
          headerTitle: 'Qty ordered',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        accessorKey: 'qty_delivered',
        header: ({ column }) => <DataGridColumnHeader title="Qty delivered" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty_delivered),
        size: 130,
        meta: {
          headerTitle: 'Qty delivered',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'outstanding',
        header: ({ column }) => <DataGridColumnHeader title="Still owed" column={column} />,
        // Computed here rather than sent, so it cannot disagree with the two columns beside
        // it. A negative delivery (over-shipped) reads as 0 rather than as a negative
        // commitment, which is what the committed figure does too.
        cell: ({ row }) =>
          fmtInt(Math.max(row.original.qty_ordered - row.original.qty_delivered, 0)),
        size: 120,
        meta: {
          headerTitle: 'Still owed',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        accessorKey: 'warehouse_code',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => row.original.warehouse_code || '-',
        size: 120,
        meta: { headerTitle: 'Location' },
      },
      {
        accessorKey: 'required_date',
        header: ({ column }) => <DataGridColumnHeader title="Required" column={column} />,
        cell: ({ row }) =>
          row.original.required_date ? fmtDate(row.original.required_date) : '-',
        size: 130,
        meta: { headerTitle: 'Required' },
      },
      {
        accessorKey: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UoM" column={column} />,
        cell: ({ row }) => row.original.uom,
        size: 90,
        meta: { headerTitle: 'UoM' },
      },
      {
        accessorKey: 'line_status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={row.original.line_status === 'closed' ? 'secondary' : 'primary'}
            appearance="light"
          >
            {titleCase(row.original.line_status ?? 'open')}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Status' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // Back and prev/next live on the RIGHT of the record header, next to each other, the way
  // the purchase-order and users screens do it.
  const backLink = (
    <Button variant="outline" size="sm" asChild className="w-fit gap-1.5">
      <Link href={`/scm/sales-orders${listSearch ? `?${listSearch}` : ''}`}>
        <ArrowLeft className="size-4" />
        Back to sales orders
      </Link>
    </Button>
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-sm font-semibold">Sales order not found</div>
          <p className="max-w-md text-sm text-muted-foreground">
            This sales order doesn&apos;t exist, or it was removed after this link was made.
            Head back to the list to pick another.
          </p>
        </Card>
      </div>
    );
  }

  const so = data;
  const s = statusBadge(so.status);
  const committed = countsAsCommitted(so);
  const lineCount = so.line_count ?? lines.length;

  return (
    <div className="space-y-4">
      {/* Summary - always rendered. */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="text-lg">{so.so_number}</CardTitle>
              <Badge variant={s.variant} appearance="light">
                {s.label}
              </Badge>
              {committed ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-scm-incoming">
                  <CheckCircle2 className="size-3.5" /> Committed demand
                </span>
              ) : (
                // Why it is not committed, which is not always "delivered": an absorbed 2020
                // order is closed history, and calling it delivered claims a delivery this
                // system recorded when it only ever read one off a spreadsheet.
                <span className="text-xs text-muted-foreground">
                  {so.source === 'history'
                    ? 'Not committed (absorbed history)'
                    : so.status === 'cancelled'
                      ? 'Not committed (cancelled)'
                      : 'Not committed (nothing outstanding)'}
                </span>
              )}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <SalesOrderNavigation salesOrderId={id} />
              {backLink}
            </div>
          </div>
        </CardHeader>
        {/* Named as a region so a reader (and a test) can tell the summary's "Still owed"
            from the lines grid's column of the same name. They share the phrase on purpose:
            it is the same quantity, once for the order and once per line. */}
        <section
          aria-label="Order summary"
          className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4"
        >
          <Field label="Customer">{so.customer_name || '-'}</Field>
          <Field label="Customer code">{so.customer_code || '-'}</Field>
          <Field label="Order type">{so.order_type_label || '-'}</Field>
          <Field label="Market segment">{so.market_segment || '-'}</Field>
          <Field label="Order date">{fmtDate(so.order_date)}</Field>
          <Field label="Requested delivery">
            {so.requested_delivery_date ? fmtDate(so.requested_delivery_date) : '-'}
          </Field>
          <Field label="Priority">{PRIORITY_LABELS[so.priority] ?? titleCase(so.priority)}</Field>
          <Field label="Locations">
            {so.stock_locations?.length ? so.stock_locations.join(', ') : '-'}
          </Field>
          <Field label="Total qty">{fmtInt(so.total_qty)}</Field>
          <Field label="Lines">{fmtInt(lineCount)}</Field>
          {/* What is still owed, shown only when it differs from what the order says - on a
              wholly open order the two are equal and a second identical figure is noise,
              while on a part-delivered or absorbed order the gap IS the answer. */}
          {so.committed_qty !== so.total_qty ? (
            <Field label="Still owed">{fmtInt(so.committed_qty)}</Field>
          ) : null}
          <Field label="Source">{SOURCE_LABELS[so.source ?? 'manual'] ?? 'Manual'}</Field>
        </section>
      </Card>

      {/* Lines - always rendered, explicit empty state. */}
      <DataGrid
        table={table}
        recordCount={lines.length}
        isLoading={false}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="This sales order has no lines."
        listingKey=""
      >
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Order lines</CardTitle>
            </CardHeading>
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      </DataGrid>

      {/* Delivery - always rendered, empty state when nothing has shipped. The counterpart
          of the purchase-order screen's goods receipt. */}
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Delivery</CardTitle>
          </CardHeading>
        </CardHeader>
        <div className="p-4">
          {so.total_qty > 0 && so.committed_qty === 0 ? (
            <div className="flex items-center gap-2 text-sm">
              <Truck className="size-4 text-scm-incoming" />
              <span className="font-medium">{fmtInt(so.total_qty)}</span>
              <span className="text-muted-foreground">delivered in full</span>
            </div>
          ) : so.committed_qty > 0 && so.committed_qty < so.total_qty ? (
            <p className="text-sm text-muted-foreground">
              {fmtInt(so.total_qty - so.committed_qty)} of {fmtInt(so.total_qty)} delivered.{' '}
              {fmtInt(so.committed_qty)} still owed across {fmtInt(so.open_line_count ?? 0)}{' '}
              {(so.open_line_count ?? 0) === 1 ? 'line' : 'lines'}.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Nothing delivered yet. Create a delivery order from the sales orders list to
              record what shipped.
            </p>
          )}
        </div>
      </Card>

      {/* Note - always rendered, because a blank panel says "there is no note" where a
          missing panel says nothing at all. */}
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Note</CardTitle>
          </CardHeading>
        </CardHeader>
        <div className="p-4">
          {so.internal_note ? (
            <p className="text-sm">{so.internal_note}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              No note. Absorbed and imported orders keep the customer name and code here when
              the customer could not be matched.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

export default SalesOrderDetail;
