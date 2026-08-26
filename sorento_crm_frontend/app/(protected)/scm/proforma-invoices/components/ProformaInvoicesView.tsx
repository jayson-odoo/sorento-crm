'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';
import { FileText, LoaderCircle, Trash2, Upload } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useHasPermission } from '@/hooks/usePermissions';
import { useFulfilmentSuppliers } from '../../hooks/useFulfilment';
import {
  useBulkDeleteProformaInvoices,
  useConvertProformaInvoicesToDraftShipment,
  useDeleteProformaInvoice,
  useProformaInvoices,
} from '../../hooks/useProformaInvoices';
import { BulkActionsMenu } from '../../components/BulkActionsMenu';
import type { ProformaInvoiceListRow } from '../../services/proformaInvoiceService';
import { EM_DASH, fmtDate, fmtInt, fmtSupplierCost } from '../../lib/format';
import { OverCapacityDialog } from './OverCapacityDialog';
import { ProformaUploadDialog } from './ProformaUploadDialog';
import { buildProformaBulkActions } from '../lib/proformaBulkActions';

/**
 * What is on file per supplier: the priced document the loading plan and the eventual
 * PI-vs-PO check both read from. Upload writes it; nothing here edits a line once it has
 * landed - a proforma is the supplier's document, and the correction path is re-upload
 * (updates in place, AC-P1.4) or delete.
 *
 * Two bulk actions share ONE selection (the captain's ask): "Convert N to draft shipment"
 * drafts one inbound shipment from every selected invoice, any suppliers - a container is
 * routinely several factories' PIs, so multi-select is the natural pick-more-than-one
 * surface for it. "Delete N" hard-deletes, refusing (named, not silently skipped) any
 * invoice already converted - same shape as the PO book's bulk delete.
 */

const UPLOAD_PERMISSION = 'scm.proforma_invoice.upload';
const CONVERT_PERMISSION = 'scm.reorder.run';

export function ProformaInvoicesView() {
  const router = useRouter();
  const suppliers = useFulfilmentSuppliers();
  const canUpload = useHasPermission(UPLOAD_PERMISSION);
  const canConvert = useHasPermission(CONVERT_PERMISSION);
  const [supplierId, setSupplierId] = useState<string | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleteRow, setDeleteRow] = useState<ProformaInvoiceListRow | null>(null);
  const [bulkDeleteIds, setBulkDeleteIds] = useState<string[] | null>(null);
  const [overCapacity, setOverCapacity] = useState<string | null>(null);
  const [overrideReason, setOverrideReason] = useState('');

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
    setRowSelection({});
  }, [supplierId]);

  const { data, isLoading } = useProformaInvoices(supplierId, {
    limit: pagination.pageSize,
    offset: pagination.pageIndex * pagination.pageSize,
  });
  const deleteInvoice = useDeleteProformaInvoice();
  const convertToDraftShipment = useConvertProformaInvoicesToDraftShipment();
  const bulkDeleteInvoices = useBulkDeleteProformaInvoices();

  const rows = useMemo<ProformaInvoiceListRow[]>(() => data?.data ?? [], [data]);

  const columns = useMemo<ColumnDef<ProformaInvoiceListRow>[]>(
    () => [
      buildSelectColumn<ProformaInvoiceListRow>({
        rowLabel: (row) => `Select ${row.original.pi_number}`,
      }),
      {
        accessorKey: 'pi_number',
        header: ({ column }) => <DataGridColumnHeader title="PI number" column={column} />,
        // A superseded revision says so HERE rather than only on its detail page: it is
        // still listed, still readable, and picking it for a convert is refused - so the
        // list has to explain the refusal before it happens (AC-E7).
        cell: ({ row }) => (
          <div className="flex flex-col gap-0.5">
            <Link
              href={`/scm/proforma-invoices/${row.original.id}`}
              className="truncate font-medium text-primary hover:underline"
              title={`Open ${row.original.pi_number}`}
            >
              {row.original.pi_number}
            </Link>
            {row.original.revision_count > 1 ? (
              <span className="text-xs text-muted-foreground">
                Revision {row.original.revision_no} of {row.original.revision_count}
                {row.original.status === 'superseded' ? ' - superseded' : ''}
              </span>
            ) : null}
          </div>
        ),
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'PI number' },
      },
      {
        id: 'supplier',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="truncate" title={row.original.supplier_name ?? undefined}>
              {row.original.supplier_name ?? EM_DASH}
            </span>
            {row.original.supplier_code ? (
              <span className="text-xs text-muted-foreground">{row.original.supplier_code}</span>
            ) : null}
          </div>
        ),
        size: 200,
        enableSorting: false,
        meta: { headerTitle: 'Supplier' },
      },
      {
        accessorKey: 'invoice_date',
        header: ({ column }) => <DataGridColumnHeader title="Invoice date" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{fmtDate(row.original.invoice_date)}</span>
        ),
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Invoice date' },
      },
      {
        accessorKey: 'container_no',
        header: ({ column }) => <DataGridColumnHeader title="Container" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.container_no ?? undefined}>
            {row.original.container_no ?? EM_DASH}
          </span>
        ),
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Container' },
      },
      {
        accessorKey: 'bl_no',
        header: ({ column }) => <DataGridColumnHeader title="BL" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.bl_no ?? undefined}>
            {row.original.bl_no ?? EM_DASH}
          </span>
        ),
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'BL' },
      },
      {
        accessorKey: 'currency',
        header: ({ column }) => <DataGridColumnHeader title="Currency" column={column} />,
        cell: ({ row }) => row.original.currency ?? EM_DASH,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Currency' },
      },
      {
        accessorKey: 'line_count',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        cell: ({ row }) => fmtInt(row.original.line_count),
        size: 80,
        enableSorting: false,
        meta: { headerTitle: 'Lines', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'total_amount',
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        cell: ({ row }) => fmtSupplierCost(row.original.total_amount, row.original.currency),
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Total', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'uploaded',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="text-muted-foreground">{fmtDate(row.original.created_at)}</span>
            {row.original.uploaded_by ? (
              <span className="truncate text-xs text-muted-foreground" title={row.original.uploaded_by}>
                {row.original.uploaded_by}
              </span>
            ) : null}
          </div>
        ),
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Uploaded' },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex items-center justify-end">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1 px-2 text-xs text-destructive hover:text-destructive"
              onClick={() => setDeleteRow(row.original)}
            >
              <Trash2 className="size-3.5" />
              Delete
            </Button>
          </div>
        ),
        size: 90,
        enableHiding: false,
        enableSorting: false,
      },
    ],
    [],
  );

  const total = data?.total ?? 0;

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, rowSelection },
    onPaginationChange: setPagination,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const selectedIds = table.getSelectedRowModel().rows.map((r) => r.original.id);

  const runConvert = async (reason?: string) => {
    if (!selectedIds.length) return;
    try {
      const result = await convertToDraftShipment.mutateAsync({
        invoiceIds: selectedIds,
        overrideReason: reason,
      });
      setOverCapacity(null);
      setOverrideReason('');
      table.resetRowSelection();
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
      // An over-capacity refusal is a question, not a failure: it names the volume and the
      // capacity and asks whether to load the box anyway (AC-E5).
      const code = (e as { code?: string | null })?.code ?? null;
      const message = e instanceof Error ? e.message : 'Failed to draft a shipment';
      if (code === 'over_capacity') {
        setOverCapacity(message);
        return;
      }
      toast.error(message);
    }
  };

  const runBulkDelete = async () => {
    if (!bulkDeleteIds) return;
    try {
      const res = await bulkDeleteInvoices.mutateAsync(bulkDeleteIds);
      table.resetRowSelection();
      const deletedMsg = `Deleted ${res.deleted} proforma invoice${res.deleted === 1 ? '' : 's'}`;
      if (res.blocked.length > 0) {
        const names = res.blocked
          .map((b) => `${b.pi_number} (already converted to ${b.shipment_number ?? 'a shipment'})`)
          .join(', ');
        toast.error(`${deletedMsg} - could not delete: ${names}`);
      } else {
        toast.success(deletedMsg);
      }
      setBulkDeleteIds(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete proforma invoices');
    }
  };

  const bulkActions = buildProformaBulkActions(
    { selectedCount: selectedIds.length },
    { onConvert: () => void runConvert(), onDelete: () => setBulkDeleteIds(selectedIds) },
  ).filter((a) => {
    if (a.key === 'bulk-convert') return canConvert;
    if (a.key === 'bulk-delete') return canUpload;
    return true;
  });

  return (
    <div className="space-y-3">
      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No proforma invoice read yet. Upload the supplier's proforma workbook to hold its priced lines."
      >
        <Card>
          <CardHeader className="block py-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0">
                <Label className="text-xs text-muted-foreground" htmlFor="proforma-supplier-filter">
                  Supplier
                </Label>
                <SearchableSelect
                  id="proforma-supplier-filter"
                  className="mt-1 w-72"
                  value={supplierId ?? ''}
                  onChange={(v: string) => setSupplierId(v || null)}
                  options={suppliers.data ?? []}
                  placeholder="All suppliers"
                  clearable
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {selectedIds.length > 0 ? (
                  <>
                    <span className="text-xs text-muted-foreground">
                      {fmtInt(selectedIds.length)} selected
                    </span>
                    <BulkActionsMenu actions={bulkActions} />
                  </>
                ) : null}
                {canUpload ? (
                  <Button onClick={() => setUploadOpen(true)}>
                    <Upload className="size-4" />
                    Upload proforma invoice
                  </Button>
                ) : null}
              </div>
            </div>
          </CardHeader>
          {!isLoading && rows.length === 0 ? (
            <div className="flex flex-col items-center gap-3 p-10 text-center">
              <FileText className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">
                {supplierId ? 'No proforma invoice on file for this supplier.' : 'No proforma invoice read yet.'}
              </p>
              {canUpload ? (
                <Button variant="outline" size="sm" onClick={() => setUploadOpen(true)}>
                  <Upload className="size-4" />
                  Upload proforma invoice
                </Button>
              ) : null}
            </div>
          ) : (
            <>
              <CardTable>
                <ScrollArea>
                  <DataGridTable />
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              </CardTable>
              <CardFooter>
                <DataGridPagination />
              </CardFooter>
            </>
          )}
        </Card>
      </DataGrid>

      {/* No `onApplied` auto-close here: the dialog's own result summary ("Created N,
          updated M") would never paint if the parent closed it the instant the apply
          finished. The dialog invalidates the list on apply regardless of this prop; the
          user dismisses it themselves once they have read the result (footer flips
          Cancel -> Close, S8). */}
      <ProformaUploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />

      <OverCapacityDialog
        message={overCapacity}
        reason={overrideReason}
        onReasonChange={setOverrideReason}
        onCancel={() => setOverCapacity(null)}
        onConfirm={() => void runConvert(overrideReason.trim())}
        pending={convertToDraftShipment.isPending}
      />

      <ConfirmDeleteDialog
        open={!!deleteRow}
        onOpenChange={(o) => !o && setDeleteRow(null)}
        title="Confirm delete"
        description={
          deleteRow
            ? `This action cannot be undone. This deletes proforma invoice ${deleteRow.pi_number} and every line it carries.`
            : ''
        }
        onDelete={async () => {
          if (deleteRow) await deleteInvoice.mutateAsync(deleteRow.id);
        }}
        successMessage="Proforma invoice deleted."
      />

      {/* Bulk delete - AlertDialog + destructive button per ADR-PRODUCT-STANDARDS, same
          shape as the PO book's bulk delete. Reports which invoices were BLOCKED (already
          converted to a draft shipment) rather than silently deleting only some. */}
      <AlertDialog open={!!bulkDeleteIds} onOpenChange={(o) => !o && setBulkDeleteIds(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              {bulkDeleteIds
                ? `Delete ${fmtInt(bulkDeleteIds.length)} proforma invoice${
                    bulkDeleteIds.length === 1 ? '' : 's'
                  }? This action cannot be undone.`
                : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button
              variant="outline"
              onClick={() => setBulkDeleteIds(null)}
              disabled={bulkDeleteInvoices.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={runBulkDelete}
              disabled={bulkDeleteInvoices.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {bulkDeleteInvoices.isPending ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : null}
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default ProformaInvoicesView;
