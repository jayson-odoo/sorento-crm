'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useContainerSizes } from '../../hooks/useFulfilment';
import { useProformaInvoice } from '../../hooks/useProformaInvoices';
import { useProformaInvoicePacking } from '../../hooks/useProformaInvoicePacking';
import { EM_DASH, fmtQty, fmtTrimmedDecimal } from '../../lib/format';
import type { ProformaInvoiceLine } from '../../services/proformaInvoiceService';
import type { ProformaInvoicePackingLine } from '../types/packingLine.types';

/**
 * How much of THIS invoice goes onto a container (AC-F10, Q9), and which container (S5,
 * ruling 1).
 *
 * The per-line quantity question is the PI DETAIL's own: placing part of an invoice is a
 * deliberate act made on one document, so the list converts its whole selection at once and
 * never sees that part of the body (R15, `single` stays null for a multi-invoice convert).
 * The Container size select is common to both surfaces, because both are the SAME write
 * (`convert_to_draft_shipment`) and the box being loaded is a property of the shipment
 * either way.
 */
/** One thing that can go on the container (ruling 25): a supplier packing row, or - for a
 *  line the packing list never mentioned - the invoice line itself. */
interface PlacementRow {
  key: string;
  line: ProformaInvoiceLine;
  /** Null on a bare line: nothing packed it, so the operator types a quantity instead of
   *  ticking a carton. */
  row: ProformaInvoicePackingLine | null;
  qty: number;
  cartons: number | null;
  cbm: number | null;
}

/** One frozen empty array for "nothing to place", so the grid's `data` identity is stable
 *  while the invoice is still loading. */
const NO_ROWS: PlacementRow[] = [];

export function ConvertToPackingListDialog({
  open,
  onOpenChange,
  invoiceIds,
  pending,
  onConvert,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  invoiceIds: string[];
  pending?: boolean;
  onConvert: (args: {
    lineQuantities: Record<string, number>;
    containerSizeId: string | null;
    /** The ticked packing rows (AC-D2b). Absent on an invoice with no packing rows, which
     *  is what tells the convert to place every line's remainder as before. */
    packingRowIds?: string[];
  }) => void;
}) {
  const single = invoiceIds.length === 1 ? invoiceIds[0] : null;
  const { data: invoice, isLoading } = useProformaInvoice(open ? single : null);
  const packing = useProformaInvoicePacking(open ? invoice : undefined);
  const packingRows = useMemo(() => packing.data?.rows ?? [], [packing.data]);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const containerSizes = useContainerSizes();
  const [containerSizeId, setContainerSizeId] = useState<string | null>(null);
  // A packing row placed whole or not at all (S4, AC-D2b) - every MATCHED row starts
  // checked (placed), the same default the plan rules for "default all unplaced" rows on
  // a PI nothing has convertED yet.
  const [placedRowIds, setPlacedRowIds] = useState<Set<string>>(new Set());

  // Re-read on every open: a remainder typed last time describes an invoice that has since
  // moved, and a stale figure here places the wrong quantity silently. The size resets to
  // the tenant default too - a size chosen for a previous convert says nothing about this
  // one.
  useEffect(() => {
    if (!open) return;
    setQuantities({});
    setContainerSizeId(null);
  }, [open]);

  // Rows default to placed the moment they arrive - a checkbox nobody has touched yet
  // reads as "everything goes", which is the plan's own default.
  useEffect(() => {
    if (!open) return;
    setPlacedRowIds(new Set(packingRows.filter((r) => r.match_state === 'matched').map((r) => r.id)));
  }, [open, packingRows]);

  /** Container / seal / BL carried onto the draft (AC-D2c), read off the INVOICE's own
   *  header - the packing document already filled those three there at apply, and the
   *  convert reads the same fields. Nothing is derived here: a second rule on this screen
   *  would be a second answer, and where several invoices disagree it is the convert's own
   *  `header_conflicts` that says so (the response, on the page behind this dialog). */
  const headerCarryOver = {
    container: invoice?.container_no ?? null,
    seal: invoice?.seal_no ?? null,
    bl: invoice?.bl_no ?? null,
  };

  const defaultSize = useMemo(
    () => (containerSizes.data ?? []).find((s) => s.is_default) ?? null,
    [containerSizes.data],
  );
  const containerSizeOptions = useMemo(
    () =>
      (containerSizes.data ?? []).map((s) => ({
        value: s.id,
        label: `${s.code} - ${fmtTrimmedDecimal(s.cbm, 2)} cbm${s.is_default ? ' (default)' : ''}`,
      })),
    [containerSizes.data],
  );

  const placeable = useMemo(
    () => (invoice?.lines ?? []).filter((line) => (line.remaining_qty ?? 0) > 0),
    [invoice],
  );
  /** Finished: every piece of it is on a container. */
  const alreadyPlaced = useMemo(
    () =>
      (invoice?.lines ?? []).filter(
        (line) => (line.remaining_qty ?? 0) <= 0 && (line.placed_qty ?? 0) > 0,
      ),
    [invoice],
  );
  /**
   * ONE row per placement unit (ruling 25): a matched packing row where the invoice line
   * has any, else the line itself. That is the grain the convert writes shipment lines on
   * and the grain the operator ticks, so it is the grain the table shows - the stacked
   * cards this replaced made the reader hold the two together in their head.
   */
  const placementRows = useMemo<PlacementRow[]>(() => {
    const out: PlacementRow[] = [];
    for (const line of placeable) {
      const rows = packingRows.filter(
        (r) => r.proforma_invoice_line_id === line.id && r.match_state === 'matched',
      );
      if (rows.length === 0) {
        out.push({
          key: `line-${line.id}`,
          line,
          row: null,
          qty: line.remaining_qty ?? 0,
          cartons: line.cartons ?? null,
          cbm: line.cbm_total ?? null,
        });
        continue;
      }
      for (const row of rows) {
        out.push({
          key: `row-${row.id}`,
          line,
          row,
          qty: row.qty ?? 0,
          cartons: row.cartons ?? null,
          cbm: row.cbm_total ?? null,
        });
      }
    }
    return out;
  }, [placeable, packingRows]);

  /** Footer totals over what is on screen. Read through a ref by the footer cells, the
   *  same way the Packing tab's own footers do: listing the rows as a `columns` dependency
   *  rebuilds every cell renderer whenever the packing query resolves. */
  const totals = useMemo(
    () => ({
      qty: placementRows.reduce((sum, r) => sum + (r.qty ?? 0), 0),
      cartons: placementRows.reduce((sum, r) => sum + (r.cartons ?? 0), 0),
      cbm: placementRows.reduce((sum, r) => sum + (r.cbm ?? 0), 0),
    }),
    [placementRows],
  );
  const totalsRef = useRef(totals);
  totalsRef.current = totals;

  const columns = useMemo<ColumnDef<PlacementRow>[]>(
    () => [
      {
        id: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.line.item_code}>
            {row.original.line.item_code}
          </span>
        ),
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Code' },
      },
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => (
          <span
            className="block truncate"
            title={row.original.line.product_code ?? row.original.line.description ?? undefined}
          >
            {row.original.line.product_code || row.original.line.description || EM_DASH}
          </span>
        ),
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'invoiced',
        header: ({ column }) => <DataGridColumnHeader title="On invoice" column={column} />,
        cell: ({ row }) => fmtQty(row.original.line.qty),
        size: 90,
        enableSorting: false,
        meta: {
          headerTitle: 'On invoice',
          headerClassName: 'text-end',
          cellClassName: 'text-end tabular-nums',
        },
      },
      {
        id: 'row_no',
        header: ({ column }) => <DataGridColumnHeader title="Row" column={column} />,
        cell: ({ row }) => (row.original.row ? row.original.row.row_no : EM_DASH),
        size: 60,
        enableSorting: false,
        meta: { headerTitle: 'Row', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => fmtQty(row.original.qty),
        size: 80,
        enableSorting: false,
        meta: { headerTitle: 'Qty', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () => fmtQty(totalsRef.current.qty),
      },
      {
        id: 'cartons',
        header: ({ column }) => <DataGridColumnHeader title="Ctns" column={column} />,
        cell: ({ row }) => (row.original.cartons == null ? EM_DASH : fmtQty(row.original.cartons)),
        size: 70,
        enableSorting: false,
        meta: { headerTitle: 'Ctns', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () => fmtQty(totalsRef.current.cartons),
      },
      {
        id: 'cbm',
        header: ({ column }) => <DataGridColumnHeader title="CBM" column={column} />,
        cell: ({ row }) =>
          row.original.cbm == null ? EM_DASH : fmtTrimmedDecimal(row.original.cbm, 3),
        size: 80,
        enableSorting: false,
        meta: { headerTitle: 'CBM', headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        footer: () => fmtTrimmedDecimal(totalsRef.current.cbm, 3),
      },
      {
        id: 'place',
        header: ({ column }) => <DataGridColumnHeader title="Place" column={column} />,
        // A packing row goes whole or not at all (AC-D2b): the supplier packed that many
        // cartons of it and there is no part of a carton. A line the packing list never
        // mentioned has no such grain, so it keeps the quantity it always had.
        cell: ({ row }) =>
          row.original.row ? (
            <Checkbox
              id={`packing-row-${row.original.row.id}`}
              aria-label={`Place row ${row.original.row.row_no} of ${row.original.line.item_code}`}
              checked={placedRowIds.has(row.original.row.id)}
              onCheckedChange={(checked) =>
                setPlacedRowIds((prev) => {
                  const next = new Set(prev);
                  if (checked) next.add(row.original.row!.id);
                  else next.delete(row.original.row!.id);
                  return next;
                })
              }
            />
          ) : (
            <div className="flex items-center gap-1.5">
              <Input
                type="number"
                min={0}
                max={row.original.line.remaining_qty}
                value={quantities[row.original.line.id] ?? String(row.original.line.remaining_qty)}
                onChange={(e) =>
                  setQuantities((prev) => ({ ...prev, [row.original.line.id]: e.target.value }))
                }
                className="h-7 w-20 text-right tabular-nums"
                aria-label={`Quantity to place for ${row.original.line.item_code}`}
              />
              <span className="whitespace-nowrap text-2xs text-muted-foreground">
                of {fmtQty(row.original.line.remaining_qty)} left
              </span>
            </div>
          ),
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Place' },
      },
    ],
    [placedRowIds, quantities],
  );

  const table = useReactTable({
    columns,
    data: placementRows.length ? placementRows : NO_ROWS,
    getRowId: (row) => row.key,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const submit = () => {
    const lineQuantities: Record<string, number> = {};
    for (const line of placeable) {
      const raw = quantities[line.id];
      if (raw === undefined || raw === '') continue;
      const parsed = Number(raw);
      if (Number.isNaN(parsed)) continue;
      lineQuantities[line.id] = parsed;
    }
    // The ticked rows, in the order the grid shows them (AC-D2b). Sent only when this
    // invoice HAS packing rows: an omitted list means "every row not already placed",
    // which is the right default for a PI whose lines carry no rows at all, and the
    // convert route reads it that way. Unticking a row now genuinely leaves it off the
    // draft - the checkboxes were state nothing ever sent.
    const packingRowIds = packingRows
      .filter((r) => r.match_state === 'matched' && placedRowIds.has(r.id))
      .map((r) => r.id);
    onConvert({
      lineQuantities,
      containerSizeId,
      ...(packingRows.length > 0 ? { packingRowIds } : {}),
    });
  };

  const invalid = placeable.some((line) => {
    const raw = quantities[line.id];
    if (raw === undefined || raw === '') return false;
    const parsed = Number(raw);
    return Number.isNaN(parsed) || parsed < 0 || parsed > (line.remaining_qty ?? 0);
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Convert to a packing list</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="convert-container-size" className="text-xs">
              Container size
            </Label>
            <SearchableSelect
              id="convert-container-size"
              size="sm"
              value={containerSizeId ?? ''}
              onChange={(v: string) => setContainerSizeId(v || null)}
              options={containerSizeOptions}
              placeholder={
                defaultSize
                  ? `${defaultSize.code} - ${fmtTrimmedDecimal(defaultSize.cbm, 2)} cbm (default)`
                  : 'Default size'
              }
              clearable
            />
          </div>

          {single && isLoading ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" /> Reading the invoice...
            </p>
          ) : null}

          {single && invoice ? (
            <div className="space-y-2">
              {/* Carried onto the draft (AC-D2c), one compact line - a fact about the
                  invoice's own header, so it is stated whether or not anything is left to
                  place. */}
              {headerCarryOver.container || headerCarryOver.seal || headerCarryOver.bl ? (
                <p className="text-2xs text-muted-foreground">
                  <span className="font-medium text-foreground">Carried onto the draft: </span>
                  Container {headerCarryOver.container ?? EM_DASH}
                  {headerCarryOver.seal ? ` · Seal ${headerCarryOver.seal}` : ''}
                  {headerCarryOver.bl ? ` · BL ${headerCarryOver.bl}` : ''}
                </p>
              ) : null}
              <DataGrid
                table={table}
                recordCount={placementRows.length}
                isLoading={false}
                tableLayout={{ width: 'fixed', columnsResizable: true }}
                emptyMessage={
                  alreadyPlaced.length > 0
                    ? `Every line of ${invoice.pi_number} is already in a packing list.`
                    : `No line of ${invoice.pi_number} can go on a container yet.`
                }
              >
                <DataGridTable />
              </DataGrid>
            </div>
          ) : null}

          {invalid ? (
            <Alert variant="destructive">
              <AlertDescription>
                A quantity cannot be negative, and cannot be more than the line has left.
              </AlertDescription>
            </Alert>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={pending || invalid || (!!single && placeable.length === 0)}
          >
            {pending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Convert
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ConvertToPackingListDialog;
