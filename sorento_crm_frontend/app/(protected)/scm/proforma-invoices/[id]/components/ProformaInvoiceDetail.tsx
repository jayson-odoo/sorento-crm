'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';
import { ArrowLeft, Boxes, FileText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  useConvertProformaInvoicesToDraftShipment,
  useProformaInvoice,
} from '../../../hooks/useProformaInvoices';
import { EM_DASH, fmtDate, fmtQty, fmtSupplierCost } from '../../../lib/format';
import type { ProformaInvoiceLine } from '../../../services/proformaInvoiceService';
import ProformaInvoiceNavigation from '../../components/ProformaInvoiceNavigation';

const CONVERT_PERMISSION = 'scm.reorder.run';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export function ProformaInvoiceDetail({ id }: { id: string }) {
  const router = useRouter();
  const canConvert = useHasPermission(CONVERT_PERMISSION);
  const { data, isLoading, isError } = useProformaInvoice(id);
  const convertToDraftShipment = useConvertProformaInvoicesToDraftShipment();

  const lines = useMemo<ProformaInvoiceLine[]>(() => data?.lines ?? [], [data]);

  const runConvert = async () => {
    try {
      const result = await convertToDraftShipment.mutateAsync([id]);
      const skippedMsg =
        result.lines_skipped > 0
          ? ` (${result.lines_skipped} line${result.lines_skipped === 1 ? '' : 's'} could not be matched to a product and were skipped)`
          : '';
      toast.success(
        `Draft shipment ${result.shipment_number ?? ''} created with ${result.lines_created} line${
          result.lines_created === 1 ? '' : 's'
        }${skippedMsg}`,
      );
      // The captain's second amendment moves the packing-list-to-SPO journey to the
      // procurement packing-list book, over this same `inbound_shipments` row - so the
      // convert hand-off lands there, by id, rather than on `/scm/incoming`.
      router.push(`/procurement-management/packing-lists/${result.shipment_id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to draft a shipment');
    }
  };

  const columns = useMemo<ColumnDef<ProformaInvoiceLine>[]>(
    () => [
      {
        accessorKey: 'line_no',
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => row.original.line_no,
        size: 50,
        meta: { headerTitle: '#', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item code" column={column} />,
        cell: ({ row }) => (
          <span className="truncate whitespace-pre-line" title={row.original.item_code}>
            {row.original.item_code}
          </span>
        ),
        size: 160,
        meta: { headerTitle: 'Item code' },
      },
      {
        id: 'matched',
        header: ({ column }) => <DataGridColumnHeader title="Matched" column={column} />,
        cell: ({ row }) =>
          row.original.matched ? (
            <div className="flex flex-col">
              <Badge variant="success" appearance="light">
                Matched
              </Badge>
              {row.original.product_code ? (
                <span className="mt-0.5 text-xs text-muted-foreground">
                  {row.original.product_code}
                </span>
              ) : null}
            </div>
          ) : (
            <Badge variant="secondary" appearance="light">
              Not in catalogue
            </Badge>
          ),
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Matched' },
      },
      {
        accessorKey: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.description ?? undefined}>
            {row.original.description ?? EM_DASH}
          </span>
        ),
        size: 220,
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'qty',
        accessorFn: (line) => line.qty ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => fmtQty(row.original.qty),
        size: 90,
        meta: { headerTitle: 'Qty', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UoM" column={column} />,
        cell: ({ row }) => row.original.uom ?? EM_DASH,
        size: 80,
        meta: { headerTitle: 'UoM' },
      },
      {
        id: 'unit_price',
        accessorFn: (line) => line.unit_price ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Unit price" column={column} />,
        cell: ({ row }) => fmtSupplierCost(row.original.unit_price, data?.currency),
        size: 110,
        meta: { headerTitle: 'Unit price', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'amount',
        accessorFn: (line) => line.amount ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
        cell: ({ row }) => fmtSupplierCost(row.original.amount, data?.currency),
        size: 120,
        meta: { headerTitle: 'Amount', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'po_ref',
        header: ({ column }) => <DataGridColumnHeader title="PO ref" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.po_ref ?? undefined}>
            {row.original.po_ref ?? EM_DASH}
          </span>
        ),
        size: 130,
        meta: { headerTitle: 'PO ref' },
      },
      {
        id: 'shipment',
        header: ({ column }) => <DataGridColumnHeader title="Went to" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (line.shipment_number && line.shipment_id) {
            return (
              <Link
                href={`/procurement-management/packing-lists/${line.shipment_id}`}
                className="truncate font-medium text-primary hover:underline"
                title={`Open shipment ${line.shipment_number}`}
              >
                {line.shipment_number}
              </Link>
            );
          }
          if (line.unmatched_reason) {
            return (
              <span className="truncate text-muted-foreground" title={line.unmatched_reason}>
                {line.unmatched_reason}
              </span>
            );
          }
          return <span className="text-muted-foreground">{EM_DASH}</span>;
        },
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Went to' },
      },
    ],
    [data?.currency],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const backLink = (
    <Button variant="outline" size="sm" asChild className="w-fit gap-1.5">
      <Link href="/scm/proforma-invoices">
        <ArrowLeft className="size-4" />
        Back to proforma invoices
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
          <FileText className="size-6 text-muted-foreground" />
          <div className="text-sm font-semibold">Proforma invoice not found</div>
          <p className="max-w-md text-sm text-muted-foreground">
            This proforma invoice doesn&apos;t exist, or it was deleted. Head back to the list to
            pick another.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary - always rendered, all read-only metadata (never inside a tab body). */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="text-lg">{data.pi_number}</CardTitle>
              {data.currency ? <Badge variant="secondary">{data.currency}</Badge> : null}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {data.converted_shipments.length === 0 && canConvert ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={runConvert}
                  disabled={convertToDraftShipment.isPending}
                >
                  <Boxes className="size-4" />
                  Convert to draft shipment
                </Button>
              ) : null}
              <ProformaInvoiceNavigation invoiceId={id} />
              {backLink}
            </div>
          </div>
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4">
          <Field label="Supplier">
            {data.supplier_name ?? EM_DASH}
            {data.supplier_code ? (
              <span className="ms-1 font-normal text-muted-foreground">
                ({data.supplier_code})
              </span>
            ) : null}
          </Field>
          <Field label="Invoice date">{fmtDate(data.invoice_date)}</Field>
          <Field label="Container">{data.container_no ?? EM_DASH}</Field>
          <Field label="BL">{data.bl_no ?? EM_DASH}</Field>
          <Field label="Total">{fmtSupplierCost(data.total_amount, data.currency)}</Field>
          <Field label="Lines">{data.line_count}</Field>
          <Field label="Source file">{data.source_ref ?? EM_DASH}</Field>
          <Field label="Uploaded by">{data.uploaded_by ?? EM_DASH}</Field>
          <Field label="Uploaded on">{fmtDate(data.created_at)}</Field>
          <Field label="Draft shipment">
            {data.converted_shipments.length === 0 ? (
              EM_DASH
            ) : (
              <div className="flex flex-col gap-0.5">
                {data.converted_shipments.map((s) => (
                  <Link
                    key={s.shipment_id}
                    href={`/procurement-management/packing-lists/${s.shipment_id}`}
                    className="text-primary hover:underline"
                  >
                    {s.shipment_number ?? EM_DASH}
                  </Link>
                ))}
              </div>
            )}
          </Field>
        </div>
      </Card>

      {/* Lines - always rendered, explicit empty state. */}
      <DataGrid
        table={table}
        recordCount={lines.length}
        isLoading={false}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="This proforma invoice has no lines."
        listingKey=""
      >
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Invoice lines</CardTitle>
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
    </div>
  );
}

export default ProformaInvoiceDetail;
