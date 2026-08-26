'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';
import { ArrowLeft, Boxes, Download, FileText, Pencil, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle, CardToolbar } from '@/components/ui/card';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { useContainerSizes } from '../../../hooks/useFulfilment';
import {
  useConvertProformaInvoicesToDraftShipment,
  useDeleteProformaInvoiceLine,
  useProformaInvoice,
  useUpdateProformaInvoice,
  useUpdateProformaInvoiceLine,
} from '../../../hooks/useProformaInvoices';
import { EM_DASH, fmtDate, fmtQty, fmtSupplierCost, fmtTrimmedDecimal } from '../../../lib/format';
import {
  downloadProformaInvoiceExport,
  type ProformaInvoiceDetail as ProformaInvoiceDetailPayload,
  type ProformaInvoiceLine,
} from '../../../services/proformaInvoiceService';
import OverCapacityDialog from '../../components/OverCapacityDialog';
import ProformaInvoiceNavigation from '../../components/ProformaInvoiceNavigation';
import { ProformaRevisionsCard } from './ProformaRevisionsCard';
import { ProformaVolumeFill } from './ProformaVolumeFill';

const CONVERT_PERMISSION = 'scm.reorder.run';
const ADJUST_PERMISSION = 'scm.proforma_invoice.upload';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

/**
 * What one line takes up per unit, however the supplier stated it.
 *
 * The document states a per-unit volume and a total, and only sometimes both; a line whose
 * quantity we then trim has to keep answering "how much room does it take", so the per-unit
 * figure is the one that survives an adjustment and the total is derived from it. Null when
 * neither was stated, which is the Kailu shape and reads as unmeasured rather than as zero.
 */
function perUnitCbm(line: ProformaInvoiceLine): number | null {
  if (line.cbm_per_unit != null) return line.cbm_per_unit;
  if (line.cbm_total != null && line.qty) return line.cbm_total / line.qty;
  return null;
}

export function ProformaInvoiceDetail({ id }: { id: string }) {
  const router = useRouter();
  const canConvert = useHasPermission(CONVERT_PERMISSION);
  const canAdjust = useHasPermission(ADJUST_PERMISSION);
  const { data, isLoading, isError } = useProformaInvoice(id);
  const containerSizes = useContainerSizes();
  const convertToDraftShipment = useConvertProformaInvoicesToDraftShipment();
  const updateLine = useUpdateProformaInvoiceLine(id);
  const removeLineMutation = useDeleteProformaInvoiceLine(id);
  const updateInvoice = useUpdateProformaInvoice(id);

  const [editing, setEditing] = useState(false);
  const [draftQty, setDraftQty] = useState<Record<string, string>>({});
  const [draftSizeId, setDraftSizeId] = useState<string | null>(null);
  const [lineToRemove, setLineToRemove] = useState<ProformaInvoiceLine | null>(null);
  const [overCapacity, setOverCapacity] = useState<string | null>(null);
  const [overrideReason, setOverrideReason] = useState('');
  const [saving, setSaving] = useState(false);

  const lines = useMemo<ProformaInvoiceLine[]>(() => data?.lines ?? [], [data]);
  const superseded = data?.status === 'superseded';
  // A converted invoice is frozen: the goods are already drafted onto a shipment, and
  // trimming the document afterwards would leave the two disagreeing with nothing on screen
  // saying which one the container was loaded from.
  const converted = (data?.converted_shipments?.length ?? 0) > 0;
  const canEdit = canAdjust && !superseded && !converted;

  // Editing starts from whatever the server currently holds, every time - a draft left over
  // from a cancelled edit would silently re-apply the quantity the user backed out of.
  const beginEdit = () => {
    setDraftQty(
      Object.fromEntries(lines.map((ln) => [ln.id, ln.qty == null ? '' : String(ln.qty)])),
    );
    setDraftSizeId(data?.container_size_id ?? null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraftQty({});
  };

  // A line removed mid-edit leaves the draft holding a key for a line that no longer exists,
  // and a line the server re-numbered leaves the draft missing one. Re-sync on every payload
  // change rather than trusting the draft to still describe the invoice.
  useEffect(() => {
    if (!editing) return;
    setDraftQty((prev) =>
      Object.fromEntries(
        lines.map((ln) => [ln.id, prev[ln.id] ?? (ln.qty == null ? '' : String(ln.qty))]),
      ),
    );
  }, [editing, lines]);

  const effectiveQty = (line: ProformaInvoiceLine): number => {
    if (!editing) return line.qty ?? 0;
    const raw = draftQty[line.id];
    const parsed = Number(raw);
    return raw === undefined || raw === '' || Number.isNaN(parsed) ? (line.qty ?? 0) : parsed;
  };

  // Live while editing (the journey's "fill bar live"), and the server's own figures once
  // saved (AC-E3) - the two agree because both multiply the per-unit volume by the quantity.
  const volume = useMemo(() => {
    if (!editing) {
      return {
        total: data?.total_cbm ?? null,
        unmeasured: data?.unmeasured_lines ?? 0,
      };
    }
    let total: number | null = null;
    let unmeasured = 0;
    for (const line of lines) {
      const per = perUnitCbm(line);
      if (per == null) {
        unmeasured += 1;
        continue;
      }
      total = (total ?? 0) + per * effectiveQty(line);
    }
    return { total, unmeasured };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, lines, draftQty, data?.total_cbm, data?.unmeasured_lines]);

  const containerCbm = useMemo(() => {
    if (!editing) return data?.container_cbm ?? null;
    const chosen = (containerSizes.data ?? []).find((s) => s.id === draftSizeId);
    if (chosen) return chosen.cbm;
    const fallback = (containerSizes.data ?? []).find((s) => s.is_default);
    return fallback?.cbm ?? data?.container_cbm ?? null;
  }, [editing, draftSizeId, containerSizes.data, data?.container_cbm]);

  const containerLabel = useMemo(() => {
    if (!editing) return data?.container_size_code ?? null;
    const chosen = (containerSizes.data ?? []).find((s) => s.id === draftSizeId);
    if (chosen) return chosen.code;
    const fallback = (containerSizes.data ?? []).find((s) => s.is_default);
    return fallback?.code ?? data?.container_size_code ?? null;
  }, [editing, draftSizeId, containerSizes.data, data?.container_size_code]);

  const containerOptions = useMemo(
    () =>
      (containerSizes.data ?? []).map((s) => ({
        value: s.id,
        label: `${s.code} - ${fmtTrimmedDecimal(s.cbm, 2)} cbm${s.is_default ? ' (default)' : ''}`,
      })),
    [containerSizes.data],
  );

  const saveEdit = async () => {
    if (!data) return;
    setSaving(true);
    try {
      for (const line of lines) {
        const raw = draftQty[line.id];
        if (raw === undefined || raw === '') continue;
        const next = Number(raw);
        if (Number.isNaN(next) || next < 0) {
          toast.error(`${line.item_code}: enter a quantity of zero or more.`);
          setSaving(false);
          return;
        }
        if (next === (line.qty ?? 0)) continue;
        await updateLine.mutateAsync({ lineId: line.id, qty: next });
      }
      if ((draftSizeId ?? null) !== (data.container_size_id ?? null)) {
        await updateInvoice.mutateAsync({ container_size_id: draftSizeId ?? null });
      }
      setEditing(false);
      setDraftQty({});
      toast.success('Proforma invoice saved.');
    } catch {
      // The mutation hooks already toast the message; the edit stays open so the operator
      // can see which figure was refused rather than losing every other change with it.
    } finally {
      setSaving(false);
    }
  };

  const runConvert = async (reason?: string) => {
    try {
      const result = await convertToDraftShipment.mutateAsync({
        invoiceIds: [id],
        overrideReason: reason,
      });
      setOverCapacity(null);
      setOverrideReason('');
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
      const code = (e as { code?: string | null })?.code ?? null;
      const message = e instanceof Error ? e.message : 'Failed to draft a shipment';
      if (code === 'over_capacity') {
        setOverCapacity(message);
        return;
      }
      toast.error(message);
    }
  };

  const runExport = async () => {
    try {
      await downloadProformaInvoiceExport(id, data?.pi_number);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to export the proforma invoice');
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
        size: 200,
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'qty',
        accessorFn: (line) => line.qty ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        // View and edit in the SAME place: the input replaces the number where the number
        // was, and the supplier's own figure sits under both so the comparison never moves.
        cell: ({ row }) => {
          const line = row.original;
          const differs =
            line.supplier_qty != null && line.qty != null && line.supplier_qty !== line.qty;
          return (
            <div className="flex flex-col items-end gap-0.5">
              {editing ? (
                <Input
                  type="number"
                  min={0}
                  value={draftQty[line.id] ?? ''}
                  onChange={(e) =>
                    setDraftQty((prev) => ({ ...prev, [line.id]: e.target.value }))
                  }
                  className="h-8 w-24 text-right tabular-nums"
                  aria-label={`Quantity for ${line.item_code}`}
                />
              ) : (
                <span>{fmtQty(line.qty)}</span>
              )}
              {differs ? (
                <span className="text-2xs text-muted-foreground">
                  Supplier: {fmtQty(line.supplier_qty)}
                </span>
              ) : null}
            </div>
          );
        },
        size: 130,
        meta: { headerTitle: 'Qty', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UoM" column={column} />,
        cell: ({ row }) => row.original.uom ?? EM_DASH,
        size: 70,
        meta: { headerTitle: 'UoM' },
      },
      {
        id: 'cartons',
        accessorFn: (line) => line.cartons ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Cartons" column={column} />,
        cell: ({ row }) =>
          row.original.cartons == null ? EM_DASH : fmtQty(row.original.cartons),
        size: 90,
        meta: { headerTitle: 'Cartons', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'cbm_per_unit',
        accessorFn: (line) => line.cbm_per_unit ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="CBM / unit" column={column} />,
        cell: ({ row }) =>
          row.original.cbm_per_unit == null
            ? EM_DASH
            : fmtTrimmedDecimal(row.original.cbm_per_unit, 3),
        size: 100,
        meta: { headerTitle: 'CBM / unit', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'cbm_total',
        accessorFn: (line) => line.cbm_total ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Total CBM" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          const per = perUnitCbm(line);
          const shown = editing && per != null ? per * effectiveQty(line) : line.cbm_total;
          return shown == null ? EM_DASH : fmtTrimmedDecimal(shown, 2);
        },
        size: 100,
        meta: { headerTitle: 'Total CBM', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
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
        size: 120,
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
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Went to' },
      },
      {
        id: 'line_actions',
        header: '',
        cell: ({ row }) =>
          editing ? (
            <div className="flex items-center justify-end">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1 px-2 text-xs text-destructive hover:text-destructive"
                onClick={() => setLineToRemove(row.original)}
              >
                <Trash2 className="size-3.5" />
                Remove
              </Button>
            </div>
          ) : null,
        size: 100,
        enableHiding: false,
        enableSorting: false,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data?.currency, editing, draftQty],
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

  const invoice: ProformaInvoiceDetailPayload = data;

  return (
    <div className="space-y-4">
      {/* Summary - always rendered, all read-only metadata (never inside a tab body). */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="text-lg">{invoice.pi_number}</CardTitle>
              {invoice.currency ? <Badge variant="secondary">{invoice.currency}</Badge> : null}
              {invoice.revision_count > 1 ? (
                <Badge variant="secondary" appearance="light">
                  Revision {invoice.revision_no} of {invoice.revision_count}
                </Badge>
              ) : null}
              {superseded ? (
                <Badge variant="secondary" appearance="light">
                  Superseded
                </Badge>
              ) : null}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {editing ? (
                <>
                  <Button size="sm" onClick={() => void saveEdit()} disabled={saving}>
                    Save
                  </Button>
                  <Button variant="outline" size="sm" onClick={cancelEdit} disabled={saving}>
                    <X className="size-4" />
                    Cancel
                  </Button>
                </>
              ) : (
                <>
                  {canEdit ? (
                    <Button variant="outline" size="sm" className="gap-1.5" onClick={beginEdit}>
                      <Pencil className="size-4" />
                      Edit
                    </Button>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => void runExport()}
                  >
                    <Download className="size-4" />
                    Export adjusted PI
                  </Button>
                  {!converted && !superseded && canConvert ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => void runConvert()}
                      disabled={convertToDraftShipment.isPending}
                    >
                      <Boxes className="size-4" />
                      Convert to draft shipment
                    </Button>
                  ) : null}
                  <ProformaInvoiceNavigation invoiceId={id} />
                  {backLink}
                </>
              )}
            </div>
          </div>
        </CardHeader>
        <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4">
          <Field label="Supplier">
            {invoice.supplier_name ?? EM_DASH}
            {invoice.supplier_code ? (
              <span className="ms-1 font-normal text-muted-foreground">
                ({invoice.supplier_code})
              </span>
            ) : null}
          </Field>
          <Field label="Invoice date">{fmtDate(invoice.invoice_date)}</Field>
          <Field label="Container">{invoice.container_no ?? EM_DASH}</Field>
          <Field label="BL">{invoice.bl_no ?? EM_DASH}</Field>
          <Field label="Total">{fmtSupplierCost(invoice.total_amount, invoice.currency)}</Field>
          <Field label="Lines">{invoice.line_count}</Field>
          {/* Same slot in both views: the value becomes a select where the value was. */}
          <div className="flex flex-col gap-0.5">
            <Label className="text-xs font-normal text-muted-foreground" htmlFor="pi-container-size">
              Container size
            </Label>
            {editing ? (
              <SearchableSelect
                id="pi-container-size"
                className="mt-0.5"
                size="sm"
                value={draftSizeId ?? ''}
                onChange={(v: string) => setDraftSizeId(v || null)}
                options={containerOptions}
                placeholder={containerLabel ? `${containerLabel} (default)` : 'Default size'}
                clearable
              />
            ) : (
              <span className="text-sm font-medium">
                {invoice.container_size_code ?? EM_DASH}
                {invoice.container_cbm != null ? (
                  <span className="ms-1 font-normal text-muted-foreground">
                    {fmtTrimmedDecimal(invoice.container_cbm, 2)} cbm
                  </span>
                ) : null}
              </span>
            )}
          </div>
          <Field label="Source file">{invoice.source_ref ?? EM_DASH}</Field>
          <Field label="Uploaded by">{invoice.uploaded_by ?? EM_DASH}</Field>
          <Field label="Uploaded on">{fmtDate(invoice.created_at)}</Field>
          <Field label="Adjusted by">
            {invoice.adjusted_by ? (
              <>
                {invoice.adjusted_by}
                <span className="ms-1 font-normal text-muted-foreground">
                  {fmtDate(invoice.adjusted_at)}
                </span>
              </>
            ) : (
              EM_DASH
            )}
          </Field>
          <Field label="Draft shipment">
            {invoice.converted_shipments.length === 0 ? (
              EM_DASH
            ) : (
              <div className="flex flex-col gap-0.5">
                {invoice.converted_shipments.map((s) => (
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
        <div className="border-t px-4 py-3">
          <span className="text-xs text-muted-foreground">Volume</span>
          <ProformaVolumeFill
            className="mt-1 max-w-xl"
            totalCbm={volume.total}
            containerCbm={containerCbm}
            containerLabel={containerLabel}
            unmeasuredLines={volume.unmeasured}
          />
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
            <CardToolbar>
              {superseded ? (
                <span className="text-xs text-muted-foreground">
                  A superseded revision is read-only.
                </span>
              ) : converted ? (
                <span className="text-xs text-muted-foreground">
                  Already in a packing list, so the quantities are fixed.
                </span>
              ) : null}
            </CardToolbar>
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      </DataGrid>

      {/* Revisions - always rendered with its own empty state, per the CRUD standard. */}
      <ProformaRevisionsCard invoice={invoice} canEdit={canAdjust && !superseded} />

      <ConfirmDeleteDialog
        open={!!lineToRemove}
        onOpenChange={(o) => !o && setLineToRemove(null)}
        title="Remove this line?"
        description={
          lineToRemove
            ? `This removes ${lineToRemove.item_code} from ${invoice.pi_number}. This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (lineToRemove) await removeLineMutation.mutateAsync(lineToRemove.id);
        }}
        successMessage="Line removed."
      />

      <OverCapacityDialog
        message={overCapacity}
        reason={overrideReason}
        onReasonChange={setOverrideReason}
        onCancel={() => setOverCapacity(null)}
        onConfirm={() => void runConvert(overrideReason.trim())}
        pending={convertToDraftShipment.isPending}
      />
    </div>
  );
}

export default ProformaInvoiceDetail;
