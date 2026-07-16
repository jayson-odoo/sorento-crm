'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  getCoreRowModel,
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
import { usePurchaseOrder } from '../../../hooks/usePurchaseOrders';
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
  cancelled: { variant: 'secondary', label: 'Cancelled' },
};

const statusBadge = (s: string): BadgeDef =>
  STATUS_BADGE[s as PurchaseOrderStatus] ?? { variant: 'secondary', label: titleCase(s) };

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

  const lines = useMemo<PurchaseOrderLine[]>(() => data?.lines ?? [], [data]);

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
        accessorKey: 'qty_ordered',
        header: ({ column }) => <DataGridColumnHeader title="Qty ordered" column={column} />,
        cell: ({ row }) => fmtInt(row.original.qty_ordered),
        size: 130,
        meta: { headerTitle: 'Qty ordered', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'qty_received',
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

  const backLink = (
    <Button variant="outline" size="sm" asChild className="w-fit gap-1.5">
      <Link href="/scm/purchase-orders">
        <ArrowLeft className="size-4" />
        Back to purchase orders
      </Link>
    </Button>
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        {backLink}
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        {backLink}
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
      {backLink}

      {/* Summary — always rendered. */}
      <Card>
        <CardHeader className="block">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <CardTitle className="text-lg">{po.po_number}</CardTitle>
              <Badge variant={s.variant} appearance="light">
                {s.label}
              </Badge>
              {onOrder ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-scm-incoming">
                  <CheckCircle2 className="size-3.5" /> On order
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">Not on order (draft)</span>
              )}
            </div>
          </div>
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4">
          <Field label="Supplier">{po.supplier_name}</Field>
          <Field label="Warehouse">{po.warehouse_name ?? '—'}</Field>
          <Field label="Order date">{fmtDate(po.order_date)}</Field>
          <Field label="Expected date">{fmtDate(po.expected_date)}</Field>
          <Field label="Total qty">{fmtInt(po.total_qty)}</Field>
          <Field label="Lines">{fmtInt(po.line_count)}</Field>
          <Field label="Source">
            {po.source === 'recommendation' ? 'Reorder recommendation' : 'Manual'}
          </Field>
          <Field label="On order">{onOrder ? 'Yes' : 'No'}</Field>
        </div>
      </Card>

      {/* Lines — always rendered, explicit empty state. */}
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

      {/* Goods receipt — always rendered, empty state when none. */}
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
              <span className="text-muted-foreground">— received in full</span>
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
