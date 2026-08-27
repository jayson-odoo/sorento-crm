'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  ArrowLeft,
  Columns3,
  FileText,
  ListOrdered,
  LoaderCircleIcon,
  Move,
  Search,
  SquarePen,
  Truck,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTable,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { StockTransfersPanel } from '@/app/(protected)/inventory-management/stock-transfers/components/StockTransfersPanel';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Input } from '@/components/ui/input';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { DEMAND_CLASS_OPTIONS } from '@/app/(protected)/master-data-management/sales-agents/lib/demandClass';
// The SAME pill the order-inquiry worklist reads, not a second one worded differently:
// "Placed" has to mean the same thing on both screens or the two disagree in a glance.
import { OrderInquiryStatePill } from '@/app/(protected)/project-sales/_shared/components/OrderInquiryVerbPill';
import {
  formatMyrExact,
  multiplyMoney,
  subtractMoney,
  sumMoney,
} from '@/app/(protected)/project-sales/_shared/lib/money';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useSearchParams } from 'next/navigation';
import { useSalesOrder, useUpdateSalesOrder } from '../../../hooks/useSalesOrders';
import { useWarehouseOptions } from '../../../hooks/useScmOptions';
import {
  SELECT_PAGE_SIZE,
  searchCustomerOptions,
  searchProductOptions,
} from '../../../services/scmOptionsService';
import { useSalesAgentOptions } from '../../hooks/useSalesAgentOptions';
import SalesOrderNavigation from '../../components/SalesOrderNavigation';
import { getSalesOrderUoms, type SalesOrderPlanningChangeBatch } from '../../../services/salesOrderService';
import { fmtDate, fmtInt } from '../../../lib/format';
import { demandClassBadge } from '../../../lib/demandClass';
import {
  salesOrderPriorityVariant,
  salesOrderStatusLabel,
  salesOrderStatusVariant,
} from '../../../lib/salesOrderStatus';
import type {
  SalesOrder,
  SalesOrderLine,
  SalesOrderLineSupplyComponent,
  SalesOrderPriority,
} from '../../../types/scm.types';
// ONE vocabulary for where supply comes from (PLAN-scm-cs-planning-uat.md section 2), shared
// with the planning board rather than restated here.
import { describe as describeSupply } from '../../../../project-sales/_shared/lib/supplyVocabulary';

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
 * THE RECORD IS TABBED, the same shape as the user detail page: the page header (number,
 * status, actions, prev/next) sits above a `variant="line"` tab strip, and each concern of the
 * order owns one tab - General (the summary and the note), Lines, Delivery. Every section is
 * still rendered with its own empty state; a tab is where it lives, not a condition on it.
 *
 * THE GENERAL TAB IS THREE CARDS, each at most TWO columns of label/value fields - Order,
 * Customer, Totals. It was one four-across grid of eleven fields, which reads as a wall
 * rather than as three things a person asks separately.
 *
 * VIEW AND EDIT ARE THE SAME SCREEN (A5). Editing swaps a read-only value for an input IN
 * PLACE - the same fields, in the same order, in the same card, in the same tab. Editable:
 * Order type, Priority, Order date, Delivery date, Agent, Customer. Lines: Product, Qty
 * ordered, Unit price, Discount, Location, Delivery date and UoM. Everything else (Source,
 * Customer code, the three totals) has no edit counterpart and stays exactly where it was.
 *
 * ORDER TYPE IS THE PLANNING CLASS, both ways. It used to RENDER `demand_class` and EDIT
 * `order_type` - a column that is NULL on 96% of this book - and then refuse to save while
 * the order type was empty, so most orders could not be header-edited at all. The select now
 * offers the same two words the class has (Project / Retail), is clearable, and saves as
 * `demand_class`; leaving it empty is allowed and leaves the stored classification alone.
 *
 * One Save writes the whole header, plus the lines ONLY when they actually moved - see
 * `lineSignature` - because the PUT endpoint still upserts the WHOLE `lines` array when the
 * key is sent at all: omit it for a header-only edit or every line is re-sent for no reason.
 * The service UPSERTS what it is sent rather than delete-and-reinsert, matching each sent
 * line to an existing row by `id` FIRST (this form now sends it) or by SKU otherwise - so a
 * matched line keeps its id, `qty_delivered` and `source_system`; only an unmatched existing
 * line is deleted, and the BE refuses that with a 409 when the line is still reconciled to a
 * project sales order or claimed by a purchase order.
 *
 * `warehouse_code` / `required_date` / `uom` / `unit_price` / `discount` ride on the SAME line
 * objects as SKU/qty. The BE applies each key independently via `model_fields_set` - a key a
 * sent LINE does not carry leaves that line's stored value untouched - but this form always
 * sends all five for every line once `lines` is sent at all (the same "resend everything on
 * any line change" rule the SKU/qty columns already followed), each carrying either the
 * draft's edited value or the value the order loaded with, so an untouched line reads back
 * exactly as it was. `line_total` is NOT sent: it is what the source document charged.
 *
 * MONEY IS A STRING END TO END. The backend sends `Decimal`, which Pydantic serialises as a
 * string, and every sum here goes through `project-sales/_shared/lib/money` - which does the
 * arithmetic on scaled integers - rather than `Number()`. A float sum of 200 line totals
 * drifts, and a footer that disagrees with the header by one cent is read as a data problem.
 */

function titleCase(v: string): string {
  return v.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Where the order came from. `history` is its own answer because "Manual" would claim
 *  somebody keyed a 2020 order by hand. Mirrors the purchase-order side's `import`. */
const SOURCE_LABELS: Record<string, string> = {
  inquiry: 'Order inquiry sheet',
  // The same words the list uses for the same row - the upload carries the whole book, not
  // only what is still owed.
  upload: 'Sales order upload',
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

/** Does this line answer the product search above the grid? Code and description, because
 *  a planner looking for one item on a 200-line order knows one or the other, not both. */
function lineMatches(line: SalesOrderLine, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    line.sku.toLowerCase().includes(q) || (line.product_name ?? '').toLowerCase().includes(q)
  );
}

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

/** `sku|qty|warehouse_code|required_date|uom|unit_price|discount` per line,
 *  order-independent, so a re-save with the same lines in a different order is not read as a
 *  change. Mirrors `SalesOrderFormModal`'s own invariant: `lines` is left off the write
 *  entirely when nothing here moved, or a header-only edit would resend every line for the
 *  BE to match-and-upsert for no reason. */
function lineSignature(
  ls: {
    sku: string;
    qty_ordered: number;
    warehouse_code: string;
    required_date: string;
    uom: string;
    unit_price: string;
    discount: string;
  }[],
): string {
  return ls
    .map(
      (l) =>
        `${l.sku}|${l.qty_ordered}|${l.warehouse_code}|${l.required_date}|${l.uom}` +
        `|${l.unit_price}|${l.discount}`,
    )
    .sort()
    .join(',');
}

type LineDraft = {
  sku: string;
  qty_ordered: string;
  warehouse_code: string;
  required_date: string;
  uom: string;
  unit_price: string;
  discount: string;
};

/** The in-progress draft for a line, or one seeded from the row as loaded when nothing has
 *  touched it yet - so any single field's onChange can spread this and set only the field it
 *  owns without silently dropping the other six. */
function draftOrRow(
  drafts: Record<string, LineDraft>,
  row: SalesOrderLine,
): LineDraft {
  return drafts[row.id] ?? seedDraft(row);
}

function seedDraft(row: SalesOrderLine): LineDraft {
  return {
    sku: row.sku,
    qty_ordered: String(row.qty_ordered),
    warehouse_code: row.warehouse_code ?? '',
    required_date: row.required_date?.slice(0, 10) ?? '',
    uom: row.uom ?? '',
    unit_price: row.unit_price ?? '',
    discount: row.discount ?? '',
  };
}

/**
 * What a line is worth: the total the source document stated, or the arithmetic its parts
 * support. The SAME rule the backend's own `total_amount` follows, so the column, the
 * footer and the header total cannot disagree - and `null` rather than 0 when nobody
 * priced it, because an unpriced line is not a line worth nothing.
 */
function lineAmount(
  qty: string,
  unitPrice: string,
  discount: string,
  lineTotal: string | null | undefined,
): string | null {
  if (lineTotal) return lineTotal;
  if (!unitPrice) return null;
  const gross = multiplyMoney(qty, unitPrice);
  if (gross === null) return null;
  return discount ? subtractMoney(gross, discount) : gross;
}

/** The money cell's text: the figure, or a plain "-" for a line nobody priced. */
function fmtMoneyCell(value: string | null | undefined): string {
  return value ? formatMyrExact(value) : '-';
}

/**
 * The option the Product select shows for a line whose product is not on the page the
 * server just returned - which is most of them, against a 22,000-row catalogue.
 *
 * Only while the draft still names the line's OWN product: once a different one has been
 * picked, its label comes from the fetched page and this fallback would relabel it.
 */
function productFallback(
  row: SalesOrderLine,
  draftSku: string | undefined,
): SearchableSelectOption | undefined {
  const sku = draftSku ?? row.sku;
  if (!row.sku || sku !== row.sku) return undefined;
  return {
    value: row.sku,
    label: row.product_name ? `${row.sku} · ${row.product_name}` : row.sku,
  };
}

/**
 * One frozen composition, in the planning board's own words (AC-D4).
 *
 * `describe` is the SAME function the board, its list view and the cell popover render with,
 * imported rather than restated: PLAN section 2 is one vocabulary, and a second phrasing of
 * "Shared 71 (BRW)" on this page is how two screens start disagreeing about one decision.
 *
 * `ownLocation` is what tells the agent's own group from the shared pool on a component
 * frozen before the rung was recorded.
 */
function SupplyText({
  parts,
  ownLocation,
  absent,
}: {
  parts?: SalesOrderLineSupplyComponent[] | null;
  ownLocation?: string | null;
  absent: string;
}) {
  if (!parts) return <span className="text-muted-foreground">{absent}</span>;
  const text = describeSupply(parts, ownLocation);
  if (!text) return <span className="text-muted-foreground">-</span>;
  return (
    <span className="block truncate" title={text}>
      {text}
    </span>
  );
}

export function SalesOrderDetail({ id }: { id: string }) {
  const { data, isLoading, isError } = useSalesOrder(id);
  const searchParams = useSearchParams();
  const listSearch = searchParams.toString();

  const updateMut = useUpdateSalesOrder();
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
  // The PLANNING CLASS, not `order_type`: this is the value the read view renders, so it is
  // the value the edit form seeds from and writes back.
  const [demandClass, setDemandClass] = useState('');
  const [customerCode, setCustomerCode] = useState('');
  const [priority, setPriority] = useState<SalesOrderPriority>('normal');
  const [orderDate, setOrderDate] = useState('');
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
    setDemandClass(so.demand_class ?? '');
    setCustomerCode(so.customer_code);
    setPriority(so.priority);
    setOrderDate(so.order_date?.slice(0, 10) ?? '');
    setRequestedDate(so.requested_delivery_date?.slice(0, 10) ?? '');
    setAgentId(so.sales_agent_id ?? '');
    const drafts: Record<string, LineDraft> = {};
    for (const ln of so.lines) {
      drafts[ln.id] = seedDraft(ln);
    }
    setLineDrafts(drafts);
    originalLineSignatureRef.current = lineSignature(
      so.lines.map((l) => ({
        sku: l.sku,
        qty_ordered: l.qty_ordered,
        warehouse_code: l.warehouse_code ?? '',
        required_date: l.required_date?.slice(0, 10) ?? '',
        uom: l.uom ?? '',
        unit_price: l.unit_price ?? '',
        discount: l.discount ?? '',
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
  // Sorted and searched here rather than by the API: the lines come embedded in the order
  // read, so there is no second request to spend and no page boundary to work across.
  const [sorting, setSorting] = useState<SortingState>([]);
  const [lineSearch, setLineSearch] = useState('');
  const [tab, setTab] = useState('general');

  // While an edit session is open every figure below is read off the DRAFT, so a typed
  // quantity or price moves the row AND the totals row at once. Outside a session they read
  // the stored row, which is the same value.
  const outstandingOf = useCallback(
    (row: SalesOrderLine) => {
      // A CLOSED line is outstanding NOTHING, whatever its two quantities say. A book
      // re-upload closes a line by absence without knowing what shipped, so `qty_delivered`
      // stays 0 and `ordered - delivered` read the whole quantity as still owed: SO397450
      // showed 306 Completed lines and a footer summing 39,008 outstanding.
      if ((row.line_status ?? 'open') !== 'open') return 0;
      // Off the SERVER outside an edit session, so this grid, its footer and the Totals
      // card above all print the one figure the backend computed.
      if (!isEditing && row.outstanding_qty !== undefined && row.outstanding_qty !== null) {
        return row.outstanding_qty;
      }
      const ordered = isEditing
        ? Number(draftOrRow(lineDrafts, row).qty_ordered)
        : Number(row.qty_ordered);
      if (!Number.isFinite(ordered)) return 0;
      return Math.max(ordered - Number(row.qty_delivered), 0);
    },
    [isEditing, lineDrafts],
  );

  const amountOf = useCallback(
    (row: SalesOrderLine) => {
      if (!isEditing) {
        return lineAmount(
          String(row.qty_ordered), row.unit_price ?? '', row.discount ?? '', row.line_total,
        );
      }
      const draft = draftOrRow(lineDrafts, row);
      // The stated `line_total` is what the source document charged, so it wins - until one
      // of the figures it was charged ON is edited, at which point it no longer describes
      // what is on the screen and the arithmetic does.
      const touched =
        draft.qty_ordered !== String(row.qty_ordered) ||
        draft.unit_price !== (row.unit_price ?? '') ||
        draft.discount !== (row.discount ?? '');
      return lineAmount(
        draft.qty_ordered, draft.unit_price, draft.discount, touched ? null : row.line_total,
      );
    },
    [isEditing, lineDrafts],
  );

  const qtyOrderedTotal = useMemo(
    () =>
      lines.reduce((sum, l) => {
        const qty = isEditing
          ? Number(draftOrRow(lineDrafts, l).qty_ordered)
          : Number(l.qty_ordered);
        return sum + (Number.isFinite(qty) ? qty : 0);
      }, 0),
    [lines, isEditing, lineDrafts],
  );
  const qtyDeliveredTotal = useMemo(
    () => lines.reduce((sum, l) => sum + Number(l.qty_delivered), 0),
    [lines],
  );
  const outstandingTotal = useMemo(
    () => lines.reduce((sum, l) => sum + outstandingOf(l), 0),
    [lines, outstandingOf],
  );
  const amountTotal = useMemo(() => {
    const amounts = lines.map(amountOf).filter((a): a is string => a !== null);
    return amounts.length ? sumMoney(amounts) : null;
  }, [lines, amountOf]);

  const columns = useMemo<ColumnDef<SalesOrderLine>[]>(
    () => [
      {
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          if (isEditing) {
            const draft = lineDrafts[row.original.id];
            const selectId = `so-edit-line-${row.original.id}-product`;
            return (
              <>
                <label className="sr-only" htmlFor={selectId}>
                  Product on {row.original.sku}
                </label>
                {/* SERVER-SEARCHED, never a static list. `products/select` caps at 100 rows
                    against ~22,000 active products, so a static option list holds 0.5% of
                    the catalogue and answers "no products match" for the rest.
                    `selectedOption` is what keeps the line's OWN product readable when it
                    is not on the page that came back. */}
                <SearchableSelect
                  id={selectId}
                  value={draft?.sku ?? row.original.sku}
                  onChange={(v) =>
                    setLineDrafts((prev) => ({
                      ...prev,
                      [row.original.id]: { ...draftOrRow(prev, row.original), sku: v },
                    }))
                  }
                  paginated
                  pageSize={SELECT_PAGE_SIZE}
                  fetchOptions={searchProductOptions}
                  selectedOption={productFallback(row.original, draft?.sku)}
                  placeholder="Select product"
                  emptyMessage="No product found."
                  size="sm"
                />
              </>
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
        meta: { headerTitle: 'Product' },
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
        // One `td` per column, so the sum sits UNDER the column it sums and needs no label.
        // Rendered by the shared grid (`DataGridTable`) as soon as any column declares a
        // `footer`, which is why this is a column property rather than a hand-rolled tfoot.
        footer: () => fmtInt(qtyOrderedTotal),
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
        footer: () => fmtInt(qtyDeliveredTotal),
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
        // cell prints, so "sort by what is outstanding" sorts by the figure on screen - an
        // id-only column carries a sort arrow it cannot honour.
        //
        // In an EDIT session it recomputes from the draft quantity, live: typing 400 over
        // 320 on a line with 100 delivered has to show 300 owed straight away, or the row
        // states two figures that contradict each other until the page is reloaded.
        accessorFn: (line) =>
          Math.max(Number(line.qty_ordered) - Number(line.qty_delivered), 0),
        header: ({ column }) => <DataGridColumnHeader title="Outstanding qty" column={column} />,
        cell: ({ row }) => fmtInt(outstandingOf(row.original)),
        size: 140,
        footer: () => fmtInt(outstandingTotal),
        meta: {
          headerTitle: 'Outstanding qty',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'unit_price',
        accessorFn: (line) => Number(line.unit_price ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Unit price" column={column} />,
        cell: ({ row }) => {
          if (isEditing) {
            const draft = draftOrRow(lineDrafts, row.original);
            return (
              <Input
                type="number"
                min={0}
                step="0.01"
                aria-label={`Unit price on ${row.original.sku}`}
                value={draft.unit_price}
                onChange={(e) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [row.original.id]: {
                      ...draftOrRow(prev, row.original),
                      unit_price: e.target.value,
                    },
                  }))
                }
                className="h-8 text-right tabular-nums"
              />
            );
          }
          return fmtMoneyCell(row.original.unit_price);
        },
        size: 140,
        meta: {
          headerTitle: 'Unit price',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'discount',
        accessorFn: (line) => Number(line.discount ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Discount" column={column} />,
        cell: ({ row }) => {
          if (isEditing) {
            const draft = draftOrRow(lineDrafts, row.original);
            return (
              <Input
                type="number"
                min={0}
                step="0.01"
                aria-label={`Discount on ${row.original.sku}`}
                value={draft.discount}
                onChange={(e) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [row.original.id]: {
                      ...draftOrRow(prev, row.original),
                      discount: e.target.value,
                    },
                  }))
                }
                className="h-8 text-right tabular-nums"
              />
            );
          }
          return fmtMoneyCell(row.original.discount);
        },
        size: 130,
        meta: {
          headerTitle: 'Discount',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        id: 'line_total',
        // The figure the CELL prints, not the stored column: a line with a price and no
        // stated total shows its arithmetic and would otherwise sort as 0, the same trap the
        // Outstanding qty column above avoids.
        accessorFn: (line) => Number(amountOf(line) ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        cell: ({ row }) => fmtMoneyCell(amountOf(row.original)),
        size: 150,
        footer: () => fmtMoneyCell(amountTotal),
        meta: {
          headerTitle: 'Total',
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
        // The same light chip as every other pill on this page, worded the way AutoCount
        // words it - the same helper the header pill and the list column use.
        cell: ({ row }) => (
          <Badge
            variant={salesOrderStatusVariant(row.original.line_status ?? 'open')}
            appearance="light"
            size="md"
          >
            {salesOrderStatusLabel(row.original.line_status ?? 'open')}
          </Badge>
        ),
        size: 130,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'order_inquiry',
        accessorFn: (row) => row.order_inquiry?.inquiry_no ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Order inquiry" column={column} />
        ),
        // What purchasing has already been told about this line, by the number they quote.
        // A dash is the honest answer for a line nobody has raised an inquiry on: the
        // planning record only mirrors an order somebody adopted, and most of the book is
        // not adopted.
        cell: ({ row }) => {
          const inquiry = row.original.order_inquiry;
          if (!inquiry) return <span className="text-muted-foreground">-</span>;
          return (
            <div className="flex min-w-0 items-center gap-1.5">
              <span
                className="min-w-0 truncate tabular-nums"
                title={inquiry.inquiry_no ?? ''}
              >
                {inquiry.inquiry_no ?? '-'}
              </span>
              <OrderInquiryStatePill state={inquiry.state} />
            </div>
          );
        },
        size: 200,
        meta: { headerTitle: 'Order inquiry' },
      },
      {
        // AC-I9: WHERE this line's Buy actually sits. The same child table the order
        // inquiry worklist's "Linked to" column and the PO occupancy panel read, so the
        // three surfaces answer with one voice. A line whose inquiry row exists but holds
        // no link reads "Not linked"; a line with no inquiry row at all reads "-", which
        // is the difference between "nothing has been linked" and "nobody was told".
        id: 'linked_to',
        accessorFn: (row) => row.linked_to ?? null,
        header: ({ column }) => <DataGridColumnHeader title="Linked to" column={column} />,
        cell: ({ row }) => {
          const links = row.original.linked_to;
          if (!links) return <span className="text-muted-foreground">-</span>;
          if (links.length === 0)
            return <span className="text-muted-foreground">Not linked</span>;
          return (
            <div className="min-w-0 space-y-0.5">
              {links.map((link, index) => {
                const where = link.line_label || link.location || null;
                const due = link.expected_date ? fmtDate(link.expected_date) : null;
                // WHEN it lands, beside where it sits (AC-G7). A link that says which SPO
                // covers this line and not when it arrives answers half the question the
                // person reading it came with.
                const label = `${link.document}${where ? ` ${where}` : ''} ${link.qty}${
                  due ? ` due ${due}` : ''
                }`;
                return (
                  <span
                    // The INDEX is always in the key. One line can be linked to the same
                    // SPO line twice - the SPO covers it in two goes, each link carrying
                    // its own quantity - and kind + document + label collided on the
                    // second, which React reported as two children with the same key.
                    key={`${link.kind}-${link.document}-${where ?? 'x'}-${index}`}
                    className="flex min-w-0 items-center gap-1"
                    title={link.late ? `${label} - arrives late` : label}
                  >
                    <span className="shrink-0 rounded-sm bg-muted px-1 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
                      {link.kind}
                    </span>
                    <span className="truncate tabular-nums">{label}</span>
                    {/* AC-P3-7: it lands after the line needs it. Purchasing decides;
                        nothing is unlinked for lateness. */}
                    {link.late ? (
                      <span className="shrink-0 rounded-sm bg-amber-100 px-1 py-0.5 text-[10px] font-medium text-amber-800">
                        arrives late
                      </span>
                    ) : null}
                  </span>
                );
              })}
            </div>
          );
        },
        size: 240,
        meta: { headerTitle: 'Linked to' },
      },
      {
        // AC-D4: the board's two compositions, on the order they belong to. The SECONDARY
        // surface for the same question - the board is where the decision is taken, this is
        // where somebody looking at the order alone can see what was taken.
        id: 'supply_suggested',
        accessorFn: (row) => row.supply_proposed ?? null,
        header: ({ column }) => <DataGridColumnHeader title="Suggested" column={column} />,
        cell: ({ row }) => (
          <SupplyText
            parts={row.original.supply_proposed}
            ownLocation={row.original.warehouse_code}
            absent={row.original.decision_revision == null ? '-' : 'Not recorded'}
          />
        ),
        size: 220,
        meta: { headerTitle: 'Suggested' },
      },
      {
        id: 'supply_decided',
        accessorFn: (row) => row.supply_decided ?? null,
        header: ({ column }) => <DataGridColumnHeader title="Decided" column={column} />,
        cell: ({ row }) => (
          <SupplyText
            parts={row.original.supply_decided}
            ownLocation={row.original.warehouse_code}
            absent="-"
          />
        ),
        size: 220,
        meta: { headerTitle: 'Decided' },
      },
      {
        id: 'decision_revision',
        accessorFn: (row) => row.decision_revision ?? null,
        header: ({ column }) => <DataGridColumnHeader title="Decision" column={column} />,
        // Which confirmed revision covers this line. A line the active decision left out is
        // as undecided as a line on an order nobody planned, and both read "-".
        cell: ({ row }) =>
          row.original.decision_revision == null ? (
            <span className="text-muted-foreground">-</span>
          ) : (
            <span className="tabular-nums">{`Rev ${row.original.decision_revision}`}</span>
          ),
        size: 110,
        meta: { headerTitle: 'Decision' },
      },
    ],
    [
      isEditing,
      lineDrafts,
      warehouseSelectOptions,
      uomSelectOptions,
      outstandingOf,
      amountOf,
      qtyOrderedTotal,
      qtyDeliveredTotal,
      outstandingTotal,
      amountTotal,
    ],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.id,
    state: { sorting, globalFilter: lineSearch },
    onSortingChange: setSorting,
    onGlobalFilterChange: setLineSearch,
    // The whole ROW answers the search, so every column is allowed to carry it and the
    // matcher below decides. Left to the default, only string columns qualify, which made
    // the filter depend on which columns happen to hold strings.
    getColumnCanGlobalFilter: () => true,
    globalFilterFn: (row, _columnId, value) => lineMatches(row.original, String(value ?? '')),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    // Paged like every other listing in the product, so the footer can say "1 - 25 of 213"
    // instead of leaving a 200-line contract as one endless scroll with no count on it.
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });
  const visibleLineCount = table.getFilteredRowModel().rows.length;

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
  const lineCount = so.line_count ?? lines.length;

  const handleSave = async () => {
    setError(null);
    // No order-type check. 96% of this book carries no classification, so refusing the save
    // on an empty one made most orders un-editable; an empty class means "leave the stored
    // classification alone", which is what the BE does with it.
    if (!customerCode) return setError('Select a customer.');
    // `id` is sent so the BE matches this line by id rather than falling back to SKU.
    // Location / delivery date / UoM / price / discount ride the SAME upsert as SKU/qty -
    // see the class docstring - carrying either what the person typed or, for an untouched
    // line, exactly what the order loaded with.
    const cleanedLines = so.lines.map((ln) => {
      const draft = lineDrafts[ln.id];
      return {
        id: ln.id,
        sku: draft?.sku ?? ln.sku,
        qty_ordered: Number(draft?.qty_ordered ?? ln.qty_ordered),
        warehouse_code: draft?.warehouse_code ?? ln.warehouse_code ?? '',
        required_date: draft?.required_date ?? ln.required_date?.slice(0, 10) ?? '',
        uom: draft?.uom ?? ln.uom ?? '',
        unit_price: draft?.unit_price ?? ln.unit_price ?? '',
        discount: draft?.discount ?? ln.discount ?? '',
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
          demand_class: demandClass || null,
          customer_code: customerCode,
          priority,
          order_date: orderDate || null,
          requested_delivery_date: requestedDate || null,
          sales_agent_id: agentId || null,
          ...(linesUnchanged
            ? {}
            : {
                lines: cleanedLines.map((l) => ({
                  ...l,
                  // Empty means "clear this figure", which is what the BE reads a `null` as.
                  unit_price: l.unit_price || null,
                  discount: l.discount || null,
                })),
              }),
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
      {/* The record header - what the order IS, and what can be done to it. Above the tabs,
          because it belongs to the whole record rather than to any one of its concerns. */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="text-lg">{so.so_number}</CardTitle>
              <Badge variant={salesOrderStatusVariant(so.status)} appearance="light" size="md">
                {salesOrderStatusLabel(so.status)}
              </Badge>
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
                {/* The main action on this page, so it wears the main colour - the same
                    filled primary button an Add is on every list. */}
                <Button variant="primary" size="sm" className="gap-1.5" onClick={() => beginEdit(so)}>
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
              {/* Straight to the board, on THIS order and THIS batch (AC-P3-1): the change
                  is decided where the plan is, in one vocabulary. */}
              <Button asChild variant="outline" size="sm">
                <Link
                  href={`/project-sales/fulfilment-planning?orders=${encodeURIComponent(
                    so.so_number,
                  )}&batch=${encodeURIComponent(planningChangeBatch.id)}`}
                >
                  Plan
                </Link>
              </Button>
            </div>
          ) : null}
        </CardHeader>
      </Card>

      {/* One tab per concern of the order, the same shape as the user detail page. The tab
          set is the SAME in view and in edit - editing swaps a value for an input inside the
          tab it already lived in. */}
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
          <TabsTrigger value="delivery">
            <Truck />
            <span>Delivery</span>
          </TabsTrigger>
          <TabsTrigger value="transfers">
            <Move />
            <span>Transfers</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="mt-0 space-y-4 focus-visible:outline-none">
          {/* Three cards, each at most TWO columns of label/value. One eleven-field grid four
              across reads as a wall; these are the three things a person asks about an order
              separately - what it is, who it is for, and what it comes to. Each is named as a
              region so a reader (and a test) can address one of them. */}
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Order</CardTitle>
              </CardHeading>
            </CardHeader>
            <section
              aria-label="Order"
              className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2"
            >
              {/* The PLANNING CLASS, read and written. It used to render `demand_class` and
                  edit `order_type` - a different column, NULL on 96% of this book - so what
                  the pill said and what the select set were never the same fact. The ERP
                  document type still rides along as a hint when the order carries one and it
                  says something the class does not already say. */}
              <Field label="Order type" htmlFor={isEditing ? 'so-edit-order-type' : undefined}>
                {isEditing ? (
                  <SearchableSelect
                    id="so-edit-order-type"
                    value={demandClass}
                    onChange={setDemandClass}
                    options={DEMAND_CLASS_OPTIONS}
                    // Unclassified is a real, common answer, so it must be reachable - and
                    // saving with it empty leaves the stored classification alone rather
                    // than clearing it.
                    placeholder="Unclassified"
                    clearable
                    size="sm"
                  />
                ) : (
                  (() => {
                    const cls = demandClassBadge(so.demand_class);
                    const hint = so.order_type_label;
                    const showHint = hint && hint !== cls.label;
                    return (
                      <span className="inline-flex flex-wrap items-center gap-1.5">
                        <Badge variant={cls.variant} appearance="light" size="md">
                          {cls.label}
                        </Badge>
                        {showHint ? (
                          // `text-2xs`, not `text-xs` - the view/edit parity test walks
                          // `span.text-xs` as the Field label selector, and this hint is a
                          // VALUE, not a label.
                          <span className="text-2xs font-normal text-muted-foreground">
                            {hint}
                          </span>
                        ) : null}
                      </span>
                    );
                  })()
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
                  <Badge
                    variant={salesOrderPriorityVariant(so.priority)}
                    appearance="light"
                    size="md"
                  >
                    {PRIORITY_LABELS[so.priority] ?? titleCase(so.priority)}
                  </Badge>
                )}
              </Field>
              {/* Correctable: the absorbed book took this date off a spreadsheet, and the
                  demand trend reads 24 months of this column. */}
              <Field label="Order date" htmlFor={isEditing ? 'so-edit-order-date' : undefined}>
                {isEditing ? (
                  <Input
                    id="so-edit-order-date"
                    type="date"
                    value={orderDate}
                    onChange={(e) => setOrderDate(e.target.value)}
                    className="h-8"
                  />
                ) : (
                  fmtDate(so.order_date)
                )}
              </Field>
              {/* `requested_delivery_date`, labelled the way the Lines tab labels the same
                  fact per line: what the customer is waiting for, not an internal request. */}
              <Field
                label="Delivery date"
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
              <Field label="Source">{SOURCE_LABELS[so.source ?? 'manual'] ?? 'Manual'}</Field>
              {/* What purchasing has been told to do about this order. Read-only in both
                  views, so nothing moves between them: it is a record of what happened,
                  not a field anybody sets here. Empty states as "-", never hidden. */}
              <Field label="Order inquiries">
                {(so.order_inquiries ?? []).length ? (
                  <span className="flex flex-col gap-1">
                    {(so.order_inquiries ?? []).map((inquiry, index) => (
                      <span key={inquiry.inquiry_no ?? index} className="block">
                        <Link
                          href={`/project-sales/order-inquiries?query=${encodeURIComponent(
                            so.so_number,
                          )}`}
                          className="text-primary hover:underline"
                          title={`${inquiry.rows_placed}/${inquiry.rows_total} placed`}
                        >
                          {inquiry.inquiry_no ?? 'Unnumbered'}
                        </Link>
                        {/* Who raised it and when, ON the header rather than in a
                            tooltip (AC-H2): "who pushed this to purchasing" is the
                            first thing asked of this field, and a fact nobody hovers
                            over is a fact nobody has. Malaysian wall clock, with the
                            hour - two revisions of one order are raised hours apart. */}
                        <span className="ms-1 font-normal text-muted-foreground">
                          · {inquiry.raised_by_name ?? 'Not recorded'}
                          {inquiry.raised_at
                            ? ` · ${formatDateTimeInMalaysia(inquiry.raised_at)}`
                            : ''}
                        </span>
                      </span>
                    ))}
                  </span>
                ) : (
                  '-'
                )}
              </Field>
            </section>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Customer</CardTitle>
              </CardHeading>
            </CardHeader>
            <section
              aria-label="Customer"
              className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2"
            >
              <Field label="Customer" htmlFor={isEditing ? 'so-edit-customer' : undefined}>
                {isEditing ? (
                  // SERVER-SEARCHED. The static list pulls the whole debtor master (6,397
                  // rows) for the browser to filter, which is why this select took seconds
                  // to open. `selectedOption` keeps the order's OWN customer readable when
                  // it is not on the page that came back.
                  <SearchableSelect
                    id="so-edit-customer"
                    value={customerCode}
                    onChange={setCustomerCode}
                    paginated
                    pageSize={SELECT_PAGE_SIZE}
                    fetchOptions={searchCustomerOptions}
                    selectedOption={
                      customerCode && customerCode === so.customer_code
                        ? { value: so.customer_code, label: so.customer_name || so.customer_code }
                        : undefined
                    }
                    placeholder="Select customer"
                    emptyMessage="No customer found."
                    size="sm"
                  />
                ) : (
                  so.customer_name || '-'
                )}
              </Field>
              <Field label="Customer code">{so.customer_code || '-'}</Field>
            </section>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Totals</CardTitle>
              </CardHeading>
            </CardHeader>
            {/* Named as a region so a reader (and a test) can tell this "Outstanding qty" from
                the lines grid's column of the same name. They share the phrase on purpose: it
                is the same quantity, once for the order and once per line. No Locations field:
                a location belongs to a LINE - one order routinely ships from two - and the
                Lines tab carries it per row. */}
            <section
              aria-label="Totals"
              className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2"
            >
              {/* What the order is worth, summed on the backend from the same line figures
                  the Lines tab prints. A dash, never RM 0.00, for an order nobody priced. */}
              <Field label="Total amount">
                {so.total_amount ? formatMyrExact(so.total_amount) : '-'}
              </Field>
              <Field label="Total qty">{fmtInt(so.total_qty)}</Field>
              {/* ALWAYS shown, even when it equals the total. It used to appear only when
                  the two differed, on the grounds that a repeated figure is noise - but a
                  field that comes and goes is worse: on a wholly open order the reader has
                  to work out from its ABSENCE that nothing has shipped, and a section that
                  hides on some records teaches nobody where anything lives. */}
              <Field label="Outstanding qty">{fmtInt(so.committed_qty)}</Field>
              <Field label="Lines">{fmtInt(lineCount)}</Field>
            </section>
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
                  No note. Absorbed and imported orders keep the customer name and code here
                  when the customer could not be matched.
                </p>
              )}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="lines" className="mt-0 focus-visible:outline-none">
          {/* Lines - always rendered, explicit empty state. */}
          <DataGrid
            table={table}
            recordCount={visibleLineCount}
            isLoading={false}
            tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
            emptyMessage={
              lineSearch.trim()
                ? 'No line on this order matches that product.'
                : 'This sales order has no lines.'
            }
            // A real key, not the empty "do not persist" one: a 200-line order is read with
            // the same few columns every time, and the choice has to survive the visit. Keyed
            // off the permission slug plus a stable id, never the record's own path.
            listingKey="scm.dashboard.view::sales-order-lines"
          >
            <Card>
              <CardHeader className="flex-wrap gap-3">
                <CardHeading>
                  <CardTitle>Order lines</CardTitle>
                </CardHeading>
                <CardToolbar className="flex-wrap">
                  {/* The order is the unit here, so the search is over the lines already
                      loaded - no request, no paging, and it answers "is this item on this
                      order" on a 200-line contract. */}
                  <div className="relative">
                    <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      aria-label="Search lines"
                      placeholder="Search product..."
                      value={lineSearch}
                      onChange={(e) => setLineSearch(e.target.value)}
                      className="w-56 ps-9"
                    />
                    {lineSearch ? (
                      <Button
                        mode="icon"
                        variant="dim"
                        className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                        aria-label="Clear line search"
                        onClick={() => setLineSearch('')}
                      >
                        <X />
                      </Button>
                    ) : null}
                  </div>
                  <DataGridColumnVisibility
                    table={table}
                    trigger={
                      <Button variant="outline" size="sm" className="gap-1.5">
                        <Columns3 className="size-4" />
                        Columns
                      </Button>
                    }
                  />
                </CardToolbar>
              </CardHeader>
              <CardTable>
                <ScrollArea>
                  <DataGridTable />
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              </CardTable>
              {/* The same footer every list in the product carries - "1 - 25 of 213" and the
                  page sizes. A 200-line contract had neither, so the only way to know how
                  many lines it held was to scroll to the bottom and count. */}
              <CardFooter>
                <DataGridPagination />
              </CardFooter>
            </Card>
          </DataGrid>
        </TabsContent>

        <TabsContent value="delivery" className="mt-0 focus-visible:outline-none">
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
                  {fmtInt(so.committed_qty)} outstanding across {fmtInt(so.open_line_count ?? 0)}{' '}
                  {(so.open_line_count ?? 0) === 1 ? 'line' : 'lines'}.
                </p>
              ) : (
                // No CTA to a Create DO button any more: the list no longer carries one, and
                // pointing at a control that is not there is worse than saying nothing.
                <p className="text-sm text-muted-foreground">
                  Nothing delivered yet. Deliveries recorded against this order show here.
                </p>
              )}
            </div>
          </Card>
        </TabsContent>

        {/* AC-E6: the movements this order's supply decision asked for. The SAME grid the
            Transfers page is, pinned to this order - so a transfer cannot read one way here
            and another way there. Always rendered; it carries its own empty state. */}
        <TabsContent value="transfers" className="mt-0 focus-visible:outline-none">
          <StockTransfersPanel
            salesOrderId={so.id}
            listingKey="scm.sales_orders.view::stock-transfers"
            showFilters={false}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default SalesOrderDetail;
