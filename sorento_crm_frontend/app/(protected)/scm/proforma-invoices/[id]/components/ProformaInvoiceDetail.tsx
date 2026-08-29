'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  Boxes,
  Download,
  FileText,
  GitBranch,
  ListOrdered,
  LoaderCircle,
  PackageCheck,
  Plus,
  Settings,
  SquarePen,
  Trash2,
  Undo2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardHeader,
  CardHeading,
  CardTable,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import { useHasPermission } from '@/hooks/usePermissions';
import { useContainerSizes } from '../../../hooks/useFulfilment';
import { useForgetSupplierCodeMatch } from '../../../hooks/useSupplierCodeAliases';
import {
  useConvertProformaInvoicesToDraftShipment,
  useDeleteProformaInvoice,
  useProformaInvoice,
  useSaveProformaInvoice,
} from '../../../hooks/useProformaInvoices';
import { EM_DASH, fmtDate, fmtQty, fmtSupplierCost, fmtTrimmedDecimal } from '../../../lib/format';
import {
  downloadProformaInvoiceExport,
  type ProformaInvoiceDetail as ProformaInvoiceDetailPayload,
  type ProformaInvoiceLine,
  type ProformaInvoiceLineWrite,
} from '../../../services/proformaInvoiceService';
import ConvertToPackingListDialog from '../../components/ConvertToPackingListDialog';
import MatchToProductDialog from '../../../components/MatchToProductDialog';
import OverCapacityDialog from '../../components/OverCapacityDialog';
import DetailActions from '@/components/common/DetailActions';
import { proformaInvoicesPagerQuery } from '../../../hooks/useProformaInvoices';
import { MarkAsRevisionDialog } from './MarkAsRevisionDialog';
import { ProformaRevisionsCard } from './ProformaRevisionsCard';
import { ProformaVolumeFill } from './ProformaVolumeFill';
import BackToList from '@/components/common/BackToList';

const CONVERT_PERMISSION = 'scm.reorder.run';
const ADJUST_PERMISSION = 'scm.proforma_invoice.upload';

/** Keyed off the read permission plus a stable id, never the record's own path - a 30-line
 *  invoice is read with the same few columns every time and the choice has to survive. */
const LINES_LISTING_KEY = 'scm.dashboard.view::proforma-invoice-lines';

/** How many products a page of the picker asks for. */
const PRODUCT_PAGE_SIZE = 50;

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      {htmlFor ? (
        <Label className="text-xs font-normal text-muted-foreground" htmlFor={htmlFor}>
          {label}
        </Label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

/**
 * One line as the EDIT DRAFT holds it - and, in view mode, as the grid reads it.
 *
 * Both modes render from this one shape on purpose: the columns, their order and their
 * formatting are then written once, and "view and edit are the same layout" cannot rot into
 * two grids that drifted apart. Numbers are STRINGS because that is what an `<input>` holds;
 * an empty string is "not stated", which is not the same as zero.
 */
interface DraftLine {
  /** Stable React key. The server id for a stored line, a local one for an added row. */
  key: string;
  id?: string;
  productId: string | null;
  productCode: string | null;
  itemCode: string;
  description: string;
  qty: string;
  uom: string;
  cartons: string;
  cbmPerUnit: string;
  unitPrice: string;
  netWeight: string;
  grossWeight: string;
  /** Struck through in the draft, and only actually deleted on Save. */
  removed: boolean;
  /** The stored line this row came from - the read-only facts (match provenance, the
   *  supplier's own figures) live there. Null on a row the operator added. */
  source: ProformaInvoiceLine | null;
}

function str(value: number | null | undefined): string {
  return value == null ? '' : String(value);
}

function num(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function toDraft(line: ProformaInvoiceLine): DraftLine {
  return {
    key: line.id,
    id: line.id,
    productId: null,
    productCode: line.product_code,
    itemCode: line.item_code,
    description: line.description ?? '',
    qty: str(line.qty),
    uom: line.uom ?? '',
    cartons: str(line.cartons),
    cbmPerUnit: str(line.cbm_per_unit),
    unitPrice: str(line.unit_price),
    netWeight: str(line.net_weight),
    grossWeight: str(line.gross_weight),
    removed: false,
    source: line,
  };
}

/**
 * What one line takes up per unit, however the supplier stated it.
 *
 * The document states a per-unit volume and a total, and only sometimes both; a line whose
 * quantity we then trim has to keep answering "how much room does it take", so the per-unit
 * figure is the one that survives an adjustment and the total is derived from it.
 */
function perUnitCbm(row: DraftLine): number | null {
  const per = num(row.cbmPerUnit);
  if (per != null) return per;
  const total = row.source?.cbm_total;
  const qty = num(row.qty);
  if (total != null && qty) return total / qty;
  return null;
}

export function ProformaInvoiceDetail({ id }: { id: string }) {
  const router = useRouter();
  const canConvert = useHasPermission(CONVERT_PERMISSION);
  const canAdjust = useHasPermission(ADJUST_PERMISSION);
  const { data, isLoading, isError } = useProformaInvoice(id);
  const containerSizes = useContainerSizes();
  const convertToDraftShipment = useConvertProformaInvoicesToDraftShipment();
  const saveInvoice = useSaveProformaInvoice(id);
  const deleteInvoice = useDeleteProformaInvoice();

  const [tab, setTab] = useState('general');
  const [editing, setEditing] = useState(false);
  const [draftNumber, setDraftNumber] = useState('');
  const [draftSizeId, setDraftSizeId] = useState<string | null>(null);
  const [draftLines, setDraftLines] = useState<DraftLine[]>([]);
  const [overCapacity, setOverCapacity] = useState<string | null>(null);
  const [overrideReason, setOverrideReason] = useState('');
  const [convertOpen, setConvertOpen] = useState(false);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  // Held so an over-capacity refusal can be re-submitted with the reason WITHOUT asking
  // the operator to re-type the split they already chose.
  const [convertArgs, setConvertArgs] = useState<{
    lineQuantities: Record<string, number>;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  /** The line whose supplier code is being answered by hand (R16). */
  const [codeToMatch, setCodeToMatch] = useState<ProformaInvoiceLine | null>(null);
  const [matchToForget, setMatchToForget] = useState<ProformaInvoiceLine | null>(null);
  const forgetMatch = useForgetSupplierCodeMatch();

  const lines = useMemo<ProformaInvoiceLine[]>(() => data?.lines ?? [], [data]);
  const superseded = data?.status === 'superseded';
  // An invoice with ANY of its goods on a shipment is frozen: trimming the document
  // afterwards would leave the two disagreeing with nothing on screen saying which one the
  // container was loaded from. `fullyPlaced` is the narrower question - whether there is
  // anything left to convert (Q9).
  const converted = (data?.converted_shipments?.length ?? 0) > 0;
  const fullyPlaced = data?.placement === 'converted';
  const canEdit = canAdjust && !superseded && !converted;

  /** Product code per id, filled as the picker's pages come back, so an added line can
   *  default its item code from the product without parsing the option's label. */
  const productCodes = useRef<Map<string, { code: string; uom: string }>>(new Map());

  const fetchProducts = useCallback(async (query: string, pageIndex: number) => {
    const res = await getProducts({
      pageIndex,
      pageSize: PRODUCT_PAGE_SIZE,
      sorting: [],
      searchQuery: query,
      status: 'active',
    });
    return (res.data ?? []).map((p) => {
      productCodes.current.set(p.id, {
        code: p.product_code,
        uom: p.base_uom?.uom_code ?? '',
      });
      return {
        value: p.id,
        label: `${p.product_code} - ${p.product_name}`,
        searchText: `${p.product_code} ${p.product_name}`,
      };
    });
  }, []);

  // Editing starts from whatever the server currently holds, every time - a draft left over
  // from a cancelled edit would silently re-apply what the user backed out of.
  const beginEdit = () => {
    if (!data) return;
    setDraftNumber(data.pi_number);
    setDraftSizeId(data.container_size_id ?? null);
    setDraftLines(lines.map(toDraft));
    setEditing(true);
    setTab('general');
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraftLines([]);
  };

  // Nothing to re-sync while editing: the draft IS the document until Save, and a payload
  // that changed underneath it is a conflict the save will report, not something to silently
  // merge into what the operator is typing.
  useEffect(() => {
    if (!editing) setDraftLines([]);
  }, [editing]);

  /** What the grid renders: the draft while editing, the stored lines otherwise. */
  const rows = useMemo<DraftLine[]>(
    () => (editing ? draftLines : lines.map(toDraft)),
    [editing, draftLines, lines],
  );

  const patchLine = (key: string, patch: Partial<DraftLine>) => {
    setDraftLines((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  };

  const addLine = () => {
    setDraftLines((prev) => [
      ...prev,
      {
        key: `new-${Date.now()}-${prev.length}`,
        productId: null,
        productCode: null,
        itemCode: '',
        description: '',
        qty: '',
        uom: '',
        cartons: '',
        cbmPerUnit: '',
        unitPrice: '',
        netWeight: '',
        grossWeight: '',
        removed: false,
        source: null,
      },
    ]);
  };

  // Live while editing (the journey's "fill bar live"), and the server's own figures once
  // saved (AC-E3) - the two agree because both multiply the per-unit volume by the quantity.
  const volume = useMemo(() => {
    if (!editing) {
      return { total: data?.total_cbm ?? null, unmeasured: data?.unmeasured_lines ?? 0 };
    }
    let total: number | null = null;
    let unmeasured = 0;
    for (const row of draftLines) {
      if (row.removed) continue;
      const per = perUnitCbm(row);
      if (per == null) {
        unmeasured += 1;
        continue;
      }
      total = (total ?? 0) + per * (num(row.qty) ?? 0);
    }
    return { total, unmeasured };
  }, [editing, draftLines, data?.total_cbm, data?.unmeasured_lines]);

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
    const number = draftNumber.trim();
    if (!number) {
      toast.error('The invoice needs a number.');
      return;
    }
    const kept = draftLines.filter((r) => !r.removed);
    for (const row of kept) {
      if (!row.itemCode.trim()) {
        toast.error('Every line needs an item code.');
        return;
      }
      const qty = num(row.qty);
      if (qty == null || qty < 0) {
        toast.error(`${row.itemCode || 'A new line'}: enter a quantity of zero or more.`);
        return;
      }
    }
    // ONE call. Rows with an id update, rows without create, and a line the array no longer
    // names is deleted - so the whole draft either lands or none of it does.
    const payload: ProformaInvoiceLineWrite[] = kept.map((row) => ({
      ...(row.id ? { id: row.id } : {}),
      ...(row.productId ? { product_id: row.productId } : {}),
      item_code: row.itemCode.trim(),
      description: row.description.trim() || null,
      qty: num(row.qty) ?? 0,
      uom: row.uom.trim() || null,
      cartons: num(row.cartons),
      cbm_per_unit: num(row.cbmPerUnit),
      unit_price: num(row.unitPrice),
      net_weight: num(row.netWeight),
      gross_weight: num(row.grossWeight),
    }));
    setSaving(true);
    try {
      await saveInvoice.mutateAsync({
        pi_number: number,
        container_size_id: draftSizeId ?? null,
        lines: payload,
      });
      setEditing(false);
      setDraftLines([]);
      toast.success('Proforma invoice saved.');
    } catch {
      // The mutation hook already toasts the message; the edit stays open so the operator
      // can see which figure was refused rather than losing every other change with it.
    } finally {
      setSaving(false);
    }
  };

  const runConvert = async (
    args: { lineQuantities: Record<string, number> } | null,
    reason?: string,
  ) => {
    setConvertArgs(args);
    try {
      const result = await convertToDraftShipment.mutateAsync({
        invoiceIds: [id],
        overrideReason: reason,
        lineQuantities: args?.lineQuantities,
      });
      setOverCapacity(null);
      setOverrideReason('');
      setConvertOpen(false);
      const skippedMsg =
        result.lines_skipped > 0
          ? ` (${result.lines_skipped} line${result.lines_skipped === 1 ? '' : 's'} could not be matched to a product and were skipped)`
          : '';
      // An invoice with nothing left to place is NAMED rather than quietly left out of the
      // count, so the operator can see which of their selection did not move (AC-F7).
      if (result.skipped_invoices?.length) {
        toast.warning(
          `Not converted: ${result.skipped_invoices
            .map((i) => `${i.pi_number} - ${i.reason}`)
            .join('; ')}`,
        );
      }
      toast.success(
        `Packing list ${result.shipment_number ?? ''} created with ${result.lines_created} line${
          result.lines_created === 1 ? '' : 's'
        }${skippedMsg}`,
      );
      router.push(`/procurement-management/packing-lists/${result.shipment_id}`);
    } catch (e) {
      const code = (e as { code?: string | null })?.code ?? null;
      const message = e instanceof Error ? e.message : 'Failed to create the packing list';
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

  const columns = useMemo<ColumnDef<DraftLine>[]>(
    () => [
      {
        id: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item code" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (editing) {
            return (
              <Input
                value={line.itemCode}
                onChange={(e) => patchLine(line.key, { itemCode: e.target.value })}
                className="h-8"
                aria-label={`Item code for line ${row.index + 1}`}
                disabled={line.removed}
              />
            );
          }
          return (
            <span
              className={`truncate whitespace-pre-line ${line.removed ? 'line-through opacity-60' : ''}`}
              title={line.itemCode}
            >
              {line.itemCode}
            </span>
          );
        },
        size: 160,
        meta: { headerTitle: 'Item code' },
      },
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (editing) {
            return (
              // SERVER-SEARCHED and paginated: the catalogue is tens of thousands of rows,
              // and a picker holding one cached page silently hides the item being looked for.
              <SearchableSelect
                value={line.productId ?? ''}
                onChange={(v: string) => {
                  const known = v ? productCodes.current.get(v) : undefined;
                  patchLine(line.key, {
                    productId: v || null,
                    productCode: known?.code ?? line.productCode,
                    // Only where the operator has not written one themselves: the supplier's
                    // own spelling is the document of record, and overwriting it would make
                    // our copy disagree with their paper.
                    ...(known && !line.itemCode.trim() ? { itemCode: known.code } : {}),
                    ...(known?.uom && !line.uom.trim() ? { uom: known.uom } : {}),
                  });
                }}
                fetchOptions={fetchProducts}
                paginated
                pageSize={PRODUCT_PAGE_SIZE}
                selectedOption={
                  line.productId && line.productCode
                    ? { value: line.productId, label: line.productCode }
                    : undefined
                }
                placeholder="Search a product"
                emptyMessage="No product found."
                size="sm"
                clearable
                disabled={line.removed}
              />
            );
          }
          return line.productCode ? (
            <span className="truncate" title={line.productCode}>
              {line.productCode}
            </span>
          ) : (
            <span className="text-muted-foreground">{EM_DASH}</span>
          );
        },
        size: 190,
        enableSorting: false,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          return editing ? (
            <Input
              value={line.description}
              onChange={(e) => patchLine(line.key, { description: e.target.value })}
              className="h-8"
              aria-label={`Description for line ${row.index + 1}`}
              disabled={line.removed}
            />
          ) : (
            <span className="truncate" title={line.description || undefined}>
              {line.description || EM_DASH}
            </span>
          );
        },
        size: 200,
        enableSorting: false,
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        // View and edit in the SAME place: the input replaces the number where the number
        // was, and the supplier's own figure sits under both so the comparison never moves.
        cell: ({ row }) => {
          const line = row.original;
          const supplierQty = line.source?.supplier_qty ?? null;
          const differs = supplierQty != null && String(supplierQty) !== line.qty;
          return (
            <div className="flex flex-col items-end gap-0.5">
              {editing ? (
                <Input
                  type="number"
                  min={0}
                  value={line.qty}
                  onChange={(e) => patchLine(line.key, { qty: e.target.value })}
                  className="h-8 w-24 text-right tabular-nums"
                  aria-label={`Quantity for ${line.itemCode || `line ${row.index + 1}`}`}
                  disabled={line.removed}
                />
              ) : (
                <span>{fmtQty(num(line.qty))}</span>
              )}
              {differs ? (
                <span className="text-2xs text-muted-foreground">
                  Supplier: {fmtQty(supplierQty)}
                </span>
              ) : null}
            </div>
          );
        },
        size: 130,
        enableSorting: false,
        meta: {
          headerTitle: 'Qty',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UOM" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          return editing ? (
            <Input
              value={line.uom}
              onChange={(e) => patchLine(line.key, { uom: e.target.value })}
              className="h-8 w-20"
              aria-label={`UOM for ${line.itemCode || `line ${row.index + 1}`}`}
              disabled={line.removed}
            />
          ) : (
            <span className="truncate" title={line.uom || undefined}>
              {line.uom || EM_DASH}
            </span>
          );
        },
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'UOM' },
      },
      {
        id: 'cartons',
        header: ({ column }) => <DataGridColumnHeader title="Cartons" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          return editing ? (
            <Input
              type="number"
              min={0}
              value={line.cartons}
              onChange={(e) => patchLine(line.key, { cartons: e.target.value })}
              className="h-8 w-20 text-right tabular-nums"
              aria-label={`Cartons for ${line.itemCode || `line ${row.index + 1}`}`}
              disabled={line.removed}
            />
          ) : num(line.cartons) == null ? (
            EM_DASH
          ) : (
            fmtQty(num(line.cartons))
          );
        },
        size: 100,
        enableSorting: false,
        meta: {
          headerTitle: 'Cartons',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'cbm_per_unit',
        header: ({ column }) => <DataGridColumnHeader title="CBM / unit" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          return editing ? (
            <Input
              type="number"
              min={0}
              step="0.001"
              value={line.cbmPerUnit}
              onChange={(e) => patchLine(line.key, { cbmPerUnit: e.target.value })}
              className="h-8 w-24 text-right tabular-nums"
              aria-label={`CBM per unit for ${line.itemCode || `line ${row.index + 1}`}`}
              disabled={line.removed}
            />
          ) : num(line.cbmPerUnit) == null ? (
            EM_DASH
          ) : (
            fmtTrimmedDecimal(num(line.cbmPerUnit), 3)
          );
        },
        size: 110,
        enableSorting: false,
        meta: {
          headerTitle: 'CBM / unit',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'cbm_total',
        header: ({ column }) => <DataGridColumnHeader title="Total CBM" column={column} />,
        // Derived here as well as on the server, from the same two figures, so the fill bar
        // and this cell cannot disagree while the quantity is being typed.
        cell: ({ row }) => {
          const line = row.original;
          const per = perUnitCbm(line);
          const shown = per == null ? line.source?.cbm_total ?? null : per * (num(line.qty) ?? 0);
          return shown == null ? EM_DASH : fmtTrimmedDecimal(shown, 2);
        },
        size: 100,
        enableSorting: false,
        meta: {
          headerTitle: 'Total CBM',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'unit_price',
        header: ({ column }) => <DataGridColumnHeader title="Unit price" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          return editing ? (
            <Input
              type="number"
              min={0}
              step="0.01"
              value={line.unitPrice}
              onChange={(e) => patchLine(line.key, { unitPrice: e.target.value })}
              className="h-8 w-24 text-right tabular-nums"
              aria-label={`Unit price for ${line.itemCode || `line ${row.index + 1}`}`}
              disabled={line.removed}
            />
          ) : (
            fmtSupplierCost(num(line.unitPrice), data?.currency)
          );
        },
        size: 120,
        enableSorting: false,
        meta: {
          headerTitle: 'Unit price',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'amount',
        header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          const price = num(line.unitPrice);
          const shown = price == null ? line.source?.amount ?? null : price * (num(line.qty) ?? 0);
          return fmtSupplierCost(shown, data?.currency);
        },
        size: 120,
        enableSorting: false,
        meta: {
          headerTitle: 'Amount',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'net_weight',
        header: ({ column }) => <DataGridColumnHeader title="Net wt" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          return editing ? (
            <Input
              type="number"
              min={0}
              step="0.01"
              value={line.netWeight}
              onChange={(e) => patchLine(line.key, { netWeight: e.target.value })}
              className="h-8 w-20 text-right tabular-nums"
              aria-label={`Net weight for ${line.itemCode || `line ${row.index + 1}`}`}
              disabled={line.removed}
            />
          ) : num(line.netWeight) == null ? (
            EM_DASH
          ) : (
            fmtTrimmedDecimal(num(line.netWeight), 2)
          );
        },
        size: 100,
        enableSorting: false,
        meta: {
          headerTitle: 'Net wt',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'gross_weight',
        header: ({ column }) => <DataGridColumnHeader title="Gross wt" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          return editing ? (
            <Input
              type="number"
              min={0}
              step="0.01"
              value={line.grossWeight}
              onChange={(e) => patchLine(line.key, { grossWeight: e.target.value })}
              className="h-8 w-20 text-right tabular-nums"
              aria-label={`Gross weight for ${line.itemCode || `line ${row.index + 1}`}`}
              disabled={line.removed}
            />
          ) : num(line.grossWeight) == null ? (
            EM_DASH
          ) : (
            fmtTrimmedDecimal(num(line.grossWeight), 2)
          );
        },
        size: 100,
        enableSorting: false,
        meta: {
          headerTitle: 'Gross wt',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'matched',
        header: ({ column }) => <DataGridColumnHeader title="Match" column={column} />,
        cell: ({ row }) => {
          const line = row.original.source;
          if (!line) {
            // A row the operator added: it is matched by the product they picked, and there
            // is no recorded supplier-code ruling to change or forget yet.
            return row.original.productId ? (
              <Badge variant="success" appearance="light">
                Matched
              </Badge>
            ) : (
              <span className="text-muted-foreground">{EM_DASH}</span>
            );
          }
          if (!line.matched) {
            // The code binds to nothing we hold. Answering it here is the point: the
            // convert reads these lines, so an unmatched one is a line that cannot ship.
            return (
              <div className="flex flex-col items-start gap-1">
                <Badge
                  variant="secondary"
                  appearance="light"
                  title={line.unmatched_reason ?? undefined}
                >
                  Not in catalogue
                </Badge>
                {line.unmatched_reason ? (
                  <span
                    className="truncate text-2xs text-muted-foreground"
                    title={line.unmatched_reason}
                  >
                    {line.unmatched_reason}
                  </span>
                ) : null}
                {canAdjust ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-1.5 text-2xs"
                    onClick={() => setCodeToMatch(line)}
                  >
                    Match to product or set
                  </Button>
                ) : null}
              </div>
            );
          }
          return (
            <div className="flex flex-col items-start gap-0.5">
              <span className="flex items-center gap-1">
                <Badge variant="success" appearance="light">
                  Matched
                </Badge>
                {line.set_code ? (
                  // The supplier priced the whole WC, and our catalogue holds only its
                  // parts (R19). Badged so nobody reads the set code as a product code we
                  // are missing; the conversion is what splits it into members.
                  <Badge
                    variant="secondary"
                    appearance="light"
                    title={`Product set ${line.set_code}`}
                  >
                    Set
                  </Badge>
                ) : null}
                {line.match_source === 'auto' ? (
                  // A guess, marked as one, with the rung that made it in the title. The
                  // reason is not spelled out on screen (no explanations here) - it is in
                  // the tooltip for whoever is checking it.
                  <Badge
                    variant="secondary"
                    appearance="light"
                    title={`Matched by ${line.matched_by ?? 'the supplier code ladder'}`}
                  >
                    auto
                  </Badge>
                ) : null}
              </span>
              {canAdjust && line.match_source ? (
                <span className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-1.5 text-2xs"
                    onClick={() => setCodeToMatch(line)}
                  >
                    Change
                  </Button>
                  {/* Withdrawing the ruling, not correcting it - the code goes back to
                      whatever the ladder can work out on its own. */}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-1.5 text-2xs"
                    onClick={() => setMatchToForget(line)}
                  >
                    Forget
                  </Button>
                </span>
              ) : null}
            </div>
          );
        },
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Match' },
      },
      {
        id: 'line_actions',
        header: '',
        // Marking, not deleting. The row stays on screen struck through until Save, and Undo
        // puts it back - so a mis-click costs nothing and one write carries the whole draft.
        cell: ({ row }) =>
          editing ? (
            <div className="flex items-center justify-end">
              {row.original.removed ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 gap-1 px-2 text-xs"
                  onClick={() => patchLine(row.original.key, { removed: false })}
                >
                  <Undo2 className="size-3.5" />
                  Undo
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 gap-1 px-2 text-xs text-destructive hover:text-destructive"
                  onClick={() => patchLine(row.original.key, { removed: true })}
                >
                  <Trash2 className="size-3.5" />
                  Remove
                </Button>
              )}
            </div>
          ) : null,
        size: 110,
        enableHiding: false,
        enableSorting: false,
      },
    ],
    [data?.currency, editing, canAdjust, fetchProducts],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.key,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // Back carries the list query the row click wrote (S3-01). It lives on the
  // toolbar row now; the empty states below keep one of their own.
  const backLink = (
    <BackToList listPath="/scm/proforma-invoices" label="Back to proforma invoices" />
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
  const convertLabel =
    invoice.placement === 'split' ? 'Convert the rest' : 'Convert to packing list';
  const showConvert = !fullyPlaced && !superseded && canConvert;
  const deleteBlockedReason = converted
    ? `Already converted to ${invoice.converted_shipments.map((s) => s.shipment_number ?? 'a packing list').join(', ')}`
    : undefined;

  /** The placement, as one chip in the header - "Not converted", "Split", or the container. */
  const placementBadge =
    invoice.placement === 'not_converted' ? (
      <Badge variant="secondary" appearance="light">
        Not converted
      </Badge>
    ) : (
      <Badge variant={invoice.placement === 'split' ? 'warning' : 'success'} appearance="light">
        {invoice.placement === 'split'
          ? `Split - ${fmtQty(invoice.remaining_qty)} still to place`
          : `In ${invoice.packing_lists.map((p) => p.shipment_number ?? 'a packing list').join(', ')}`}
      </Badge>
    );

  /** Every line, per shipment, that actually went there - built once for the tab below. */
  const placedLines = (shipmentId: string) =>
    invoice.lines.filter((ln) => ln.packing_lists.some((p) => p.shipment_id === shipmentId));

  const stillToPlace = invoice.lines.filter(
    (ln) => ln.remaining_qty > 0 || ln.unmatched_reason,
  );

  return (
    <div className="space-y-4">
      {/* The record header - what the invoice IS, and what can be done to it. Above the
          tabs, because it belongs to the whole record rather than to any one of its
          concerns. Read-only provenance lives in the meta line, never inside a tab body. */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
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
                {placementBadge}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {invoice.source_ref ?? 'No source file'}
                {' · '}
                Uploaded by {invoice.uploaded_by ?? 'unknown'} on {fmtDate(invoice.created_at)}
                {invoice.adjusted_by
                  ? ` · Adjusted by ${invoice.adjusted_by} on ${fmtDate(invoice.adjusted_at)}`
                  : ''}
              </p>
            </div>

            {/* In an edit session the header states ONE intent: Save or Cancel. Nav and the
                way out act on the invoice as it is STORED, and offering them over a screen
                full of unsaved changes is offering to act on a document nobody is reading. */}
            {editing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  Nothing is written until you press Save.
                </span>
                <Button variant="outline" size="sm" onClick={cancelEdit} disabled={saving}>
                  Cancel
                </Button>
                <Button size="sm" onClick={() => void saveEdit()} disabled={saving}>
                  {saving ? <LoaderCircle className="me-2 size-4 animate-spin" /> : null}
                  Save
                </Button>
              </div>
            ) : (
              <DetailActions
                pager={{
                  ...proformaInvoicesPagerQuery,
                  detailPath: '/scm/proforma-invoices',
                  currentId: id,
                  ariaLabel: 'proforma invoice',
                }}
                gearLabel="Proforma invoice options"
                gear={
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="icon" aria-label="More actions">
                      <Settings className="size-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {canEdit ? (
                      <DropdownMenuItem onClick={beginEdit}>
                        <SquarePen className="size-4" />
                        Edit
                      </DropdownMenuItem>
                    ) : null}
                    <DropdownMenuItem onClick={() => void runExport()}>
                      <Download className="size-4" />
                      Export adjusted PI
                    </DropdownMenuItem>
                    {canAdjust && !superseded && !invoice.revision_of_pi_number ? (
                      <DropdownMenuItem onClick={() => setRevisionOpen(true)}>
                        <GitBranch className="size-4" />
                        Mark as revision of
                      </DropdownMenuItem>
                    ) : null}
                    {canAdjust ? (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive"
                          disabled={converted}
                          // A disabled item's reason travels as a native `title` - Radix has
                          // no room for a Tooltip wrapper here, and a control that refuses
                          // without saying why reads as a defect.
                          title={deleteBlockedReason}
                          onClick={converted ? undefined : () => setDeleteOpen(true)}
                        >
                          <Trash2 className="size-4" />
                          Delete invoice
                        </DropdownMenuItem>
                      </>
                    ) : null}
                  </DropdownMenuContent>
                </DropdownMenu>
                }
                primary={
                  <>
                {/* The main action on this page, so it wears the main colour. Everything
                    else is a secondary action and lives in the menu beside it. */}
                {showConvert ? (
                  <Button
                    variant="primary"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => setConvertOpen(true)}
                    disabled={convertToDraftShipment.isPending}
                  >
                    <Boxes className="size-4" />
                    {convertLabel}
                  </Button>
                ) : null}
                  </>
                }
              />
            )}
          </div>
        </CardHeader>
      </Card>

      {/* One tab per concern of the invoice, the same shape as the purchase-order screen.
          The tab set is the SAME in view and in edit - editing swaps a value for an input
          inside the tab it already lived in. */}
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start overflow-x-auto">
          <TabsTrigger value="general">
            <FileText />
            <span>General</span>
          </TabsTrigger>
          <TabsTrigger value="lines">
            <ListOrdered />
            <span>Lines</span>
          </TabsTrigger>
          <TabsTrigger value="revisions">
            <GitBranch />
            <span>Revisions</span>
          </TabsTrigger>
          <TabsTrigger value="packing-lists">
            <PackageCheck />
            <span>Packing lists</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="mt-0 space-y-4 focus-visible:outline-none">
          {/* Three cards, each at most two columns of label/value - the three things a
              person asks about this document separately: what it is, whose it is, and
              whether it fits. Each is named as a region so a reader (and a test) can
              address one. */}
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Invoice</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="Invoice" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
              {/* First field, and correctable: a derived number (`PI-<file stem>-<block>`)
                  is a guess the file forced on us, and the person holding the paper knows
                  what the supplier actually called it. */}
              <Field label="PI number" htmlFor={editing ? 'pi-number' : undefined}>
                {editing ? (
                  <Input
                    id="pi-number"
                    value={draftNumber}
                    onChange={(e) => setDraftNumber(e.target.value)}
                    maxLength={100}
                    className="h-8"
                  />
                ) : (
                  invoice.pi_number
                )}
              </Field>
              <Field label="Invoice date">{fmtDate(invoice.invoice_date)}</Field>
              <Field label="Container">{invoice.container_no ?? EM_DASH}</Field>
              <Field label="BL">{invoice.bl_no ?? EM_DASH}</Field>
              <Field label="Currency">{invoice.currency ?? EM_DASH}</Field>
              {/* Same slot in both views: the value becomes a select where the value was. */}
              <Field label="Container size" htmlFor={editing ? 'pi-container-size' : undefined}>
                {editing ? (
                  <SearchableSelect
                    id="pi-container-size"
                    size="sm"
                    value={draftSizeId ?? ''}
                    onChange={(v: string) => setDraftSizeId(v || null)}
                    options={containerOptions}
                    placeholder={containerLabel ? `${containerLabel} (default)` : 'Default size'}
                    clearable
                  />
                ) : (
                  <>
                    {invoice.container_size_code ?? EM_DASH}
                    {invoice.container_cbm != null ? (
                      <span className="ms-1 font-normal text-muted-foreground">
                        {fmtTrimmedDecimal(invoice.container_cbm, 2)} cbm
                      </span>
                    ) : null}
                  </>
                )}
              </Field>
              <Field label="Total">
                {fmtSupplierCost(invoice.total_amount, invoice.currency)}
              </Field>
              <Field label="Lines">{invoice.line_count}</Field>
            </section>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Supplier</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="Supplier" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
              <Field label="Supplier">{invoice.supplier_name ?? EM_DASH}</Field>
              <Field label="Supplier code">{invoice.supplier_code ?? EM_DASH}</Field>
            </section>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Volume</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="Volume" className="p-4">
              <ProformaVolumeFill
                className="max-w-xl"
                totalCbm={volume.total}
                containerCbm={containerCbm}
                containerLabel={containerLabel}
                unmeasuredLines={volume.unmeasured}
              />
            </section>
          </Card>
        </TabsContent>

        <TabsContent value="lines" className="mt-0 space-y-4 focus-visible:outline-none">
          {/* Lines - always rendered, explicit empty state. */}
          <DataGrid
            table={table}
            recordCount={rows.length}
            isLoading={false}
            tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
            emptyMessage="This proforma invoice has no lines."
            listingKey={LINES_LISTING_KEY}
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
          {editing ? (
            <Button variant="outline" size="sm" className="gap-1.5" onClick={addLine}>
              <Plus className="size-4" />
              Add line
            </Button>
          ) : null}
        </TabsContent>

        <TabsContent value="revisions" className="mt-0 focus-visible:outline-none">
          {/* Always rendered with its own empty state, per the CRUD standard. */}
          <ProformaRevisionsCard invoice={invoice} />
        </TabsContent>

        <TabsContent value="packing-lists" className="mt-0 focus-visible:outline-none">
          {/* Where the goods went, and what is left. "Split" is a real state: one invoice
              legitimately sits in two containers (Q9, AC-F8). */}
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Packing lists</CardTitle>
              </CardHeading>
            </CardHeader>
            <div className="space-y-4 p-4">
              {invoice.packing_lists.length === 0 ? (
                <div className="flex flex-col items-start gap-3">
                  <p className="text-sm text-muted-foreground">
                    Nothing from this invoice is in a packing list yet.
                  </p>
                  {showConvert ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => setConvertOpen(true)}
                    >
                      <Boxes className="size-4" />
                      {convertLabel}
                    </Button>
                  ) : null}
                </div>
              ) : (
                <ul className="divide-y divide-border rounded-lg border">
                  {invoice.packing_lists.map((pl) => (
                    <li key={pl.shipment_id} className="space-y-1 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Link
                          href={`/procurement-management/packing-lists/${pl.shipment_id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {pl.shipment_number ?? 'Draft'}
                        </Link>
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          {fmtQty(pl.qty)} of {fmtQty(invoice.total_qty)}
                          {pl.shipment_status ? (
                            <Badge variant="secondary" appearance="light">
                              {pl.shipment_status}
                            </Badge>
                          ) : null}
                        </span>
                      </div>
                      <p className="text-2xs text-muted-foreground">
                        {placedLines(pl.shipment_id)
                          .map((ln) => ln.item_code)
                          .join(', ') || 'No line recorded against this container.'}
                      </p>
                    </li>
                  ))}
                </ul>
              )}

              {/* Named, never silently absent: a line that cannot go is the reason a convert
                  reports fewer lines than the invoice carries. */}
              <div className="space-y-1">
                <p className="text-xs font-medium">Still to place</p>
                {stillToPlace.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Every line on this invoice has been placed.
                  </p>
                ) : (
                  <ul className="divide-y divide-border rounded-lg border text-xs">
                    {stillToPlace.map((ln) => (
                      <li
                        key={ln.id}
                        className="flex flex-wrap items-center justify-between gap-2 p-2.5"
                      >
                        <span className="truncate font-medium" title={ln.item_code}>
                          {ln.item_code}
                        </span>
                        <span className="text-muted-foreground">
                          {ln.unmatched_reason
                            ? ln.unmatched_reason
                            : `${fmtQty(ln.remaining_qty)} left`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      {/* "This code is that product" - recorded once, and every row already uploaded
          under it is re-bound in the same write (R16). */}
      <MatchToProductDialog
        open={!!codeToMatch}
        onOpenChange={(o) => !o && setCodeToMatch(null)}
        supplierId={invoice.supplier_id}
        supplierCode={codeToMatch?.item_code ?? null}
        supplierLabel={codeToMatch?.description ?? null}
        onMatched={() => setCodeToMatch(null)}
      />

      {/* Forgetting a ruling is destructive - the rows bound by it are un-bound in the same
          write - so it is asked before it is done, like every other delete here. */}
      <ConfirmDeleteDialog
        open={!!matchToForget}
        onOpenChange={(o) => !o && setMatchToForget(null)}
        title="Forget this match?"
        description={
          matchToForget
            ? `Forget that ${matchToForget.item_code} means ${
                matchToForget.product_code ?? 'this product'
              }? Next upload will match it again by the ladder.`
            : ''
        }
        confirmLabel="Forget"
        onDelete={async () => {
          if (matchToForget?.match_id) await forgetMatch.mutateAsync(matchToForget.match_id);
        }}
        successMessage="Match forgotten."
      />

      {/* Hard delete, per the CRUD standard, and only from the actions menu - it is not a
          button sitting beside the one everybody presses. */}
      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Confirm delete"
        description={`This action cannot be undone. This deletes proforma invoice ${invoice.pi_number} and every line it carries.`}
        onDelete={async () => {
          await deleteInvoice.mutateAsync(id);
          router.push('/scm/proforma-invoices');
        }}
        successMessage="Proforma invoice deleted."
      />

      <MarkAsRevisionDialog
        open={revisionOpen}
        onOpenChange={setRevisionOpen}
        invoice={invoice}
      />

      <OverCapacityDialog
        message={overCapacity}
        reason={overrideReason}
        onReasonChange={setOverrideReason}
        onCancel={() => setOverCapacity(null)}
        onConfirm={() => void runConvert(convertArgs, overrideReason.trim())}
        pending={convertToDraftShipment.isPending}
      />

      {/* How much of this invoice goes onto a container (AC-F10, Q9). Always a NEW draft
          packing list: "add to an existing draft" is gone everywhere (Q6). */}
      <ConvertToPackingListDialog
        open={convertOpen}
        onOpenChange={setConvertOpen}
        invoiceIds={[id]}
        pending={convertToDraftShipment.isPending}
        onConvert={(args) => void runConvert(args)}
      />
    </div>
  );
}

export default ProformaInvoiceDetail;
