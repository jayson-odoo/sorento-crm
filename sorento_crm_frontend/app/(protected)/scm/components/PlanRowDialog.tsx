'use client';

import { useMemo, useState, type ReactNode } from 'react';
import {
  type ColumnDef,
  type ExpandedState,
  type OnChangeFn,
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight } from 'lucide-react';

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';

import { EM_DASH, fmtDate, fmtInt, fmtMoney, fmtSupplierCost } from '../lib/format';
import { useContainerRequestDrill } from '../hooks/useContainerRequestDrill';
import { useLocationStock } from '../reorder/hooks/useReorderRun';
import { StockDocumentsPanel } from '../../project-sales/fulfilment-planning/components/StockDocumentsPanel';
import type {
  ContainerRequestDrillIncomingPlRow,
  ContainerRequestDrillPoRow,
  ContainerRequestDrillSpoRow,
} from '../services/containerRequestDrillService';

/**
 * ONE lightbox for the SCM family (R7, AC-B1/AC-B7).
 *
 * Every figure a buyer would want to argue with opens a dialog naming the DOCUMENTS behind
 * it: the sales orders, the shipping orders, the packing lists, the purchase orders, the
 * stock rows. What this replaces on the loading plan and the SPO planner was a hover popover
 * per number - mouse-only, too narrow for a document table, dismissed by the mouse drifting
 * off it, and (inside a DataGrid cell) painted over by the sticky column beside it, which is
 * why each one carried a `PopoverPortal` workaround.
 *
 * The shell is copied from the reorder-revamp lane's `PlanRowDialogs.tsx` rather than
 * reinvented, so the two screens' lightboxes are the same object to a reader; at whichever
 * merge lands second, that lane re-points its import here and one file survives (plan
 * section 9).
 *
 * The shell knows nothing about any body: it is a titled frame, and the caller renders what
 * belongs inside. A registry keyed on `kind` would have to import every body and so every
 * body's data hook, which is how one dialog comes to fetch for six screens.
 *
 * S9 (3 Sep, plan section 3.9): every body in this file renders on the repo's own `DataGrid`
 * rather than a plain `<table>` - the SPO document detail's own line table
 * (`SPODocumentDetail.tsx`) is the reference this family now matches: `TabsList variant="line"`,
 * fixed-width resizable columns, and a footer TOTAL row under whichever column the cell's own
 * figure sums. `DrillTable` below is the one place that wiring lives, because every body here
 * is the same shape - a caller-held list of rows, no server pagination, no per-user column
 * memory (a dialog's columns are not a personal preference, so `listingKey` is always `null`).
 * `OnHandTable` builds its own table instead of going through it: its rows expand in place,
 * which needs TanStack's expanded-row state passed straight to `useReactTable`.
 */

export type PlanRowDialogKind =
  | 'project'
  | 'retail'
  | 'on_hand'
  | 'spo'
  | 'incoming_pl'
  | 'po'
  | 'po_takes'
  | 'so_coverage'
  // The invoice blocks a loading plan's "They hold" figure is the SUM of (S6): one uploaded
  // file holds five stacked invoices, and a figure that is five numbers added up has to be
  // openable or it cannot be checked against the paper.
  | 'blocks';

/** The word in front of the product code. Kept here so the eight titles cannot drift. */
export const PLAN_ROW_DIALOG_TITLES: Record<PlanRowDialogKind, string> = {
  project: 'Project',
  retail: 'Retail',
  on_hand: 'On hand',
  spo: 'SPO',
  incoming_pl: 'Incoming PL',
  po: 'PO',
  po_takes: 'PO covers',
  so_coverage: 'SO covered',
  blocks: 'Packed',
};

// ---------------------------------------------------------------------------
// Table furniture - exported so a body written by another screen looks the same
//
// `ContainerRequestScheduleMatrix.tsx` is the one remaining consumer: its schedule PIVOT is
// not a list of rows (it is a product/SO axis against day/week/month buckets) and so is never
// a `DataGrid` - these stay here for it.
// ---------------------------------------------------------------------------

export function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return (
    <th
      className={cn(
        'whitespace-nowrap px-2 py-1.5 font-medium text-muted-foreground',
        right ? 'text-right' : 'text-left',
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  right,
  title,
  className,
  colSpan,
}: {
  children: ReactNode;
  right?: boolean;
  title?: string;
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      className={cn('px-2 py-1.5', right && 'text-right tabular-nums', className)}
      title={title}
      colSpan={colSpan}
    >
      {children}
    </td>
  );
}

export function EmptyRow({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-2 py-6 text-center text-muted-foreground">
        {children}
      </td>
    </tr>
  );
}

export function LoadingRows({ colSpan }: { colSpan: number }) {
  return (
    <>
      {Array.from({ length: 3 }).map((_, i) => (
        <tr key={i}>
          <td colSpan={colSpan} className="px-2 py-1.5">
            <Skeleton className="h-4 w-full" />
          </td>
        </tr>
      ))}
    </>
  );
}

export function DocTable({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">{children}</table>
    </div>
  );
}

/** What a body says when a drill has no SPO on its way to a pool for this product. */
export const NO_SPO_TO_POOL = 'No SPO is on its way to a site pool for this product.';

function textCell(value: string | null | undefined) {
  return value ? value : <span className="text-muted-foreground">{EM_DASH}</span>;
}

function moneyCell(value: number | null | undefined) {
  return value === null || value === undefined ? (
    <span className="text-muted-foreground">{EM_DASH}</span>
  ) : (
    fmtMoney(value)
  );
}

/** Every right-aligned quantity/money/date column shares this header + cell alignment. */
export const RIGHT: { headerClassName: string; cellClassName: string } = {
  headerClassName: 'text-right',
  cellClassName: 'text-right tabular-nums',
};

/** One `Skeleton` bar, reused across every column's `meta.skeleton` in this file. */
const SKELETON_CELL = <Skeleton className="h-4 w-full" />;

/** The label half of a footer TOTAL row (AC-J3) - under whichever column comes first. */
export const TOTAL_LABEL = <span className="text-muted-foreground">Total</span>;

/**
 * A tab's own table (AC-J2): every row the caller already holds, in the repo's `DataGrid`,
 * with no server pagination (there is nothing left to page - the caller passed the whole
 * list) and no per-user column persistence (`listingKey={null}`: a dialog's columns are not a
 * personal preference). The horizontal scroll a wide table needs is the grid's own
 * `overflow-x-auto` scroller, which stays INSIDE the dialog body - the dialog itself never
 * grows past `max-h-[85vh]`.
 */
export function DrillTable<TRow extends object>({
  columns,
  rows,
  getRowId,
  isLoading,
  emptyMessage,
}: {
  columns: ColumnDef<TRow>[];
  rows: TRow[];
  getRowId?: (row: TRow, index: number) => string;
  isLoading?: boolean;
  emptyMessage: ReactNode;
}) {
  const table = useReactTable({
    columns,
    data: rows,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={Boolean(isLoading)}
      listingKey={null}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={emptyMessage}
    >
      <DataGridTable />
    </DataGrid>
  );
}

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/** `2026-04` reads `Apr 26`. The bucket is a month, so it is never rendered as a date. */
export function monthLabel(month: string | null): string {
  if (!month) return EM_DASH;
  const [year, m] = month.split('-');
  const name = MONTHS[Number(m) - 1];
  if (!name || !year) return month;
  return `${name} ${year.slice(2)}`;
}

// ---------------------------------------------------------------------------
// Project / Retail - the orders behind a channel's number, and the 12-month series
// ---------------------------------------------------------------------------

/** One open sales-order line behind the Project or Retail figure. */
export interface PlanDemandLineRow {
  so_number: string | null;
  customer: string | null;
  project: string | null;
  agent: string | null;
  /** What the customer pays, in ringgit. Null when the line carries no price. */
  price: number | null;
  qty: number;
  required_date: string | null;
  /** The sales order's own page, when the caller can name one. */
  href?: string | null;
}

/** One month of the two 12-month series (AC-B2 / AC-B6). */
export interface PlanHistoryPoint {
  month: string;
  project_qty: number;
  retail_qty: number;
}

function peakOf(history: PlanHistoryPoint[], channel: 'project' | 'retail') {
  let peak: PlanHistoryPoint | null = null;
  for (const point of history) {
    const qty = channel === 'project' ? point.project_qty : point.retail_qty;
    const best = peak ? (channel === 'project' ? peak.project_qty : peak.retail_qty) : -1;
    if (qty > best) peak = point;
  }
  if (!peak) return null;
  return {
    month: peak.month,
    qty: channel === 'project' ? peak.project_qty : peak.retail_qty,
  };
}

/**
 * One channel's demand, twice: what is still open before the plan's cut-off, and what the
 * product's order history says over the last twelve months.
 *
 * Controlled and pure - the loading-plan grid already holds both payloads (the build's
 * `include_lines` read and the history read), so a second fetch here would ask the server for
 * what the caller is holding. `initialTab='history'` is how the Project peak / Retail peak
 * cells open the same dialog on the series they name (AC-B6).
 */
export function ProjectRetailTabs({
  channel,
  lines,
  history,
  initialTab = 'open',
  focus,
  loading,
}: {
  channel: 'project' | 'retail';
  lines: PlanDemandLineRow[];
  history: PlanHistoryPoint[];
  initialTab?: 'open' | 'history';
  /** Which series the reader came in for. Defaults to the channel's own. */
  focus?: 'project' | 'retail';
  loading?: boolean;
}) {
  const focused = focus ?? channel;
  const total = useMemo(() => lines.reduce((sum, l) => sum + (l.qty || 0), 0), [lines]);
  const projectPeak = peakOf(history, 'project');
  const retailPeak = peakOf(history, 'retail');
  // AC-J3: the history tab foots BOTH series - the peak line above states the biggest month,
  // this states the whole twelve.
  const projectTotal = useMemo(
    () => history.reduce((sum, p) => sum + (p.project_qty || 0), 0),
    [history],
  );
  const retailTotal = useMemo(
    () => history.reduce((sum, p) => sum + (p.retail_qty || 0), 0),
    [history],
  );
  const openLabel =
    channel === 'project'
      ? `Open project SO lines (${fmtInt(lines.length)})`
      : `Open sales orders (${fmtInt(lines.length)})`;

  const openColumns = useMemo<ColumnDef<PlanDemandLineRow>[]>(
    () => [
      {
        id: 'so_number',
        header: 'Sales order',
        cell: ({ row }) => {
          const l = row.original;
          return l.href ? (
            <a className="hover:underline" href={l.href}>
              {l.so_number ?? 'Not numbered'}
            </a>
          ) : (
            (l.so_number ?? 'Not numbered')
          );
        },
        footer: () => TOTAL_LABEL,
        size: 130,
        meta: { skeleton: SKELETON_CELL },
      },
      {
        id: 'customer',
        header: 'Customer',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.customer ?? undefined}>
            {textCell(row.original.customer)}
          </span>
        ),
        size: 170,
        meta: { skeleton: SKELETON_CELL },
      },
      {
        id: 'project',
        header: 'Project',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.project ?? undefined}>
            {textCell(row.original.project)}
          </span>
        ),
        size: 170,
      },
      {
        id: 'agent',
        header: 'Agent',
        cell: ({ row }) => textCell(row.original.agent),
        size: 90,
      },
      {
        id: 'price',
        header: 'Price',
        cell: ({ row }) => moneyCell(row.original.price),
        size: 100,
        meta: RIGHT,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => fmtInt(row.original.qty),
        footer: () => fmtInt(total),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'required_date',
        header: 'Required',
        cell: ({ row }) => fmtDate(row.original.required_date),
        size: 110,
        meta: RIGHT,
      },
    ],
    [total],
  );

  const historyColumns = useMemo<ColumnDef<PlanHistoryPoint>[]>(
    () => [
      {
        id: 'month',
        header: 'Month',
        cell: ({ row }) => monthLabel(row.original.month),
        footer: () => TOTAL_LABEL,
        size: 110,
        meta: { skeleton: SKELETON_CELL },
      },
      {
        id: 'project_qty',
        header: 'Project',
        cell: ({ row }) => fmtInt(row.original.project_qty),
        footer: () => fmtInt(projectTotal),
        size: 100,
        meta: {
          ...RIGHT,
          cellClassName: cn(RIGHT.cellClassName, focused === 'project' && 'font-medium'),
        },
      },
      {
        id: 'retail_qty',
        header: 'Retail',
        cell: ({ row }) => fmtInt(row.original.retail_qty),
        footer: () => fmtInt(retailTotal),
        size: 100,
        meta: {
          ...RIGHT,
          cellClassName: cn(RIGHT.cellClassName, focused === 'retail' && 'font-medium'),
        },
      },
    ],
    [focused, projectTotal, retailTotal],
  );

  return (
    <Tabs defaultValue={initialTab}>
      <TabsList variant="line">
        <TabsTrigger value="open">{openLabel}</TabsTrigger>
        <TabsTrigger value="history">12-month history</TabsTrigger>
      </TabsList>

      <TabsContent value="open">
        <DrillTable
          columns={openColumns}
          rows={lines}
          getRowId={(l, i) => `${l.so_number ?? 'unnumbered'}-${i}`}
          isLoading={loading}
          emptyMessage="Nothing open on this channel for this product."
        />
      </TabsContent>

      <TabsContent value="history">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-4 text-xs">
            <span className={cn(focused === 'project' && 'font-medium')}>
              {`Project peak ${projectPeak ? `${fmtInt(projectPeak.qty)} ${monthLabel(projectPeak.month)}` : EM_DASH}`}
            </span>
            <span className={cn(focused === 'retail' && 'font-medium')}>
              {`Retail peak ${retailPeak ? `${fmtInt(retailPeak.qty)} ${monthLabel(retailPeak.month)}` : EM_DASH}`}
            </span>
          </div>
          <DrillTable
            columns={historyColumns}
            rows={history}
            getRowId={(p) => p.month}
            isLoading={loading}
            emptyMessage="Nothing was ordered in the last twelve months."
          />
        </div>
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// On hand - the site pools' stock, row by row, with the documents under each
// ---------------------------------------------------------------------------

/** One site-pool stock row, as `useLocationStock` returns it. */
interface OnHandLocation {
  warehouse_id: string;
  warehouse_code: string | null;
  on_hand: number;
  reserved: number;
  free: number;
  so_qty: number;
  spo_qty: number;
  available: number;
  is_pool?: boolean;
  po_qty?: number | null;
}

/**
 * Reorder planning's On hand lightbox, verbatim (AC-B3 / AC-G3): the SITE POOL rows only,
 * each expanding to the documents standing behind that location.
 *
 * Pools only, because a project bin holds stock already spoken for by an Order Inquiry, and
 * counting it here would disagree with the cell, which nets pools alone. A response with no
 * pool row at all falls back to everything it was given, rather than showing an empty table
 * for a product that plainly has stock somewhere.
 *
 * Builds its own `useReactTable` rather than going through `DrillTable`: the expanding row
 * needs TanStack's own expanded-row state, which `DrillTable`'s callers never do.
 */
export function OnHandTable({ productId }: { productId: string }) {
  const stock = useLocationStock(productId, Boolean(productId));
  const [openRow, setOpenRow] = useState<string | null>(null);

  const rows = useMemo(() => {
    const locations = (stock.data?.locations ?? []) as OnHandLocation[];
    const pools = locations.filter((l) => l.is_pool);
    return pools.length ? pools : locations;
  }, [stock.data]);

  const total = rows.reduce((sum, l) => sum + (l.on_hand || 0), 0);

  const columns = useMemo<ColumnDef<OnHandLocation>[]>(
    () => [
      {
        id: 'expand',
        header: '',
        cell: ({ row }) =>
          row.getIsExpanded() ? (
            <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
          ) : (
            <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden />
          ),
        size: 32,
        enableResizing: false,
      },
      {
        id: 'location',
        header: 'Location',
        cell: ({ row }) => (
          <span title={row.original.warehouse_code ?? undefined}>
            {textCell(row.original.warehouse_code)}
          </span>
        ),
        footer: () => <span className="text-muted-foreground">Site pools</span>,
        size: 120,
        meta: {
          skeleton: SKELETON_CELL,
          expandedContent: (loc: OnHandLocation) => (
            <StockDocumentsPanel productId={productId} warehouseId={loc.warehouse_id} />
          ),
        },
      },
      {
        id: 'on_hand',
        header: 'On hand',
        cell: ({ row }) => fmtInt(row.original.on_hand),
        footer: () => fmtInt(total),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'reserved',
        header: 'Reserved',
        cell: ({ row }) => fmtInt(row.original.reserved),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'free',
        header: 'Free',
        cell: ({ row }) => fmtInt(row.original.free),
        size: 80,
        meta: RIGHT,
      },
      {
        id: 'so_qty',
        header: 'SO qty',
        cell: ({ row }) => fmtInt(row.original.so_qty),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'spo_qty',
        header: 'SPO qty',
        cell: ({ row }) => fmtInt(row.original.spo_qty),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'available',
        header: 'Available',
        cell: ({ row }) => (
          <span className={cn(row.original.available < 0 && 'text-destructive')}>
            {fmtInt(row.original.available)}
          </span>
        ),
        size: 100,
        meta: RIGHT,
      },
      {
        id: 'po_qty',
        // `po_qty` arrives with the reorder lane's own extension of this endpoint; until it
        // merges the column reads as "not stated", never as zero.
        header: 'PO qty',
        cell: ({ row }) =>
          row.original.po_qty === null || row.original.po_qty === undefined ? (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ) : (
            fmtInt(row.original.po_qty)
          ),
        size: 90,
        meta: RIGHT,
      },
    ],
    [productId, total],
  );

  const expanded: ExpandedState = openRow ? { [openRow]: true } : {};
  const onExpandedChange: OnChangeFn<ExpandedState> = (updater) => {
    const next = typeof updater === 'function' ? updater(expanded) : updater;
    const openIds = Object.keys(next).filter((id) => (next as Record<string, boolean>)[id]);
    setOpenRow(openIds[0] ?? null);
  };

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (l) => l.warehouse_id,
    state: { expanded },
    onExpandedChange,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  });

  return (
    <div className="space-y-2">
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={stock.isLoading}
        listingKey={null}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        onRowClick={(loc) => setOpenRow((cur) => (cur === loc.warehouse_id ? null : loc.warehouse_id))}
        emptyMessage="No stock rows for this product."
      >
        <DataGridTable />
      </DataGrid>
      {/* The newest stock timestamp for the product, never the moment this dialog asked. */}
      {stock.data?.as_of ? (
        <p className="text-2xs text-muted-foreground">
          Stock as of {formatDateTimeInMalaysia(stock.data.as_of)}
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SPO - what is on the water for the site pools
// ---------------------------------------------------------------------------

/** Columns shared by the open and history tabs - only the footer total differs. */
function spoColumns(totalQty: number): ColumnDef<ContainerRequestDrillSpoRow>[] {
  return [
    {
      id: 'spo_number',
      header: 'SPO',
      cell: ({ row }) => textCell(row.original.spo_number),
      footer: () => TOTAL_LABEL,
      size: 140,
      meta: { skeleton: SKELETON_CELL },
    },
    {
      id: 'packing_list',
      header: 'Packing list',
      cell: ({ row }) =>
        row.original.shipment_id ? (row.original.shipment_number ?? 'Draft') : 'Not shipped',
      size: 140,
    },
    {
      id: 'to',
      header: 'To',
      cell: ({ row }) => textCell(row.original.warehouse_code),
      size: 90,
    },
    {
      id: 'qty',
      header: 'Qty',
      cell: ({ row }) => fmtInt(row.original.qty),
      footer: () => fmtInt(totalQty),
      size: 90,
      meta: RIGHT,
    },
    {
      id: 'received',
      header: 'Received',
      cell: ({ row }) => fmtInt(row.original.received),
      size: 100,
      meta: RIGHT,
    },
    {
      id: 'eta',
      header: 'ETA',
      cell: ({ row }) => fmtDate(row.original.eta),
      size: 100,
      meta: RIGHT,
    },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) => textCell(row.original.status),
      size: 110,
    },
  ];
}

function spoRowId(r: ContainerRequestDrillSpoRow, i: number): string {
  return `${r.spo_number ?? 'unnumbered'}-${r.shipment_id}-${i}`;
}

/**
 * The shipping orders behind the SPO cell (AC-B4), open first and then what has landed.
 *
 * Rows come from `/container-requests/drill?kind=spo`, whose total IS the cell - see that
 * service's docstring for why the reader is `spo_allocations` and not the purchase-order
 * table (migration 420 moved every SPO document out of it). The open tab foots to that same
 * total; the history tab has none to defer to, so it sums its own rows (AC-J3).
 */
export function SpoTabs({ supplierId, productId }: { supplierId: string; productId: string }) {
  const drill = useContainerRequestDrill(supplierId, productId, 'spo');
  const open = (drill.data?.rows ?? []) as ContainerRequestDrillSpoRow[];
  const history = (drill.data?.history ?? []) as ContainerRequestDrillSpoRow[];

  const openTotal = drill.data?.total ?? open.reduce((s, r) => s + r.qty, 0);
  const historyTotal = history.reduce((s, r) => s + r.qty, 0);
  const openColumns = useMemo(() => spoColumns(openTotal), [openTotal]);
  const historyColumns = useMemo(() => spoColumns(historyTotal), [historyTotal]);

  return (
    <Tabs defaultValue="open">
      <TabsList variant="line">
        <TabsTrigger value="open">{`Open to pools (${fmtInt(open.length)})`}</TabsTrigger>
        <TabsTrigger value="history">{`History (${fmtInt(history.length)})`}</TabsTrigger>
      </TabsList>
      <TabsContent value="open">
        <DrillTable
          columns={openColumns}
          rows={open}
          getRowId={spoRowId}
          isLoading={drill.isLoading}
          emptyMessage={NO_SPO_TO_POOL}
        />
      </TabsContent>
      <TabsContent value="history">
        <DrillTable
          columns={historyColumns}
          rows={history}
          getRowId={spoRowId}
          isLoading={drill.isLoading}
          emptyMessage="No shipping order has landed here for this product."
        />
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// Incoming PL - packing lists on their way, reference only
// ---------------------------------------------------------------------------

/**
 * The packing lists behind the Incoming PL cell (AC-B4). One table, no tabs: a packing list
 * that has arrived is already the On hand dialog, so there is no landed half to show.
 */
export function IncomingPlTable({
  supplierId,
  productId,
  onOpenShipment,
}: {
  supplierId: string;
  productId: string;
  /** Opens the packing list. Absent = the number is plain text. */
  onOpenShipment?: (shipmentId: string) => void;
}) {
  const drill = useContainerRequestDrill(supplierId, productId, 'incoming_pl');
  const rows = (drill.data?.rows ?? []) as ContainerRequestDrillIncomingPlRow[];
  const total = drill.data?.total ?? rows.reduce((s, r) => s + r.qty, 0);

  const columns = useMemo<ColumnDef<ContainerRequestDrillIncomingPlRow>[]>(
    () => [
      {
        id: 'shipment_number',
        header: 'Packing list',
        cell: ({ row }) => {
          const r = row.original;
          return onOpenShipment ? (
            <button
              type="button"
              className="underline-offset-2 hover:underline"
              onClick={() => onOpenShipment(r.shipment_id)}
            >
              {r.shipment_number ?? 'Draft'}
            </button>
          ) : (
            (r.shipment_number ?? 'Draft')
          );
        },
        footer: () => TOTAL_LABEL,
        size: 150,
        meta: { skeleton: SKELETON_CELL },
      },
      {
        id: 'container_number',
        header: 'Container',
        cell: ({ row }) => textCell(row.original.container_number),
        size: 130,
      },
      {
        id: 'supplier_name',
        header: 'Supplier',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.supplier_name ?? undefined}>
            {textCell(row.original.supplier_name)}
          </span>
        ),
        size: 170,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => fmtInt(row.original.qty),
        footer: () => fmtInt(total),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'eta',
        header: 'ETA',
        cell: ({ row }) => fmtDate(row.original.eta),
        size: 100,
        meta: RIGHT,
      },
      {
        id: 'status',
        header: 'Status',
        cell: ({ row }) => textCell(row.original.status),
        size: 110,
      },
    ],
    [onOpenShipment, total],
  );

  return (
    <DrillTable
      columns={columns}
      rows={rows}
      getRowId={(r) => r.shipment_id}
      isLoading={drill.isLoading}
      emptyMessage="Nothing is on its way on a packing list for this product."
    />
  );
}

// ---------------------------------------------------------------------------
// PO - what is already ordered, and what was ordered before
// ---------------------------------------------------------------------------

/** Columns shared by the open and history tabs - only the footer total differs. */
function poColumns(totalStillToCome: number): ColumnDef<ContainerRequestDrillPoRow>[] {
  return [
    {
      id: 'po_number',
      header: 'PO',
      cell: ({ row }) => textCell(row.original.po_number),
      footer: () => <span className="text-muted-foreground">Total still to come</span>,
      size: 120,
      meta: { skeleton: SKELETON_CELL },
    },
    {
      id: 'supplier_name',
      header: 'Supplier',
      cell: ({ row }) => (
        <span className="block truncate" title={row.original.supplier_name ?? undefined}>
          {textCell(row.original.supplier_name)}
        </span>
      ),
      size: 170,
    },
    {
      id: 'qty_ordered',
      header: 'Qty',
      cell: ({ row }) => fmtInt(row.original.qty_ordered),
      size: 90,
      meta: RIGHT,
    },
    {
      id: 'still_to_come',
      header: 'Still to come',
      cell: ({ row }) => fmtInt(row.original.still_to_come),
      footer: () => fmtInt(totalStillToCome),
      size: 110,
      meta: RIGHT,
    },
    {
      id: 'unit_price',
      header: 'Unit price',
      cell: ({ row }) =>
        row.original.unit_price === null ? (
          <span className="text-muted-foreground">{EM_DASH}</span>
        ) : (
          fmtSupplierCost(row.original.unit_price, row.original.currency)
        ),
      size: 120,
      meta: RIGHT,
    },
    {
      id: 'issued',
      header: 'Issued',
      cell: ({ row }) => fmtDate(row.original.issued),
      size: 100,
      meta: RIGHT,
    },
    {
      id: 'eta',
      header: 'ETA',
      cell: ({ row }) => fmtDate(row.original.eta),
      size: 100,
      meta: RIGHT,
    },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) => textCell(row.original.status),
      size: 100,
    },
  ];
}

function poRowId(r: ContainerRequestDrillPoRow, i: number): string {
  return `${r.purchase_order_id}-${i}`;
}

/** The purchase-order lines behind the PO cell (AC-B4): open first, then the last 12 months. */
export function PoTabs({ supplierId, productId }: { supplierId: string; productId: string }) {
  const drill = useContainerRequestDrill(supplierId, productId, 'po');
  const open = (drill.data?.rows ?? []) as ContainerRequestDrillPoRow[];
  const history = (drill.data?.history ?? []) as ContainerRequestDrillPoRow[];

  const openStillToCome = drill.data?.total ?? open.reduce((s, r) => s + r.still_to_come, 0);
  const historyStillToCome = history.reduce((s, r) => s + r.still_to_come, 0);
  const openColumns = useMemo(() => poColumns(openStillToCome), [openStillToCome]);
  const historyColumns = useMemo(() => poColumns(historyStillToCome), [historyStillToCome]);

  return (
    <Tabs defaultValue="open">
      <TabsList variant="line">
        <TabsTrigger value="open">{`Open (${fmtInt(open.length)})`}</TabsTrigger>
        <TabsTrigger value="history">{`History (${fmtInt(history.length)})`}</TabsTrigger>
      </TabsList>
      <TabsContent value="open">
        <DrillTable
          columns={openColumns}
          rows={open}
          getRowId={poRowId}
          isLoading={drill.isLoading}
          emptyMessage="Nothing is on order for this product."
        />
      </TabsContent>
      <TabsContent value="history">
        <DrillTable
          columns={historyColumns}
          rows={history}
          getRowId={poRowId}
          isLoading={drill.isLoading}
          emptyMessage="No purchase order in the last twelve months names this product."
        />
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// SPO planner - the two pickers (R21, AC-G1/AC-G2)
// ---------------------------------------------------------------------------

/** One PO this SPO can draw from. Structurally the planner's own `SpoPoTake`. */
export interface PoTakeRow {
  po_line_id: string;
  po_number: string | null;
  supplier_name: string | null;
  /** The PO's own document date, distinct from `expected_date` (when the line is due). */
  po_date: string | null;
  expected_date: string | null;
  /** What the cascade took from this line. */
  qty: number;
  /** What the line has open, which is what it could give if a neighbour were unticked. */
  open_qty: number;
}

/**
 * Which POs this SPO draws from, oldest DOCUMENT first (Q8, AC-G1), each one tickable and
 * the suggested takes pre-ticked.
 *
 * Controlled and fetch-free on purpose: the SPO planner already holds `po_takes` in its
 * payload and owns the cascade that re-walks the takes when a tick changes. A picker that
 * fetched would be a second opinion about the same rows.
 */
export function PoTakesPicker({
  takes,
  tickedIds,
  onChange,
  coveredQty,
  packedQty,
}: {
  takes: PoTakeRow[];
  tickedIds: string[];
  onChange: (ids: string[]) => void;
  /** What the ticked takes cover, for the footer. */
  coveredQty: number;
  /** What the shipment line packs, for the footer. */
  packedQty: number;
}) {
  const toggle = (id: string, on: boolean) =>
    onChange(on ? [...tickedIds, id] : tickedIds.filter((x) => x !== id));

  const columns = useMemo<ColumnDef<PoTakeRow>[]>(
    () => [
      {
        id: 'select',
        header: '',
        cell: ({ row }) => {
          const t = row.original;
          return (
            <Checkbox
              checked={tickedIds.includes(t.po_line_id)}
              onCheckedChange={(checked) => toggle(t.po_line_id, !!checked)}
              aria-label={`Draw from ${t.po_number ?? t.po_line_id}`}
            />
          );
        },
        size: 40,
        enableResizing: false,
      },
      {
        id: 'po_number',
        header: 'PO',
        cell: ({ row }) => textCell(row.original.po_number),
        footer: () => TOTAL_LABEL,
        size: 130,
        meta: { skeleton: SKELETON_CELL },
      },
      {
        id: 'supplier_name',
        header: 'Supplier',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.supplier_name ?? undefined}>
            {textCell(row.original.supplier_name)}
          </span>
        ),
        size: 170,
      },
      {
        id: 'po_date',
        header: 'Doc date',
        cell: ({ row }) => fmtDate(row.original.po_date),
        size: 100,
        meta: RIGHT,
      },
      {
        id: 'expected_date',
        header: 'Due',
        cell: ({ row }) => fmtDate(row.original.expected_date),
        size: 100,
        meta: RIGHT,
      },
      {
        id: 'open_qty',
        header: 'Open',
        cell: ({ row }) => fmtInt(row.original.open_qty),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'qty',
        header: 'Taken',
        cell: ({ row }) => fmtInt(row.original.qty),
        footer: () => fmtInt(coveredQty),
        size: 90,
        meta: RIGHT,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tickedIds, coveredQty],
  );

  return (
    <div className="space-y-2">
      <DrillTable
        columns={columns}
        rows={takes}
        getRowId={(t) => t.po_line_id}
        emptyMessage="No open PO can back this line."
      />
      <p className="border-t pt-2 text-2xs text-muted-foreground">
        {`${fmtInt(tickedIds.length)} of ${fmtInt(takes.length)} POs · covers ${fmtInt(coveredQty)} of packed ${fmtInt(packedQty)}`}
      </p>
    </div>
  );
}

/** One piece of demand this SPO could cover. Structurally the planner's `SpoCoverageLine`. */
export interface SoCoverageRow {
  key: string;
  kind: 'project' | 'retail';
  document: string | null;
  customer_name: string | null;
  required_date: string | null;
  qty: number;
  warehouse_code: string | null;
}

/**
 * Which demand this SPO is pointed at (Q4, AC-G2): project rows first, then retail, in the
 * order the server walked them, pre-ticked to the packed quantity.
 *
 * What no tick claims is stated as Unassigned rather than quietly attached to the first order
 * in the list. Controlled and fetch-free for the same reason as `PoTakesPicker`.
 */
export function SoCoveragePicker({
  coverage,
  tickedKeys,
  onChange,
  unassigned,
  takes,
}: {
  coverage: SoCoverageRow[];
  tickedKeys: string[];
  onChange: (keys: string[]) => void;
  unassigned: number;
  /** What each ticked row actually GETS out of this SPO, by `key` (AC-G2's Take column).
   *  Omitted by a caller that holds no walk - the column then does not render at all,
   *  rather than reading 0 for every row and being mistaken for one. */
  takes?: Record<string, number>;
}) {
  const toggle = (key: string, on: boolean) =>
    onChange(on ? [...tickedKeys, key] : tickedKeys.filter((x) => x !== key));

  const totalQty = useMemo(() => coverage.reduce((s, c) => s + c.qty, 0), [coverage]);
  const totalTaken = useMemo(
    () => (takes ? coverage.reduce((s, c) => s + (takes[c.key] ?? 0), 0) : null),
    [coverage, takes],
  );

  const columns = useMemo<ColumnDef<SoCoverageRow>[]>(
    () => [
      {
        id: 'select',
        header: '',
        cell: ({ row }) => {
          const c = row.original;
          return (
            <Checkbox
              checked={tickedKeys.includes(c.key)}
              onCheckedChange={(checked) => toggle(c.key, !!checked)}
              aria-label={`Cover ${c.document ?? c.key}`}
            />
          );
        },
        size: 40,
        enableResizing: false,
      },
      {
        id: 'document',
        header: 'Sales order',
        cell: ({ row }) => textCell(row.original.document),
        footer: () => TOTAL_LABEL,
        size: 130,
        meta: { skeleton: SKELETON_CELL },
      },
      {
        id: 'customer_name',
        header: 'Customer',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.customer_name ?? undefined}>
            {textCell(row.original.customer_name)}
          </span>
        ),
        size: 170,
      },
      {
        id: 'kind',
        header: 'Class',
        cell: ({ row }) => (row.original.kind === 'project' ? 'Project' : 'Retail'),
        size: 90,
      },
      {
        id: 'required_date',
        header: 'Required',
        cell: ({ row }) => fmtDate(row.original.required_date),
        size: 100,
        meta: RIGHT,
      },
      {
        id: 'qty',
        header: 'Open',
        cell: ({ row }) => fmtInt(row.original.qty),
        footer: () => fmtInt(totalQty),
        size: 90,
        meta: RIGHT,
      },
      ...(takes
        ? [
            {
              id: 'take',
              header: 'Take',
              cell: ({ row }) => fmtInt(takes[row.original.key] ?? 0),
              footer: () => fmtInt(totalTaken ?? 0),
              size: 90,
              meta: RIGHT,
            } as ColumnDef<SoCoverageRow>,
          ]
        : []),
      {
        id: 'warehouse_code',
        header: 'Location',
        cell: ({ row }) => textCell(row.original.warehouse_code),
        size: 110,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tickedKeys, takes, totalQty, totalTaken],
  );

  return (
    <div className="space-y-2">
      <DrillTable
        columns={columns}
        rows={coverage}
        getRowId={(c) => c.key}
        emptyMessage="No open demand this SPO could cover."
      />
      <p className="border-t pt-2 text-2xs text-muted-foreground">
        {`Unassigned ${fmtInt(unassigned)}`}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The shell
// ---------------------------------------------------------------------------

/**
 * The one dialog a grid mounts, titled "<Kind> · <product code>" with the product name as its
 * description (Radix wants one, and a sentence explaining the dialog would be an on-screen
 * explanation, which the standards forbid).
 *
 * `context` is the figure and its qualifier - "2,876 before cut-off 30/09/2026", "117
 * arriving at site pools" - so the reader can see what the rows are supposed to add up to
 * without reading them.
 */
export function PlanRowDialog({
  kind,
  productCode,
  productName,
  context,
  open = true,
  onOpenChange,
  children,
}: {
  kind: PlanRowDialogKind;
  productCode: string;
  productName?: string | null;
  context?: string | null;
  open?: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-[95vw]">
        <DialogHeader className="shrink-0 space-y-1 border-b p-4 sm:p-6">
          <DialogTitle className="min-w-0 break-words">
            {`${PLAN_ROW_DIALOG_TITLES[kind]} · ${productCode}`}
            {context ? (
              <span className="ms-2 text-xs font-normal text-muted-foreground">{context}</span>
            ) : null}
          </DialogTitle>
          <DialogDescription className="truncate text-xs" title={productName ?? undefined}>
            {productName ?? productCode}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">{children}</DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default PlanRowDialog;
