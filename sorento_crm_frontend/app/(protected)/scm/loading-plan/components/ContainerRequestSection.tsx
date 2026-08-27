'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CellContext,
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  Check,
  Download,
  FileText,
  Info,
  LayoutGrid,
  Link2,
  LoaderCircle,
  PackageSearch,
  RefreshCw,
  Send,
  Table2,
  Upload,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import {
  useContainerRequestBuild,
  useContainerRequestHistory,
  useSendContainerRequest,
  useSupplierNotices,
  useUnfinishedStock,
} from '../../hooks/useFulfilment';
import {
  getNoticeDocumentUrl,
  type ContainerRequestHistoryProduct,
  type ContainerRequestRow,
  type ContainerRequestSoLine,
  type SupplierNotice,
} from '../../services/fulfilmentService';
import { ContainerRequestHistoryPeakCell } from './ContainerRequestHistory';
import { ContainerRequestRowDialog } from './ContainerRequestRowDialog';
import { ContainerRequestStatCards } from './ContainerRequestStatCards';
import { summariseContainerRequest } from './containerRequestSummary';
import { RankFactorsPopover } from './RankFactorsPopover';
import { SoLinesDrillPopover } from './SoLinesDrillPopover';
import { ContainerRequestScheduleMatrix } from './ContainerRequestScheduleMatrix';
import {
  buildContainerRequestMatrix,
  type ContainerRequestMatrixAxis,
  type ContainerRequestMatrixGranularity,
} from './containerRequestMatrix';

/**
 * Stage 1 of Ms Tee's journey (PLAN-scm-loading-plan-demand-first.md, amended section 4/6b -
 * 20 Aug afternoon): what to ask this supplier for, before any container is chosen. ONE
 * table over the whole stock list - a stock-list product with no open demand still gets a row
 * (`has_demand: false`, muted, unranked), so nothing the stock list holds vanishes into a
 * second table. The product set and the quantities are both derived - off the supplier's
 * stock list and the outstanding sales-order book - so the only three decisions left to her
 * are the supplier (picked above this section), any quantity she disagrees with, and Send.
 *
 * `planHorizonDate` ("Plan until", captain 20 Aug follow-up): an optional cutoff picked next
 * to the supplier, above this section. When set, every demand-derived figure the build
 * returns already excludes what is due after it (backend-side - `container_request_service`
 * mirrors the reorder run's own horizon rule exactly); this component only has to show what
 * was actually applied, which it reads off the build's own echo (`build.data.plan_horizon_date`)
 * rather than the prop, so a stale prop during a refetch can never disagree with the numbers
 * on screen.
 *
 * Also folds in "waiting on production" (captain follow-up, same day): that used to be a
 * second list below this table. A supplier-held unfinished quantity is already on every
 * matched row here as the "They hold" cell (sortable, see the `holding` column), so the
 * second list is gone. The one case that column cannot cover - a stock-list item code that
 * never matched a product at all - is called out in its own small block below the table
 * rather than silently dropped (see `unmatchedUnfinished`).
 */

const NOTICE_STATUS_LABEL: Record<SupplierNotice['status'], string> = {
  pending: 'Queued',
  sent: 'Sent',
  failed: 'Failed',
  skipped: 'Not sent',
};

const NOTICE_CHANNEL_LABEL: Record<SupplierNotice['channel'], string> = {
  email: 'Email',
  chat: 'Chat',
};

const MATRIX_AXIS_OPTIONS = [
  { value: 'product', label: 'Product' },
  { value: 'order', label: 'Order' },
];

const MATRIX_GRANULARITY_OPTIONS = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
];

/** A source older than this reads as "trust this less" rather than a hard error - the figures
 *  built off it are still real, just possibly overtaken by an upload nobody has run yet. */
const STALE_AFTER_DAYS = 7;

function isStaleSource(iso: string | null): boolean {
  if (!iso) return false;
  const ms = Date.now() - new Date(iso).getTime();
  return ms > STALE_AFTER_DAYS * 24 * 60 * 60 * 1000;
}

/** The stamp's own date, +time when the source ISO actually carries one - `stock_list_as_of`
 *  is a bare date (`supplier_inventory.as_of`), the other three are timestamps. Naive-UTC
 *  timestamps must go through `formatDateTimeInMalaysia` (parses as UTC, renders MYT) - a bare
 *  `new Date(iso)` reads the naive string as local time and lands 8h early. */
function formatSourceStamp(iso: string | null): string {
  if (!iso) return EM_DASH;
  return iso.includes('T') ? formatDateTimeInMalaysia(iso) : formatDateInMalaysia(iso);
}

function SourceStamp({ label, iso }: { label: string; iso: string | null }) {
  const stale = isStaleSource(iso);
  return (
    <span className={cn(stale && 'text-amber-600')} title={stale ? 'Consider re-uploading' : undefined}>
      {label} {formatSourceStamp(iso)}
    </span>
  );
}

/**
 * What "Packed" sorts by: the one quantity the column shows (captain, 27 Aug: the unfinished
 * half left the grid; it still reads in the row dialog and the unmatched-unfinished list).
 * A row neither document names sorts below every row that carries a figure, rather than
 * tying with a real zero.
 */
export function holdingSortValue(row: ContainerRequestRow): number {
  return row.holding_qty ?? -1;
}

/**
 * What the supplier says they hold, in the words of whichever document said it (F1).
 *
 * A stock list states two quantities and they are never summed - packed can go on a
 * container this week, unfinished is a request to their production line. A proforma states
 * one, for one container, and carries a badge saying so, because a promise for a container is
 * not the same fact as stock in their warehouse. Neither reads as a dash rather than a zero:
 * "they have told us nothing" and "they told us they have none" are different answers.
 */
function HoldingCell({ row }: { row: ContainerRequestRow }) {
  if (row.holding_source === 'proforma') {
    return (
      <div className="flex flex-col text-2xs">
        <span className="tabular-nums">{fmtInt(row.holding_qty ?? 0)}</span>
        <span className="text-muted-foreground">
          PI {row.holding_as_of ? formatDateInMalaysia(row.holding_as_of) : EM_DASH}
        </span>
      </div>
    );
  }
  if (row.holding_source === 'none') {
    return <span className="text-2xs text-muted-foreground">{EM_DASH}</span>;
  }
  return <span className="tabular-nums">{fmtInt(row.qty_packed)}</span>;
}

/**
 * A channel's open quantity with its SO lines one click away.
 *
 * The figure alone when there is nothing behind it (zero, or no lines loaded): an info icon
 * that opens an empty list teaches the eye to stop clicking.
 */
function ChannelQtyCell({
  row,
  qty,
  lines,
  channel,
}: {
  row: ContainerRequestRow;
  qty: number;
  lines: ContainerRequestSoLine[];
  channel: 'project' | 'retail';
}) {
  if (!qty || lines.length === 0) return <span className="tabular-nums">{fmtInt(qty)}</span>;
  return (
    <SoLinesDrillPopover
      title={`${row.item_code ?? row.product_name ?? 'This product'} - ${channel} SOs`}
      lines={lines}
      trigger={
        <button
          type="button"
          title={`View ${channel} SO lines`}
          className="inline-flex items-center gap-1 rounded-sm tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        >
          {fmtInt(qty)}
          <Info className="size-3.5 text-muted-foreground" aria-hidden />
        </button>
      }
    />
  );
}

export function ContainerRequestSection({
  supplierId,
  supplierName,
  planHorizonDate = null,
  onUploadStockList,
  onUploadProforma,
}: {
  supplierId: string;
  supplierName: string;
  /** "Plan until" (captain, 20 Aug) - picked next to the supplier, above this section. Null
   *  means no cutoff, today's behaviour. */
  planHorizonDate?: string | null;
  onUploadStockList: () => void;
  /** The other document that answers "what do they hold" (Q2). Optional so a caller with no
   *  proforma dialog behind it keeps the single CTA. */
  onUploadProforma?: () => void;
}) {
  const build = useContainerRequestBuild(supplierId, planHorizonDate);
  const send = useSendContainerRequest();
  const notices = useSupplierNotices(supplierId);
  // Same supplier-keyed query `useUnfinishedStock` already drives Stage 2's "Unfinished"
  // tile hint - react-query dedupes on the shared key, so this is not a second network call.
  const unfinished = useUnfinishedStock(supplierId);

  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [confirming, setConfirming] = useState(false);
  const [view, setView] = useState<'table' | 'schedule'>('table');
  const [matrixAxis, setMatrixAxis] = useState<ContainerRequestMatrixAxis>('product');
  const [matrixGranularity, setMatrixGranularity] =
    useState<ContainerRequestMatrixGranularity>('week');
  const [openingDocId, setOpeningDocId] = useState<string | null>(null);
  const [copiedNoticeId, setCopiedNoticeId] = useState<string | null>(null);
  // The product whose breakdown is open. Held as an id, not the row object, so a refresh
  // behind an open dialog shows the NEW numbers rather than the ones it opened on.
  const [openProductId, setOpenProductId] = useState<string | null>(null);

  const rows = useMemo(() => build.data?.rows ?? [], [build.data]);
  const soLines = useMemo(() => build.data?.lines ?? [], [build.data]);

  // What the table cannot show at all: a stock-list item code the supplier holds unfinished
  // that never matched a product (`container_request_service._stock_list` only carries
  // matched rows, `unfinished_at_supplier` does not filter on a match). Kept visible here
  // rather than dropped - see the module docstring.
  const unmatchedUnfinished = useMemo(() => {
    const matchedCodes = new Set(rows.map((r) => r.item_code).filter((c): c is string => !!c));
    return (unfinished.data ?? []).filter((r) => !matchedCodes.has(r.item_code));
  }, [unfinished.data, rows]);

  const linesByProduct = useMemo(() => {
    const map = new Map<string, ContainerRequestSoLine[]>();
    for (const l of soLines) {
      const arr = map.get(l.product_id);
      if (arr) arr.push(l);
      else map.set(l.product_id, [l]);
    }
    return map;
  }, [soLines]);

  // The schedule matrix's product-axis rows follow the SAME rank the ranked demand table
  // already shows - the two are two views of one order, not two independent sorts. Rows come
  // back from the build already sorted by rank; this just carries that rank along by product_id
  // for the matrix builder to key off.
  const rankByProductId = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of rows) {
      if (r.rank !== null) map.set(r.product_id, r.rank);
    }
    return map;
  }, [rows]);

  const matrix = useMemo(
    () => buildContainerRequestMatrix(soLines, matrixAxis, matrixGranularity, rankByProductId),
    [soLines, matrixAxis, matrixGranularity, rankByProductId],
  );

  // A fresh suggestion replaces whatever she had edited into the previous one - "refresh" is
  // asking the system to look again, not "keep my edits and re-rank around them".
  useEffect(() => {
    const seed: Record<string, number> = {};
    for (const r of rows) seed[r.product_id] = r.suggested_qty;
    setOverrides(seed);
  }, [rows]);

  const overridesRef = useRef(overrides);
  overridesRef.current = overrides;

  const historyRef = useRef(new Map<string, ContainerRequestHistoryProduct>());
  const historyLoadingRef = useRef(false);

  const qtyFor = (row: ContainerRequestRow) => overrides[row.product_id] ?? row.suggested_qty;

  const lines = useMemo(
    () =>
      rows.map((r) => ({ product_id: r.product_id, qty: qtyFor(r) })).filter((l) => l.qty > 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, overrides],
  );
  const totalQty = lines.reduce((sum, l) => sum + l.qty, 0);

  // A row edited to 0 leaves the request without being deleted from the grid - she can still
  // see and change her mind about it, it just does not go on the document.
  const renderQtyCell = useCallback((ctx: CellContext<ContainerRequestRow, unknown>) => {
    const original = ctx.row.original;
    const qty = overridesRef.current[original.product_id] ?? original.suggested_qty;
    return (
      <Input
        type="number"
        min={0}
        className="h-8 w-24 tabular-nums"
        value={qty}
        // The netting rule with this row's own numbers in it (F2): what the figure IS, on
        // the figure, so nobody has to remember whether the packing list was subtracted.
        title={`${fmtInt(original.open_so_need)} need - ${fmtInt(original.on_hand)} on hand - ${fmtInt(original.incoming_spo)} incoming SPO = ${fmtInt(original.suggested_qty)}`}
        onChange={(e) => {
          const next = Math.max(0, Number(e.target.value) || 0);
          setOverrides((prev) => ({ ...prev, [original.product_id]: next }));
        }}
      />
    );
  }, []);

  const columns = useMemo<ColumnDef<ContainerRequestRow>[]>(
    () => [
      {
        id: 'rank',
        header: ({ column }) => <DataGridColumnHeader title="Rank" column={column} />,
        cell: ({ row }) => {
          const original = row.original;
          const muted = original.has_demand === false;
          return (
            <div className="flex items-center gap-1">
              <span
                className={cn('tabular-nums', muted ? 'text-muted-foreground/60' : 'text-muted-foreground')}
              >
                {original.rank ?? EM_DASH}
              </span>
              {!muted ? (
                <RankFactorsPopover
                  line={{ rank_score: original.rank_score, factors: original.rank_factors }}
                />
              ) : null}
            </div>
          );
        },
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Rank' },
      },
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const original = row.original;
          const muted = original.has_demand === false;
          return (
            <button
              type="button"
              // The grid is the scan surface; the breakdown behind it is one click away, the
              // same move the fulfilment board's cell makes.
              onClick={() => setOpenProductId(original.product_id)}
              title="What this row is made of"
              className={cn(
                'flex min-w-0 flex-col text-start underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40',
                muted && 'opacity-70',
              )}
            >
              <span className="truncate font-medium" title={original.item_code ?? ''}>
                {original.item_code ?? EM_DASH}
              </span>
              <span
                className="truncate text-2xs text-muted-foreground"
                title={original.product_name ?? ''}
              >
                {original.product_name ?? EM_DASH}
              </span>
            </button>
          );
        },
        size: 210,
        enableSorting: false,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'suggested_qty',
        header: ({ column }) => (
          <span className="flex items-center gap-1">
            <DataGridColumnHeader title="Suggested qty" column={column} />
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  tabIndex={0}
                  aria-label="How the suggested quantity is worked out"
                  className="inline-flex cursor-help items-center text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Info className="size-3.5" aria-hidden />
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                Need - on hand at site pools - incoming SPO at site pools, never below 0.
                Incoming packing lists and open POs are not subtracted.
              </TooltipContent>
            </Tooltip>
          </span>
        ),
        cell: renderQtyCell,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Suggested qty' },
      },
      {
        id: 'open_so_need',
        header: ({ column }) => <DataGridColumnHeader title="Need" column={column} />,
        cell: ({ row }) => {
          const original = row.original;
          if (original.has_demand === false) {
            return (
              <span className="text-2xs text-muted-foreground" title="Need">
                No open demand
              </span>
            );
          }
          return (
            <span className="tabular-nums" title="Need">
              {fmtInt(original.open_so_need)}
            </span>
          );
        },
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Need' },
      },
      {
        accessorKey: 'project_qty',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        // The SO drill sits on the channel figure it explains (captain, 27 Aug): the "Open
        // SOs" count column is gone, and each channel opens its own lines.
        cell: ({ row }) => (
          <ChannelQtyCell
            row={row.original}
            qty={row.original.project_qty}
            lines={(linesByProduct.get(row.original.product_id) ?? []).filter(
              (l) => l.demand_class === 'project',
            )}
            channel="project"
          />
        ),
        size: 125,
        enableSorting: false,
        meta: { headerTitle: 'Project' },
      },
      {
        accessorKey: 'retail_qty',
        header: ({ column }) => <DataGridColumnHeader title="Retail" column={column} />,
        // Retail carries the unclassified lines too: the column already counts them (no
        // Unclassified column, AC-A2.2), so the drill lists what the figure counts.
        cell: ({ row }) => (
          <ChannelQtyCell
            row={row.original}
            qty={row.original.retail_qty}
            lines={(linesByProduct.get(row.original.product_id) ?? []).filter(
              (l) => l.demand_class !== 'project',
            )}
            channel="retail"
          />
        ),
        size: 125,
        enableSorting: false,
        meta: { headerTitle: 'Retail' },
      },
      {
        accessorKey: 'on_hand',
        header: ({ column }) => <DataGridColumnHeader title="On hand" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums" title="On hand">
            {fmtInt(row.original.on_hand)}
          </span>
        ),
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'On hand' },
      },
      {
        accessorKey: 'incoming_spo',
        header: ({ column }) => <DataGridColumnHeader title="SPO" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums" title="SPO">
            {fmtInt(row.original.incoming_spo)}
          </span>
        ),
        size: 80,
        enableSorting: false,
        meta: { headerTitle: 'SPO' },
      },
      {
        accessorKey: 'incoming_pl',
        header: ({ column }) => <DataGridColumnHeader title="Incoming PL" column={column} />,
        // Muted because it is a reference: a packing list names no destination, so it can be
        // read beside the ask but never subtracted from it (Q1).
        cell: ({ row }) => (
          <span className="tabular-nums text-muted-foreground" title="Incoming PL - reference only">
            {fmtInt(row.original.incoming_pl)}
          </span>
        ),
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Incoming PL' },
      },
      {
        accessorKey: 'outstanding_po',
        header: ({ column }) => <DataGridColumnHeader title="PO" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums" title="Outstanding PO - reference only">
            {fmtInt(row.original.outstanding_po)}
          </span>
        ),
        size: 80,
        enableSorting: false,
        meta: { headerTitle: 'PO' },
      },
      {
        accessorKey: 'earliest_required_date',
        header: ({ column }) => <DataGridColumnHeader title="Earliest need-by" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.earliest_required_date
              ? formatDateInMalaysia(row.original.earliest_required_date)
              : EM_DASH}
          </span>
        ),
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Earliest need-by' },
      },
      {
        id: 'holding',
        // Sortable: `accessorFn` gives the sort its number; the cell shows the figure.
        accessorFn: holdingSortValue,
        header: ({ column }) => <DataGridColumnHeader title="Packed" column={column} />,
        cell: ({ row }) => <HoldingCell row={row.original} />,
        size: 100,
        enableSorting: true,
        sortDescFirst: true,
        meta: { headerTitle: 'Packed' },
      },
      // Read through a ref for the same reason the editable qty cell does: the sidecar is
      // fetched for the page THIS table decides, which is not known until the table exists,
      // so the column cannot depend on it without a cycle. Cell functions run on every
      // render, so an arriving sidecar still paints. One column per series (captain, 27 Aug).
      {
        id: 'project_peak',
        header: ({ column }) => <DataGridColumnHeader title="Project peak" column={column} />,
        cell: ({ row }) => (
          <ContainerRequestHistoryPeakCell
            history={historyRef.current.get(row.original.product_id)}
            loading={historyLoadingRef.current}
            kind="project"
          />
        ),
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Project peak' },
      },
      {
        id: 'retail_peak',
        header: ({ column }) => <DataGridColumnHeader title="Retail peak" column={column} />,
        cell: ({ row }) => (
          <ContainerRequestHistoryPeakCell
            history={historyRef.current.get(row.original.product_id)}
            loading={historyLoadingRef.current}
            kind="retail"
          />
        ),
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Retail peak' },
      },
    ],
    [renderQtyCell, linesByProduct],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.product_id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // AC-B8: the sidecar is asked for the products ON SCREEN, never the whole supplier. A
  // 120-product stock list would otherwise pay for 240 monthly series to read 25 rows.
  const pageProductIds = useMemo(
    () => table.getRowModel().rows.map((r) => r.original.product_id),
    // The row model is rebuilt when any of these move; `table` itself is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [table, rows, pagination, sorting],
  );
  const history = useContainerRequestHistory(supplierId, pageProductIds);
  historyRef.current = useMemo(() => {
    const map = new Map<string, ContainerRequestHistoryProduct>();
    for (const p of history.data?.products ?? []) map.set(p.product_id, p);
    return map;
  }, [history.data]);
  historyLoadingRef.current = history.isFetching;

  const summary = useMemo(
    () => summariseContainerRequest(rows, qtyFor),
    // `qtyFor` reads `overrides`, so the cards follow her edits - which is the whole point of
    // putting them above the grid.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, overrides],
  );

  const openRow = openProductId
    ? (rows.find((r) => r.product_id === openProductId) ?? null)
    : null;

  const requestNotices = (notices.data ?? []).filter(
    (n) => n.notice_type === 'container_request',
  );

  const canSend = lines.length > 0 && totalQty > 0 && !send.isPending;

  function confirmSend() {
    send.mutate(
      { supplierId, supplierName, lines },
      { onSuccess: () => setConfirming(false) },
    );
  }

  // Duplicated from `SupplierNoticePanel.openDocument` rather than generalizing that panel to
  // take an arbitrary notices list: its header couples the document list to ONE action
  // (`useApproveLoadingPlan`, keyed on a `planId` this stage does not have) - reshaping it to
  // also drive `useSendContainerRequest` risked the panel's own, already-covered tests for a
  // few lines of overlap. Noted per the CLAUDE.md lesson on not silently duplicating shared
  // list/detail rendering: this IS a duplication, made deliberately and in the open.
  async function openDocument(notice: SupplierNotice, kind: 'pdf' | 'xlsx') {
    setOpeningDocId(`${notice.id}:${kind}`);
    try {
      const { url } = await getNoticeDocumentUrl(notice.id, kind);
      window.open(url, '_blank', 'noopener');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setOpeningDocId(null);
    }
  }

  // The link the supplier already has in their inbox, copied so Ms Tee can paste it into
  // WeChat herself - which is how she reaches the factories that never open email.
  async function copyLink(notice: SupplierNotice) {
    if (!notice.public_url) return;
    try {
      await navigator.clipboard.writeText(notice.public_url);
      setCopiedNoticeId(notice.id);
      toast.success('Link copied');
      window.setTimeout(() => setCopiedNoticeId(null), 2000);
    } catch {
      toast.error('Could not copy the link. Copy it from the address bar instead.');
    }
  }

  // SF-4 (reviewer): what has already been sent to this supplier does not disappear just
  // because the build is loading, errored, or has nothing to suggest right now - it is its own
  // fact, independent of the current suggestion. Rendered on every branch below.
  const noticesCard = (
    <Card className="p-4">
      <h3 className="text-sm font-semibold">Requests sent to {supplierName}</h3>
      {requestNotices.length === 0 ? (
        <p className="mt-2 rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
          Nothing sent to this supplier yet.
        </p>
      ) : (
        <div className="mt-2 divide-y divide-border rounded-lg border">
          {requestNotices.map((n) => (
            <div
              key={n.id}
              className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium">{NOTICE_CHANNEL_LABEL[n.channel]}</span>
                  <span className={cn(STATUS_PILL_BASE, statusPillClass(n.status))}>
                    {NOTICE_STATUS_LABEL[n.status]}
                  </span>
                  {n.recipient ? (
                    <span
                      className="truncate text-2xs text-muted-foreground"
                      title={n.recipient}
                    >
                      {n.recipient}
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-2xs text-muted-foreground">
                  {n.last_error ||
                    n.status_reason ||
                    (n.sent_at ? `Sent ${formatDateInMalaysia(n.sent_at)}` : EM_DASH)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-2xs text-muted-foreground">{n.line_count} products</span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!n.has_document || openingDocId === `${n.id}:pdf`}
                  onClick={() => openDocument(n, 'pdf')}
                >
                  {openingDocId === `${n.id}:pdf` ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <Download className="size-4" />
                  )}
                  PDF
                </Button>
                {/* Their own stock list with the quantity to load filled in (AC-C4). Absent
                    on notices sent before F4, which is why the button is conditional rather
                    than merely disabled. */}
                {n.has_xlsx ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={openingDocId === `${n.id}:xlsx`}
                    onClick={() => openDocument(n, 'xlsx')}
                  >
                    {openingDocId === `${n.id}:xlsx` ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <Download className="size-4" />
                    )}
                    XLSX
                  </Button>
                ) : null}
                {n.public_url ? (
                  <Button size="sm" variant="outline" onClick={() => copyLink(n)}>
                    {copiedNoticeId === n.id ? (
                      <Check className="size-4" />
                    ) : (
                      <Link2 className="size-4" />
                    )}
                    Copy link
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );

  // What the ranked table structurally cannot show: a stock-list item code held unfinished
  // that never matched a product, so it has no `product_id` to be a row (see the module
  // docstring). Rendered whenever there is at least one, on both branches that reach past the
  // build (a supplier can have zero open demand and still hold unmatched unfinished stock).
  const unmatchedCard =
    unmatchedUnfinished.length > 0 ? (
      <Card className="p-4">
        <h3 className="text-sm font-semibold">Unfinished stock without a product match</h3>
        <p className="text-2xs text-muted-foreground">
          {supplierName}&apos;s stock list names these item codes as unfinished, but none
          matches a product yet, so they cannot appear as a row above.
        </p>
        <ul className="mt-2 divide-y divide-border">
          {unmatchedUnfinished.map((r) => (
            <li key={r.item_code} className="flex items-center justify-between py-1.5">
              <span className="truncate text-xs" title={r.item_code}>
                {r.item_code}
                {r.product_name ? (
                  <span className="ms-2 text-muted-foreground">{r.product_name}</span>
                ) : null}
              </span>
              <span className="tabular-nums text-xs">{fmtInt(r.qty_unfinished)} unfinished</span>
            </li>
          ))}
        </ul>
      </Card>
    ) : null;

  if (build.isLoading) {
    return (
      <div className="space-y-4">
        <Card className="p-4">
          <Skeleton className="h-6 w-64" />
          <Skeleton className="mt-3 h-24 w-full rounded-lg" />
        </Card>
        {noticesCard}
      </div>
    );
  }

  if (build.isError) {
    return (
      <div className="space-y-4">
        <Card className="flex flex-col items-center gap-3 p-8 text-center">
          <p className="text-sm font-medium text-destructive">{build.error.message}</p>
          <Button variant="outline" size="sm" onClick={() => build.refetch()}>
            <RefreshCw className="size-4" />
            Try again
          </Button>
        </Card>
        {noticesCard}
      </div>
    );
  }

  // AC-A1: the "no stock list yet" card is GONE. The plan is built from what we buy from
  // this supplier crossed with what customers are owed, so a supplier who has never sent a
  // stock list still gets a table; "They hold" reads their newest proforma, or a dash.
  if (!build.data || rows.length === 0) {
    return (
      <div className="space-y-4">
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <PackageSearch className="size-5" />
          </span>
          <p className="text-sm font-medium">
            Nothing to ask {supplierName} for right now.
          </p>
          <p className="text-2xs text-muted-foreground">
            No open customer demand on what they supply, and nothing of theirs on file.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button size="sm" variant="outline" onClick={onUploadStockList}>
              <Upload className="size-4" />
              Upload stock list
            </Button>
            {onUploadProforma ? (
              <Button size="sm" variant="outline" onClick={onUploadProforma}>
                <FileText className="size-4" />
                Upload proforma invoice
              </Button>
            ) : null}
          </div>
        </Card>
        {unmatchedCard}
        {noticesCard}
      </div>
    );
  }

  const sources = build.data.sources;

  return (
    <div className="space-y-4">
      {/* The cards carry the swatches, which is why there is no legend row under them (r4). */}
      <ContainerRequestStatCards
        summary={summary}
        horizonDate={
          build.data.plan_horizon_date
            ? formatDateInMalaysia(build.data.plan_horizon_date)
            : null
        }
      />

      <DataGrid
        table={table}
        recordCount={rows.length}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No open customer demand for what this supplier supplies."
      >
        <Card>
          <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold">What to ask {supplierName} for</h3>
              {/* The freshness strip (captain, "plan with trusted data"): a source older than
                  a week reads in a warning tone rather than a hard block - the figures are
                  still real, just possibly stale. */}
              <p className="text-2xs text-muted-foreground">
                <SourceStamp label="SO book" iso={sources.so_book_as_of} /> -{' '}
                <SourceStamp label="PO book" iso={sources.po_book_as_of} /> -{' '}
                <SourceStamp label="SPO" iso={sources.spo_as_of} /> -{' '}
                {/* Whichever document the holdings actually came from - never both, because
                    the proforma is not consulted while a stock list exists (AC-A2/A3). */}
                {sources.stock_list_as_of || !sources.proforma_as_of ? (
                  <SourceStamp label="Stock list" iso={sources.stock_list_as_of} />
                ) : (
                  <SourceStamp label="PI" iso={sources.proforma_as_of} />
                )}
              </p>
              {/* What was actually applied, read off the build's own echo rather than the
                  prop - never lets the numbers on screen disagree with what this line says
                  they mean. */}
              {build.data.plan_horizon_date ? (
                <p className="text-2xs text-muted-foreground">
                  Counting SO need due on or before{' '}
                  {formatDateInMalaysia(build.data.plan_horizon_date)}.
                </p>
              ) : null}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => build.refetch()}
                disabled={build.isFetching}
              >
                {build.isFetching ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <RefreshCw className="size-4" />
                )}
                Refresh suggestion
              </Button>
              <Button size="sm" onClick={() => setConfirming(true)} disabled={!canSend}>
                {send.isPending ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <Send className="size-4" />
                )}
                Send to supplier
              </Button>
            </div>
          </CardHeader>

          <div className="flex flex-col gap-3 border-t border-border px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between">
            <div
              className="inline-flex rounded-md border border-input"
              role="group"
              aria-label="Request view"
            >
              <Button
                type="button"
                size="sm"
                variant={view === 'table' ? 'primary' : 'ghost'}
                className="rounded-e-none"
                aria-pressed={view === 'table'}
                onClick={() => setView('table')}
              >
                <Table2 className="size-4" aria-hidden />
                Table
              </Button>
              <Button
                type="button"
                size="sm"
                variant={view === 'schedule' ? 'primary' : 'ghost'}
                className="rounded-s-none border-s border-input"
                aria-pressed={view === 'schedule'}
                onClick={() => setView('schedule')}
              >
                <LayoutGrid className="size-4" aria-hidden />
                Schedule
              </Button>
            </div>

            {view === 'schedule' ? (
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <Label htmlFor="request-matrix-rows" className="text-xs text-muted-foreground">
                    Rows
                  </Label>
                  <div className="w-32">
                    <SearchableSelect
                      id="request-matrix-rows"
                      value={matrixAxis}
                      onChange={(v) => setMatrixAxis(v as ContainerRequestMatrixAxis)}
                      options={MATRIX_AXIS_OPTIONS}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Label htmlFor="request-matrix-by" className="text-xs text-muted-foreground">
                    By
                  </Label>
                  <div className="w-32">
                    <SearchableSelect
                      id="request-matrix-by"
                      value={matrixGranularity}
                      onChange={(v) => setMatrixGranularity(v as ContainerRequestMatrixGranularity)}
                      options={MATRIX_GRANULARITY_OPTIONS}
                    />
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          {view === 'table' ? (
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
          ) : matrix.rows.length === 0 ? (
            <div className="p-6 text-center">
              <p className="text-sm font-medium">No open sales-order lines behind this request.</p>
              <p className="mt-1 text-2xs text-muted-foreground">
                The schedule reads the same open SO lines the Table view totals - nothing to
                bucket by date yet.
              </p>
            </div>
          ) : (
            <div className="p-4">
              <ContainerRequestScheduleMatrix
                buckets={matrix.buckets}
                rows={matrix.rows}
                rowHeader={matrixAxis === 'order' ? 'Order' : 'Product'}
                cells={matrix.cells}
              />
            </div>
          )}
        </Card>
      </DataGrid>

      {unmatchedCard}

      {/* SF-4 (reviewer): always rendered, with an explicit empty state - "nothing sent yet" is
          a state she needs to see, not infer from an absent section. Shared with the early
          returns above so every branch of this component shows the same fact. */}
      {noticesCard}

      {openRow ? (
        <ContainerRequestRowDialog
          row={openRow}
          askQty={qtyFor(openRow)}
          soLines={linesByProduct.get(openRow.product_id) ?? []}
          history={historyRef.current.get(openRow.product_id)}
          historyLoading={history.isFetching}
          onClose={() => setOpenProductId(null)}
        />
      ) : null}

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Send this request to {supplierName}?</AlertDialogTitle>
            <AlertDialogDescription>
              {lines.length} product{lines.length === 1 ? '' : 's'}, {fmtInt(totalQty)} units in
              total. The supplier receives the request document by email when an address is on
              file; the document is available either way.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {send.isError ? (
            <p className="text-xs text-destructive">{send.error.message}</p>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                // Radix closes an Action on click by default; the send is async and can fail,
                // so closing is deferred to the mutation's own onSuccess instead - a failure
                // then leaves the dialog open with the error on it, per the CRUD standard.
                e.preventDefault();
                confirmSend();
              }}
              disabled={send.isPending}
            >
              Send
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default ContainerRequestSection;
