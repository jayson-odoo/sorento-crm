'use client';

import { useMemo, useRef } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import Link from 'next/link';
import { Boxes } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { EM_DASH, fmtDate, fmtQty } from '../../../lib/format';
import type {
  PackingListPlacement,
  ProformaInvoiceDetail,
} from '../../../services/proformaInvoiceService';

/** Keyed off the read permission plus a stable id, the same convention the Lines and
 *  Packing grids on this page use. */
const LISTING_KEY = 'scm.dashboard.view::proforma-invoice-packing-lists';

/** One frozen empty array, so the grid's `data` identity is stable before anything is
 *  converted (`data-grid.stable-data.inventory.test.ts`). */
const NO_ROWS: PackingListPlacement[] = [];

/**
 * Which packing lists this invoice's goods went into (S2 follow-up, ruling 26).
 *
 * A plain list of containers: the number that opens it, what state it is in, which box,
 * how much of this invoice it carries and when it was drafted. Nothing about what is still
 * to place - that question is the convert dialog's own table, and a line that cannot go at
 * all says so in the Lines tab's Matched column, where the fix for it also lives.
 */
export function ProformaInvoicePackingListsTab({
  invoice,
  onConvert,
  convertLabel,
}: {
  invoice: ProformaInvoiceDetail;
  /** Omitted when this invoice cannot be converted (no permission, nothing left). */
  onConvert?: () => void;
  convertLabel: string;
}) {
  const rows = invoice.packing_lists.length ? invoice.packing_lists : NO_ROWS;
  const totalQtyRef = useRef(invoice.total_qty);
  totalQtyRef.current = invoice.total_qty;

  const columns = useMemo<ColumnDef<PackingListPlacement>[]>(
    () => [
      {
        accessorKey: 'shipment_number',
        header: ({ column }) => <DataGridColumnHeader title="Number" column={column} />,
        cell: ({ row }) => (
          <Link
            href={`/procurement-management/packing-lists/${row.original.shipment_id}`}
            className="block truncate font-medium text-primary hover:underline"
            title={row.original.shipment_number ?? 'Draft'}
          >
            {row.original.shipment_number ?? 'Draft'}
          </Link>
        ),
        size: 160,
        meta: { headerTitle: 'Number' },
      },
      {
        accessorKey: 'shipment_status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) =>
          row.original.shipment_status ? (
            <Badge variant="secondary" appearance="light">
              {row.original.shipment_status}
            </Badge>
          ) : (
            EM_DASH
          ),
        size: 130,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'container_number',
        header: ({ column }) => <DataGridColumnHeader title="Container" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.container_number ?? undefined}>
            {row.original.container_number || EM_DASH}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Container' },
      },
      {
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Placed qty" column={column} />,
        cell: ({ row }) => `${fmtQty(row.original.qty)} of ${fmtQty(totalQtyRef.current)}`,
        size: 120,
        meta: {
          headerTitle: 'Placed qty',
          headerClassName: 'text-end',
          cellClassName: 'text-end tabular-nums',
        },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created at" column={column} />,
        cell: ({ row }) =>
          row.original.created_at ? fmtDate(row.original.created_at) : EM_DASH,
        size: 120,
        meta: { headerTitle: 'Created at' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.shipment_id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="Nothing from this invoice is in a packing list yet."
      emptyAction={
        onConvert ? (
          <Button variant="outline" size="sm" className="gap-1.5" onClick={onConvert}>
            <Boxes className="size-4" />
            {convertLabel}
          </Button>
        ) : undefined
      }
      listingKey={LISTING_KEY}
    >
      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>Packing lists</CardTitle>
          </CardHeading>
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
      </Card>
    </DataGrid>
  );
}

export default ProformaInvoicePackingListsTab;
