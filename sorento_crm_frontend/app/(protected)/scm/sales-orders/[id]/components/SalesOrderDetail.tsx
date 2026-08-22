'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  SortingState,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ArrowLeft, CheckCircle2, LoaderCircleIcon, SquarePen, Truck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Input } from '@/components/ui/input';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { useSearchParams } from 'next/navigation';
import { useSalesOrder, useUpdateSalesOrder } from '../../../hooks/useSalesOrders';
import {
  useCustomerOptions,
  useOrderTypeOptions,
  useProductOptions,
  useWarehouseOptions,
} from '../../../hooks/useScmOptions';
import { useSalesAgentOptions } from '../../hooks/useSalesAgentOptions';
import SalesOrderNavigation from '../../components/SalesOrderNavigation';
import { getSalesOrderUoms, type SalesOrderPlanningChangeBatch } from '../../../services/salesOrderService';
import { fmtDate, fmtInt } from '../../../lib/format';
import { demandClassBadge } from '../../../lib/demandClass';
import type { SalesOrder, SalesOrderLine, SalesOrderPriority } from '../../../types/scm.types';

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
 *
 * VIEW AND EDIT ARE THE SAME SCREEN (A5). Editing swaps a read-only value for an input IN
 * PLACE - the same fields, in the same order, in the same grid. Header: Order type, Customer,
 * Priority, Requested delivery, Agent. Lines: SKU, Qty ordered, Location, Delivery date and
 * UoM. Everything else on the summary (Customer code, Market segment, Source, Lines, Total
 * qty, Still owed, Locations) has no edit counterpart and stays exactly where it always was.
 * One Save writes the whole header, plus the lines ONLY when they actually moved - see
 * `lineSignature` - because the PUT endpoint still upserts the WHOLE `lines` array when the
 * key is sent at all: omit it for a header-only edit or every line is re-sent for no reason.
 * The service UPSERTS what it is sent rather than delete-and-reinsert, matching each sent
 * line to an existing row by `id` FIRST (this form now sends it) or by SKU otherwise - so a
 * matched line keeps its id, `qty_delivered` and `source_system`; only an unmatched existing
 * line is deleted, and the BE refuses that with a 409 when the line is still reconciled to a
 * project sales order or claimed by a purchase order.
 *
 * `warehouse_code` / `required_date` / `uom` ride on the SAME line objects as SKU/qty. The BE
 * applies each key independently via `model_fields_set` - a key a sent LINE does not carry
 * leaves that line's stored value untouched - but this form always sends all three for every
 * line once `lines` is sent at all (the same "resend everything on any line change" rule the
 * SKU/qty columns already followed), each carrying either the draft's edited value or the
 * value the order loaded with, so an untouched line reads back exactly as it was.
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

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

/** Is this order still owed to the customer? The counterpart of the PO screen's "On order".
 *  Derived from the OPEN line count rather than the status alone, because an order can sit
 *  in an open status with every line closed. */
const countsAsCommitted = (so: SalesOrder) =>
  (so.open_line_count ?? 0) > 0 && so.committed_qty > 0;

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  /** Set while editing, so the label associates with the input/select it now wraps and
   *  the field is reachable by its name - the same label text either way. */
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      {htmlFor ? (
        <label htmlFor={htmlFor} className="text-xs text-muted-foreground">
          {label}
        </label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

/** `sku|qty|warehouse_code|required_date|uom` per line, order-independent, so a re-save
 *  with the same lines in a different order is not read as a change. Mirrors
 *  `SalesOrderFormModal`'s own invariant: `lines` is left off the write entirely when
 *  nothing here moved, or a header-only edit would resend every line for the BE to
 *  match-and-upsert for no reason. */
function lineSignature(
  ls: {
    sku: string;
    qty_ordered: number;
    warehouse_code: string;
    required_date: string;
    uom: string;
  }[],
): string {
  return ls
    .map((l) => `${l.sku}|${l.qty_ordered}|${l.warehouse_code}|${l.required_date}|${l.uom}`)
    .sort()
    .join(',');
}

type LineDraft = {
  sku: string;
  qty_ordered: string;
  warehouse_code: string;
  required_date: string;
  uom: string;
};

/** The in-progress draft for a line, or one seeded from the row as loaded when nothing has
 *  touched it yet - so any single field's onChange can spread this and set only the field it
 *  owns without silently dropping the other four. */
function draftOrRow(
  drafts: Record<string, LineDraft>,
  row: SalesOrderLine,
): LineDraft {
  return (
    drafts[row.id] ?? {
      sku: row.sku,
      qty_ordered: String(row.qty_ordered),
      warehouse_code: row.warehouse_code ?? '',
      required_date: row.required_date?.slice(0, 10) ?? '',
      uom: row.uom ?? '',
    }
  );
}

export function SalesOrderDetail({ id }: { id: string }) {
  const { data, isLoading, isError } = useSalesOrder(id);
  const searchParams = useSearchParams();
  const listSearch = searchParams.toString();

  const updateMut = useUpdateSalesOrder();
  const orderTypeOptions = useOrderTypeOptions();
  const customerOptions = useCustomerOptions();
  const productOptions = useProductOptions();
  const agentOptions = useSalesAgentOptions();
  const warehouseOptions = useWarehouseOptions();
  // Inline rather than a shared hook file: this select is used on this one screen. Mirrors
  // `useSalesOrderAgents`'s own staleTime - the UoM master changes rarely enough that a
  // 5-minute cache is not worth a dedicated hooks file for one caller.
  const uomOptionsQuery = useQuery({
    queryKey: ['scm', 'sales-order-uoms'],
    queryFn: getSalesOrderUoms,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const uomSelectOptions = useMemo<SearchableSelectOption[]>(
    () => (uomOptionsQuery.data ?? []).map((u) => ({ value: u.uom_code, label: u.uom_name })),
    [uomOptionsQuery.data],
  );
  // Code review nit: the read view's Location cell shows the code (`row.original.warehouse_code`,
  // below), and `getWarehouseOptions` labels each option with the NAME - so the same value read
  // as "BRW" and edited as "Bandar Rawang Warehouse". Prefix the code onto the label here so the
  // edit select reads the same value the view does, without changing the shared option list every
  // other SCM picker (filter bar, planning modal, preview card) also uses.
  const warehouseSelectOptions = useMemo(
    () => (warehouseOptions.data ?? []).map((o) => ({ ...o, label: `${o.value} - ${o.label}` })),
    [warehouseOptions.data],
  );

  const [isEditing, setIsEditing] = useState(false);
  const [orderType, setOrderType] = useState('');
  const [customerCode, setCustomerCode] = useState('');
  const [priority, setPriority] = useState<SalesOrderPriority>('normal');
  const [requestedDate, setRequestedDate] = useState('');
  const [agentId, setAgentId] = useState('');
  const [lineDrafts, setLineDrafts] = useState<Record<string, LineDraft>>({});
  const [error, setError] = useState<string | null>(null);
  const originalLineSignatureRef = useRef<string | null>(null);
  // Set only when a save's response actually carries one (PLAN-so-book-diff-replanning.md
  // section 2) - most saves never touch this. Cleared on the next edit session, so it
  // cannot linger and describe a batch a later save superseded.
  const [planningChangeBatch, setPlanningChangeBatch] =
    useState<SalesOrderPlanningChangeBatch | null>(null);

  const beginEdit = (so: SalesOrder) => {
    setPlanningChangeBatch(null);
    setOrderType(so.order_type);
    setCustomerCode(so.customer_code);
    setPriority(so.priority);
    setRequestedDate(so.requested_delivery_date?.slice(0, 10) ?? '');
    setAgentId(so.sales_agent_id ?? '');
    const drafts: Record<string, LineDraft> = {};
    for (const ln of so.lines) {
      drafts[ln.id] = {
        sku: ln.sku,
        qty_ordered: String(ln.qty_ordered),
        warehouse_code: ln.warehouse_code ?? '',
        required_date: ln.required_date?.slice(0, 10) ?? '',
        uom: ln.uom ?? '',
      };
    }
    setLineDrafts(drafts);
    originalLineSignatureRef.current = lineSignature(
      so.lines.map((l) => ({
        sku: l.sku,
        qty_ordered: l.qty_ordered,
        warehouse_code: l.warehouse_code ?? '',
        required_date: l.required_date?.slice(0, 10) ?? '',
        uom: l.uom ?? '',
      })),
    );
    setError(null);
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setIsEditing(false);
    setError(null);
  };

  // `?edit=1` opens the session on arrival - the same entry the list's Pencil action uses -
  // so a click there and a bookmarked link land in the same place. Fired once: re-running it
  // after Cancel would put the user straight back into the session they just left.
  const wantsEdit = searchParams.get('edit') === '1';
  const opened = useRef(false);
  useEffect(() => {
    if (!wantsEdit || opened.current || !data) return;
    opened.current = true;
    beginEdit(data);
  }, [wantsEdit, data]);

  const lines = useMemo<SalesOrderLine[]>(() => data?.lines ?? [], [data]);
  // Sorted here rather than by the API: the lines come embedded in the order read, so there
  // is no second request to spend and no page boundary to sort across.
  const [sorting, setSorting] = useState<SortingState>([]);

  // The Product dropdown is server-paged (top 100 by code), so a line whose SKU sorts past
  // page one - routine on a large catalogue - is not among `productOptions.data` and the
  // SearchableSelect renders it blank even though the line's own `sku` is set correctly.
  // Widen the option list with this order's own lines so every one it opened with resolves.
  const mergedProductOptions = useMemo(() => {
    const base = productOptions.data ?? [];
    const known = new Set(base.map((o) => o.value));
    const extra: SearchableSelectOption[] = [];
    for (const l of lines) {
      if (!l.sku || known.has(l.sku)) continue;
      known.add(l.sku);
      extra.push({
        value: l.sku,
        label: l.product_name ? `${l.sku} · ${l.product_name}` : l.sku,
      });
    }
    return extra.length ? [...base, ...extra] : base;
  }, [productOptions.data, lines]);

  const columns = useMemo<ColumnDef<SalesOrderLine>[]>(
    () => [
      {
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="SKU" column={column} />,
        cell: ({ row }) => {
          if (isEditing) {
            const draft = lineDrafts[row.original.id];
            return (
              <SearchableSelect
                value={draft?.sku ?? row.original.sku}
                onChange={(v) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [row.original.id]: { ...draftOrRow(prev, row.original), sku: v },
                  }))
                }
                options={mergedProductOptions}
                placeholder="Select product"
                size="sm"
              />
            );
          }
          return (
            <div className="flex min-w-0 flex-col">
              <span className="font-medium">{row.original.sku}</span>
              <span
                className="truncate text-xs text-muted-foreground"
                title={row.original.product_name}
              >
                {row.original.product_name}
              </span>
            </div>
          );
        },
        size: 260,
        meta: { headerTitle: 'SKU' },
      },
      {
        id: 'qty_ordered',
        // The sort value is the NUMBER, never the printed string: a quantity read off the
        // API as "1200.0000" would otherwise order before "45" the way a word does.
        accessorFn: (line) => Number(line.qty_ordered),
        header: ({ column }) => <DataGridColumnHeader title="Qty ordered" column={column} />,
        cell: ({ row }) => {
          if (isEditing) {
            const draft = lineDrafts[row.original.id];
            return (
              <Input
                type="number"
                min={0}
                value={draft?.qty_ordered ?? String(row.original.qty_ordered)}
                onChange={(e) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [row.original.id]: { ...draftOrRow(prev, row.original), qty_ordered: e.target.value },
                  }))
                }
                className="h-8 text-right tabular-nums"
              />
            );
          }
          return fmtInt(row.original.qty_ordered);
        },
        size: 130,
        meta: {
          headerTitle: 'Qty ordered',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'qty_delivered',
        accessorFn: (line) => Number(line.qty_delivered),
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
        // Computed here rather than sent, so it cannot disagree with the two columns beside
        // it. A negative delivery (over-shipped) reads as 0 rather than as a negative
        // commitment, which is what the committed figure does too. The accessor is what the
        // cell prints, so "sort by what is still owed" sorts by the figure on screen - an
        // id-only column carries a sort arrow it cannot honour.
        accessorFn: (line) =>
          Math.max(Number(line.qty_ordered) - Number(line.qty_delivered), 0),
        header: ({ column }) => <DataGridColumnHeader title="Still owed" column={column} />,
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
        cell: ({ row }) => {
          if (isEditing) {
            const draft = draftOrRow(lineDrafts, row.original);
            const selectId = `so-edit-line-${row.original.id}-warehouse`;
            return (
              <>
                {/* SearchableSelect forwards `id`, not arbitrary aria props - the accessible
                    name needs a real (visually-hidden) label. */}
                <label className="sr-only" htmlFor={selectId}>
                  Location on {row.original.sku}
                </label>
                <SearchableSelect
                  id={selectId}
                  value={draft.warehouse_code}
                  onChange={(v) =>
                    setLineDrafts((prev) => ({
                      ...prev,
                      [row.original.id]: { ...draftOrRow(prev, row.original), warehouse_code: v },
                    }))
                  }
                  options={warehouseSelectOptions}
                  placeholder="No location"
                  clearable
                  size="sm"
                />
              </>
            );
          }
          return row.original.warehouse_code || '-';
        },
        size: 140,
        meta: { headerTitle: 'Location' },
      },
      {
        id: 'required_date',
        // The ISO date, not the printed "04 Jul 2026": the display form sorts by day-of-month
        // and would put September before July. A line with no date sorts last either way.
        // Labelled "Delivery date" - the same field (`required_date`) reads as "when this
        // line ships", which is what the customer wants to know, not an internal deadline.
        accessorFn: (line) => line.required_date ?? undefined,
        header: ({ column }) => <DataGridColumnHeader title="Delivery date" column={column} />,
        cell: ({ row }) => {
          if (isEditing) {
            const draft = draftOrRow(lineDrafts, row.original);
            return (
              <Input
                type="date"
                aria-label={`Delivery date on ${row.original.sku}`}
                value={draft.required_date}
                onChange={(e) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [row.original.id]: {
                      ...draftOrRow(prev, row.original),
                      required_date: e.target.value,
                    },
                  }))
                }
                className="h-8"
              />
            );
          }
          return row.original.required_date ? fmtDate(row.original.required_date) : '-';
        },
        size: 150,
        meta: { headerTitle: 'Delivery date' },
      },
      {
        accessorKey: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UoM" column={column} />,
        cell: ({ row }) => {
          if (isEditing) {
            const draft = draftOrRow(lineDrafts, row.original);
            const selectId = `so-edit-line-${row.original.id}-uom`;
            return (
              <>
                {/* SearchableSelect forwards `id`, not arbitrary aria props - same pattern
                    as the Location select above. */}
                <label className="sr-only" htmlFor={selectId}>
                  UoM on {row.original.sku}
                </label>
                <SearchableSelect
                  id={selectId}
                  value={draft.uom}
                  onChange={(v) =>
                    setLineDrafts((prev) => ({
                      ...prev,
                      [row.original.id]: { ...draftOrRow(prev, row.original), uom: v },
                    }))
                  }
                  options={uomSelectOptions}
                  // Clearing sends `''`, which the BE reads as an explicit `uom: null` -
                  // "use the product's own default" - not "leave it alone" (this form
                  // always sends the key once `lines` is sent at all, see the class
                  // docstring).
                  placeholder="Product default"
                  clearable
                  size="sm"
                />
              </>
            );
          }
          return row.original.uom;
        },
        size: 140,
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
    [isEditing, lineDrafts, mergedProductOptions, warehouseSelectOptions, uomSelectOptions],
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

  const handleSave = async () => {
    setError(null);
    if (!orderType) return setError('Select an order type.');
    if (!customerCode) return setError('Select a customer.');
    // `id` is sent so the BE matches this line by id rather than falling back to SKU.
    // Location / delivery date / UoM ride the SAME upsert as SKU/qty - see the class
    // docstring - carrying either what the person typed or, for an untouched line, exactly
    // what the order loaded with.
    const cleanedLines = so.lines.map((ln) => {
      const draft = lineDrafts[ln.id];
      return {
        id: ln.id,
        sku: draft?.sku ?? ln.sku,
        qty_ordered: Number(draft?.qty_ordered ?? ln.qty_ordered),
        warehouse_code: draft?.warehouse_code ?? ln.warehouse_code ?? '',
        required_date: draft?.required_date ?? ln.required_date?.slice(0, 10) ?? '',
        uom: draft?.uom ?? ln.uom ?? '',
      };
    });
    if (cleanedLines.some((l) => !l.sku || !(l.qty_ordered > 0))) {
      return setError('Every line needs a product and a quantity above zero.');
    }
    const linesUnchanged =
      originalLineSignatureRef.current !== null &&
      lineSignature(cleanedLines) === originalLineSignatureRef.current;
    try {
      const result = await updateMut.mutateAsync({
        id,
        data: {
          order_type: orderType,
          customer_code: customerCode,
          priority,
          requested_delivery_date: requestedDate || null,
          sales_agent_id: agentId || null,
          ...(linesUnchanged ? {} : { lines: cleanedLines }),
        },
      });
      setPlanningChangeBatch(result.planning_change_batch ?? null);
      setIsEditing(false);
    } catch {
      // The mutation already toasted the reason; leave the session open so nothing typed
      // is lost.
    }
  };

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
            {/* In an edit session the header states ONE intent: Save or Cancel. Nav and the
                way out act on the order as it is STORED, and offering them over a screen
                full of unsaved changes is offering to act on a document nobody is reading. */}
            {isEditing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  Nothing is written until you press Save.
                </span>
                <Button variant="outline" size="sm" onClick={cancelEdit} disabled={updateMut.isPending}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={updateMut.isPending}>
                  {updateMut.isPending ? (
                    <LoaderCircleIcon className="me-2 size-4 animate-spin" />
                  ) : null}
                  Save
                </Button>
              </div>
            ) : (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <SalesOrderNavigation salesOrderId={id} />
                <Button variant="outline" size="sm" className="gap-1.5" onClick={() => beginEdit(so)}>
                  <SquarePen className="size-4" />
                  Edit
                </Button>
                {backLink}
              </div>
            )}
          </div>
          {isEditing && error ? (
            <Alert variant="destructive" className="mt-3">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          {/* Only after a save whose response carried one - the same reaction an uploaded
              book's own preview surfaces (`OutstandingUploadDialog`'s `PlanningChangeBatchCard`).
              Quiet: a count and a link, nothing explaining what a planning change is. */}
          {!isEditing && planningChangeBatch ? (
            <div className="mt-3 flex flex-col gap-2 rounded-lg border border-border bg-muted/30 p-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm font-medium">
                {`Planning changes raised on ${fmtInt(planningChangeBatch.line_count)} line${
                  planningChangeBatch.line_count === 1 ? '' : 's'
                }`}
              </p>
              <Button asChild variant="outline" size="sm">
                <Link href={`/project-sales/planning-changes/${planningChangeBatch.id}`}>
                  Review
                </Link>
              </Button>
            </div>
          ) : null}
        </CardHeader>
        {/* Named as a region so a reader (and a test) can tell the summary's "Still owed"
            from the lines grid's column of the same name. They share the phrase on purpose:
            it is the same quantity, once for the order and once per line. */}
        <section
          aria-label="Order summary"
          className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4"
        >
          <Field label="Customer" htmlFor={isEditing ? 'so-edit-customer' : undefined}>
            {isEditing ? (
              <SearchableSelect
                id="so-edit-customer"
                value={customerCode}
                onChange={setCustomerCode}
                options={customerOptions.data ?? []}
                placeholder="Select customer"
                size="sm"
              />
            ) : (
              so.customer_name || '-'
            )}
          </Field>
          <Field label="Customer code">{so.customer_code || '-'}</Field>
          {/* Primary value is the planning class (`demand_class`) - what the classification
              agents actually resolved - not `order_type_label`, the ERP document type that
              is blank on almost every row in this book. The document type still rides along
              as a hint when the order carries one and it says something the class does not
              already say. Editing is unchanged: it still sets `order_type`, which is what
              derives `demand_class` on save (see `sales_order_service.update`). */}
          <Field label="Order type" htmlFor={isEditing ? 'so-edit-order-type' : undefined}>
            {isEditing ? (
              <SearchableSelect
                id="so-edit-order-type"
                value={orderType}
                onChange={setOrderType}
                options={orderTypeOptions.data ?? []}
                placeholder="Select type"
                size="sm"
              />
            ) : (
              (() => {
                const cls = demandClassBadge(so.demand_class);
                const hint = so.order_type_label;
                const showHint = hint && hint !== cls.label;
                return (
                  <span className="inline-flex flex-wrap items-center gap-1.5">
                    <Badge variant={cls.variant} appearance="light" size="sm">
                      {cls.label}
                    </Badge>
                    {showHint ? (
                      // `text-2xs`, not `text-xs` - the view/edit parity test walks
                      // `span.text-xs` as the Field label selector, and this hint is a
                      // VALUE, not a label.
                      <span className="text-2xs font-normal text-muted-foreground">{hint}</span>
                    ) : null}
                  </span>
                );
              })()
            )}
          </Field>
          <Field label="Market segment">{so.market_segment || '-'}</Field>
          {/* Who sold it - the sales_agents master, resolved by the backend. Read as the
              code with the person it has been annotated to, when known; edited as a
              clearable select, since not every order names an agent. */}
          <Field label="Agent" htmlFor={isEditing ? 'so-edit-agent' : undefined}>
            {isEditing ? (
              <SearchableSelect
                id="so-edit-agent"
                value={agentId}
                onChange={setAgentId}
                options={agentOptions.options}
                placeholder="No agent"
                clearable
                size="sm"
              />
            ) : so.sales_agent_code ? (
              <span title={so.sales_agent_label ?? undefined}>
                {so.sales_agent_code}
                {so.sales_agent_label ? (
                  <span className="ms-1 font-normal text-muted-foreground">
                    · {so.sales_agent_label}
                  </span>
                ) : null}
              </span>
            ) : (
              '-'
            )}
          </Field>
          <Field label="Order date">{fmtDate(so.order_date)}</Field>
          <Field
            label="Requested delivery"
            htmlFor={isEditing ? 'so-edit-requested-date' : undefined}
          >
            {isEditing ? (
              <Input
                id="so-edit-requested-date"
                type="date"
                value={requestedDate}
                onChange={(e) => setRequestedDate(e.target.value)}
                className="h-8"
              />
            ) : so.requested_delivery_date ? (
              fmtDate(so.requested_delivery_date)
            ) : (
              '-'
            )}
          </Field>
          <Field label="Priority" htmlFor={isEditing ? 'so-edit-priority' : undefined}>
            {isEditing ? (
              <SearchableSelect
                id="so-edit-priority"
                value={priority}
                onChange={(v) => setPriority((v || 'normal') as SalesOrderPriority)}
                options={PRIORITY_OPTIONS}
                placeholder="Select priority"
                size="sm"
              />
            ) : (
              PRIORITY_LABELS[so.priority] ?? titleCase(so.priority)
            )}
          </Field>
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
