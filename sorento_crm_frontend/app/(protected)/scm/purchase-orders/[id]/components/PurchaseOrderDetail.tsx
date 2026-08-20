'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  SortingState,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ArrowLeft, CheckCircle2, PackageCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useSearchParams } from 'next/navigation';
import { usePurchaseOrder } from '../../../hooks/usePurchaseOrders';
import PurchaseOrderNavigation from '../../components/PurchaseOrderNavigation';
import { fmtDate, fmtInt } from '../../../lib/format';
import type { PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus } from '../../../types/scm.types';

type BadgeDef = { variant: 'secondary' | 'primary' | 'warning' | 'success'; label: string };

function titleCase(v: string): string {
  return v.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_BADGE: Partial<Record<PurchaseOrderStatus, BadgeDef>> = {
  draft: { variant: 'secondary', label: 'Draft' },
  draft_recommendation: { variant: 'secondary', label: 'Draft' },
  active: { variant: 'primary', label: 'Active' },
  confirmed: { variant: 'primary', label: 'Confirmed' },
  partially_received: { variant: 'warning', label: 'Partially received' },
  received: { variant: 'success', label: 'Received' },
  closed: { variant: 'secondary', label: 'Closed' },
  cancelled: { variant: 'secondary', label: 'Cancelled' },
};

const statusBadge = (s: string): BadgeDef =>
  STATUS_BADGE[s as PurchaseOrderStatus] ?? { variant: 'secondary', label: titleCase(s) };

/** Where the order came from. `import` is its own answer because "Manual" would claim
 *  somebody keyed a 2020 order by hand. */
const SOURCE_LABELS: Record<NonNullable<PurchaseOrder['source']>, string> = {
  recommendation: 'Reorder recommendation',
  import: 'Imported history',
  crm: 'Created in CRM',
  manual: 'Manual',
};

const isDraft = (s: string) => s === 'draft_recommendation' || s === 'draft';
const countsAsOnOrder = (po: PurchaseOrder) =>
  po.is_on_order ?? (!isDraft(po.status) && po.status !== 'cancelled');

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export function PurchaseOrderDetail({ id }: { id: string }) {
  const { data, isLoading, isError } = usePurchaseOrder(id);
  // Back returns to the list the user actually had open, filters and page included.
  const listSearch = useSearchParams().toString();

  const lines = useMemo<PurchaseOrderLine[]>(() => data?.lines ?? [], [data]);
  // Sorted here rather than by the API: the lines come embedded in the order read, so there
  // is no second request to spend and no page boundary to sort across.
  const [sorting, setSorting] = useState<SortingState>([]);

  const columns = useMemo<ColumnDef<PurchaseOrderLine>[]>(
    () => [
      {
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="SKU" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col">
            <span className="font-medium">{row.original.sku}</span>
            <span className="truncate text-xs text-muted-foreground" title={row.original.product_name}>
              {row.original.product_name}
            </span>
          </div>
        ),
        size: 260,
        meta: { headerTitle: 'SKU' },
      },
      {
        id: 'qty_ordered',
        // The sort value is the NUMBER, never the printed string: a quantity read off the
        // API as "1200.0000" would otherwise order before "45" the way a word does.
        accessorFn: (line) => Number(line.qty_ordered),
        header: ({ column }) => <DataGridColumnHeader title="Qty ordered" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty_ordered),
        size: 130,
        meta: { headerTitle: 'Qty ordered', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'qty_received',
        accessorFn: (line) => Number(line.qty_received),
        header: ({ column }) => <DataGridColumnHeader title="Qty received" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty_received),
        size: 130,
        meta: { headerTitle: 'Qty received', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UoM" column={column} />,
        cell: ({ row }) => row.original.uom,
        size: 90,
        meta: { headerTitle: 'UoM' },
      },
      {
        // Location is a LINE fact (captain, 20 Aug) - the header Warehouse field is
        // gone, so the line states its own destination.
        accessorKey: 'warehouse_code',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) =>
          row.original.warehouse_code ? (
            <span className="truncate" title={row.original.warehouse_code}>
              {row.original.warehouse_code}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 110,
        meta: { headerTitle: 'Location' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.id,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // Back and prev/next live on the RIGHT of the record header, next to each other, the way
  // the users screen does it: the actions that leave this record belong beside the record's
  // own title, not stacked above it where they read as page furniture.
  const backLink = (
    <Button variant="outline" size="sm" asChild className="w-fit gap-1.5">
      <Link href={`/scm/purchase-orders${listSearch ? `?${listSearch}` : ''}`}>
        <ArrowLeft className="size-4" />
        Back to purchase orders
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
          <div className="text-sm font-semibold">Purchase order not found</div>
          <p className="max-w-md text-sm text-muted-foreground">
            This purchase order doesn&apos;t exist, or the draft was created in another browser
            session. Head back to the list to pick another.
          </p>
        </Card>
      </div>
    );
  }

  const po = data;
  const s = statusBadge(po.status);
  const onOrder = countsAsOnOrder(po);

  return (
    <div className="space-y-4">
      {/* Summary - always rendered. */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="text-lg">{po.po_number}</CardTitle>
              <Badge variant={s.variant} appearance="light">
                {s.label}
              </Badge>
              {onOrder ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-scm-incoming">
                  <CheckCircle2 className="size-3.5" /> On order
                </span>
              ) : (
                // Why it is not incoming, which is not always "draft": an imported 2020 order
                // is closed and fully received, and calling it a draft says somebody has yet
                // to confirm a purchase that arrived six years ago.
                <span className="text-xs text-muted-foreground">
                  {isDraft(po.status)
                    ? 'Not on order (draft)'
                    : po.status === 'cancelled'
                      ? 'Not on order (cancelled)'
                      : 'Not on order (nothing outstanding)'}
                </span>
              )}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <PurchaseOrderNavigation purchaseOrderId={id} />
              {backLink}
            </div>
          </div>
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4">
          <Field label="Supplier">{po.supplier_name}</Field>
          {/* No header Warehouse field (captain, 20 Aug): a PO's location is a
              line-level fact - each line's own warehouse renders in the grid below. */}
          <Field label="Order date">{fmtDate(po.order_date)}</Field>
          <Field label="Expected date">{fmtDate(po.expected_date)}</Field>
          <Field label="Total qty">{fmtInt(po.total_qty)}</Field>
          <Field label="Lines">{fmtInt(po.line_count)}</Field>
          {/* What is still coming, shown only when it differs from what the order says -
              on a fully open order the two are equal and a second identical figure is
              noise, while on a part-received or historical order the gap is the answer. */}
          {po.open_qty != null && po.open_qty !== po.total_qty ? (
            <Field label="Still incoming">{fmtInt(po.open_qty)}</Field>
          ) : null}
          <Field label="Source">{SOURCE_LABELS[po.source ?? 'manual']}</Field>
          <Field label="On order">{onOrder ? 'Yes' : 'No'}</Field>
        </div>
      </Card>

      {/* Lines - always rendered, explicit empty state. */}
      <DataGrid
        table={table}
        recordCount={lines.length}
        isLoading={false}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="This purchase order has no lines."
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

      {/* Goods receipt - always rendered, empty state when none. */}
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Goods receipt</CardTitle>
          </CardHeading>
        </CardHeader>
        <div className="p-4">
          {po.gr_reference ? (
            <div className="flex items-center gap-2 text-sm">
              <PackageCheck className="size-4 text-scm-incoming" />
              <span className="font-medium">{po.gr_reference}</span>
              <span className="text-muted-foreground">- received in full</span>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {isDraft(po.status)
                ? 'Confirm this purchase order before a goods receipt can be created.'
                : 'No goods receipt yet. Create one from the purchase orders list to record what arrived.'}
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
