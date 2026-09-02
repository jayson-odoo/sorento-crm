'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
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
import { useRouter } from 'next/navigation';
import { ChevronDown, LayoutGrid, PackageSearch, RefreshCw, Table2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { COARSE_HIT_TARGET_CLASS, PRESSED_CLASS } from '@/components/ui/primitive-classes';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import { useContainerRequestBuild, useContainerRequestHistory } from '../../hooks/useFulfilment';
import type {
  ContainerRequestHistoryProduct,
  ContainerRequestRow,
  ContainerRequestSoLine,
} from '../../services/fulfilmentService';
import {
  DocTable,
  EmptyRow,
  IncomingPlTable,
  OnHandTable,
  PlanRowDialog,
  PoTabs,
  ProjectRetailTabs,
  SpoTabs,
  Td,
  Th,
  monthLabel,
  type PlanDemandLineRow,
  type PlanHistoryPoint,
  type PlanRowDialogKind,
} from '../../components/PlanRowDialog';
import { PlanNumberButton } from '../../components/PlanNumberButton';
import { FormulaTip } from './FormulaTip';
import { ContainerRequestRowDialog } from './ContainerRequestRowDialog';
import { ContainerRequestStatCards } from './ContainerRequestStatCards';
import { summariseContainerRequest } from './containerRequestSummary';
import { RankFactorsPopover } from './RankFactorsPopover';
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
 * second list is gone. The stock-list item codes that matched no product at all had a small
 * block of their own here until 27 Aug (R23); it went, because the unmatched-code queue above
 * this section now lists exactly those codes and lets somebody answer them, and two lists of
 * one thing is one list nobody works down.
 *
 * The header's occasional actions sit behind a gear (R23), for the reason the toolbar's own
 * gear exists: Send is the errand, and a row of equally-weighted outline buttons made the
 * rare things look as important as the routine one.
 *
 * S2 (2 Sep): this renders on the record's Lines tab only. The "Requests sent to X" card
 * that used to sit under this grid as an inline `noticesCard` left for its own Sent tab
 * (`SentRequestsPanel.tsx`); `LoadingPlanView` owns the tab strip and both panels.
 *
 * S5 (2 Sep, section 3.5): a `has_demand: false` row no longer sits muted inside the ranked
 * table - it leaves the grid's data entirely and sits under a collapsed line below it, "N
 * products held with no open demand", expandable into a second grid with the SAME column
 * definitions and the same (default, pathname-derived) listing key, so the two share one
 * column-preference store. Collapsed on every load; no shared fold component is built, this
 * is its only consumer.
 */

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

/**
 * What "Packed" sorts by: the one quantity the column shows (captain, 27 Aug: the unfinished
 * half left the grid; it still reads in the row dialog). A row neither document names sorts
 * below every row that carries a figure, rather than tying with a real zero.
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
/** "PI 31/07/2026 · 5 blocks" - which statement the figure came off, and out of how many
 *  invoices it was added up (S6, AC-F4). The block count is only said when there is more
 *  than one, because "1 block" is what an invoice is. */
function proformaHoldingNote(row: ContainerRequestRow): string {
  const when = row.holding_as_of ? formatDateInMalaysia(row.holding_as_of) : EM_DASH;
  const blocks = row.holding_blocks ?? 0;
  return blocks > 1 ? `PI ${when} · ${fmtInt(blocks)} blocks` : `PI ${when}`;
}

function HoldingCell({
  row,
  onOpenBlocks,
}: {
  row: ContainerRequestRow;
  onOpenBlocks: () => void;
}) {
  if (row.holding_source === 'proforma') {
    const split = row.blocks ?? [];
    return (
      <div className="flex flex-col text-2xs">
        {/* The sum opens its own parts: five blocks added together is a figure nobody can
            check against the supplier's paper unless the split is one click away. */}
        <PlanNumberButton
          value={fmtInt(row.holding_qty ?? 0)}
          label="Invoice blocks behind this figure"
          onClick={onOpenBlocks}
          disabled={split.length === 0}
        />
        <span className="text-muted-foreground">{proformaHoldingNote(row)}</span>
      </div>
    );
  }
  if (row.holding_source === 'none') {
    return <span className="text-2xs text-muted-foreground">{EM_DASH}</span>;
  }
  return <span className="tabular-nums">{fmtInt(row.qty_packed)}</span>;
}

/** The per-block split behind one proforma row's figure (AC-F4). */
function BlocksTable({ row }: { row: ContainerRequestRow }) {
  const blocks = row.blocks ?? [];
  return (
    <DocTable>
      <thead>
        <tr className="border-b">
          <Th>Block</Th>
          <Th>Invoice</Th>
          <Th right>Packed</Th>
        </tr>
      </thead>
      <tbody>
        {blocks.length === 0 ? (
          <EmptyRow colSpan={3}>No invoice on this plan names this product.</EmptyRow>
        ) : (
          blocks.map((b) => (
            <tr key={`${b.pi_number}-${b.block_index ?? 0}`} className="border-b last:border-0">
              <Td>{b.block_index ?? EM_DASH}</Td>
              <Td title={b.pi_number}>
                <span className="block max-w-56 truncate">{b.pi_number}</span>
              </Td>
              <Td right>{fmtInt(b.qty)}</Td>
            </tr>
          ))
        )}
      </tbody>
    </DocTable>
  );
}

/** What the grid holds while a lightbox is open: which figure was clicked, and on which row. */
interface OpenPlanRowDialog {
  kind: PlanRowDialogKind;
  row: ContainerRequestRow;
  /** Set by the two peak cells, which open the channel dialog on its 12-month tab (AC-B6). */
  onHistory?: boolean;
}

/**
 * A channel's biggest month in the last twelve, and a click into that series (AC-B6).
 *
 * Peak, not total, because the question the column answers is "how big does this product get
 * in a month". The dialog it opens is the channel's OWN - the same one the Project / Retail
 * figure opens - landed on its history tab, so the twelve months and the open orders behind
 * them are never two different lightboxes.
 */
function PeakCell({
  history,
  loading,
  kind,
  onOpen,
}: {
  history: ContainerRequestHistoryProduct | undefined;
  loading: boolean;
  kind: 'project' | 'retail';
  onOpen: () => void;
}) {
  if (loading && !history) {
    return <span className="text-2xs text-muted-foreground">Loading</span>;
  }
  const series = history?.[kind];
  if (!series || series.total === 0 || !series.peak_month) {
    return <span className="text-2xs text-muted-foreground">{EM_DASH}</span>;
  }
  return (
    <PlanNumberButton
      value={`${fmtInt(series.peak_qty)} ${monthLabel(series.peak_month)}`}
      label={`${kind === 'project' ? 'Project' : 'Retail'} ordered, last 12 months`}
      onClick={onOpen}
    />
  );
}

/** The build's SO lines in the shape the shared lightbox lists them (AC-B2). */
function toDemandLines(lines: ContainerRequestSoLine[]): PlanDemandLineRow[] {
  return lines.map((l) => ({
    so_number: l.so_number,
    customer: l.customer_label,
    project: l.project_title,
    agent: l.agent_label,
    price: l.unit_price,
    qty: l.qty,
    required_date: l.required_date,
  }));
}

/**
 * The figure the rows are supposed to add up to, said beside the title - so the reader can
 * see the total they came to check without adding the table up themselves.
 */
function dialogContext(dialog: OpenPlanRowDialog, horizon: string | null): string {
  const { kind, row } = dialog;
  if (kind === 'project' || kind === 'retail') {
    const qty = kind === 'project' ? row.project_qty : row.retail_qty;
    const cutoff = horizon ? ` before cut-off ${formatDateInMalaysia(horizon)}` : '';
    return `${fmtInt(qty)} open${cutoff}`;
  }
  if (kind === 'on_hand') return `${fmtInt(row.on_hand)} at site pools`;
  if (kind === 'spo') return `${fmtInt(row.incoming_spo)} arriving at site pools`;
  if (kind === 'incoming_pl') return `${fmtInt(row.incoming_pl)} on packing lists`;
  if (kind === 'blocks') {
    // The blocks that named THIS product, not the statement's own count: the cell beside it
    // already says how many blocks the file is, and a title claiming five while the table
    // lists two would read as a missing row.
    const named = row.blocks?.length ?? 0;
    // Short on purpose: the shell prints this beside the title, and at 375px a longer
    // qualifier wraps under the close button.
    return `${fmtInt(row.holding_qty ?? 0)} over ${fmtInt(named)} ${
      named === 1 ? 'block' : 'blocks'
    }`;
  }
  return `${fmtInt(row.outstanding_po)} still to come`;
}

/**
 * The two 12-month series, zipped per month - the dialog reads one row per month with both
 * channels on it, the sidecar answers one series per channel.
 *
 * Keyed off the project series' buckets because both are zero-filled over the SAME twelve
 * months by `_series`, so there is no month on one and not the other.
 */
function toHistoryPoints(history: ContainerRequestHistoryProduct | undefined): PlanHistoryPoint[] {
  if (!history) return [];
  const retail = new Map(history.retail.months.map((m) => [m.month, m.qty]));
  return history.project.months.map((m) => ({
    month: m.month,
    project_qty: m.qty,
    retail_qty: retail.get(m.month) ?? 0,
  }));
}

export function ContainerRequestSection({
  planId,
  supplierId,
  supplierName,
  qtyFor,
  onQtyChange,
  readOnly = false,
}: {
  /** The plan this section belongs to (R2). Supplier and cut-off are the plan row's, so the
   *  build is asked for by plan id and nothing on this screen can disagree with it. */
  planId: string;
  supplierId: string;
  supplierName: string;
  /** The quantity to show and send for a row: the record page owns the typed edits, because
   *  Save and Send live on ITS toolbar (R5) and both have to act on what the grid shows. */
  qtyFor: (row: ContainerRequestRow) => number;
  onQtyChange: (rowKey: string, qty: number) => void;
  /** A cancelled plan is a record of what was asked, not a form (AC-A8). */
  readOnly?: boolean;
}) {
  const router = useRouter();
  const build = useContainerRequestBuild(planId);

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  // The fold (S5): collapsed on every load, state in component memory only - never persisted,
  // never read from a prop.
  const [foldOpen, setFoldOpen] = useState(false);
  const [foldPagination, setFoldPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [foldSorting, setFoldSorting] = useState<SortingState>([]);
  const [view, setView] = useState<'table' | 'schedule'>('table');
  const [matrixAxis, setMatrixAxis] = useState<ContainerRequestMatrixAxis>('product');
  const [matrixGranularity, setMatrixGranularity] =
    useState<ContainerRequestMatrixGranularity>('week');
  // The row whose breakdown is open. Held as its KEY, not the row object, so a refresh
  // behind an open dialog shows the NEW numbers rather than the ones it opened on.
  const [openRowKey, setOpenRowKey] = useState<string | null>(null);
  // The figure whose documents are open (R7). ONE state for all eight columns: two of them
  // could never be open at once, and a state per column is eight ways to leave one behind.
  const [dialog, setDialog] = useState<OpenPlanRowDialog | null>(null);

  const rows = useMemo(() => build.data?.rows ?? [], [build.data]);
  const soLines = useMemo(() => build.data?.lines ?? [], [build.data]);

  // AC-E0/AC-E1: membership and placement are separate. Every candidate the build returned
  // is either ranked (open demand) or folded (held, no open demand); nothing the build sends
  // is dropped, it just changes which table it renders in.
  const rankedRows = useMemo(() => rows.filter((r) => r.has_demand !== false), [rows]);
  const foldedRows = useMemo(() => rows.filter((r) => r.has_demand === false), [rows]);

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

  const historyRef = useRef(new Map<string, ContainerRequestHistoryProduct>());
  const historyLoadingRef = useRef(false);

  // Read through refs for the same reason the history sidecar is: a column definition that
  // depended on the record page's edit state would rebuild the whole grid on every keystroke.
  // Cell functions run on every render, so the typed figure still paints.
  const qtyForRef = useRef(qtyFor);
  qtyForRef.current = qtyFor;
  const onQtyChangeRef = useRef(onQtyChange);
  onQtyChangeRef.current = onQtyChange;
  const readOnlyRef = useRef(readOnly);
  readOnlyRef.current = readOnly;

  // A row edited to 0 leaves the request without being deleted from the grid - she can still
  // see and change her mind about it, it just does not go on the document.
  const renderQtyCell = useCallback((ctx: CellContext<ContainerRequestRow, unknown>) => {
    const original = ctx.row.original;
    return (
      <Input
        type="number"
        min={0}
        className="h-8 w-24 tabular-nums"
        value={qtyForRef.current(original)}
        disabled={readOnlyRef.current}
        // The netting rule with this row's own numbers in it (F2): what the figure IS, on
        // the figure, so nobody has to remember whether the packing list was subtracted.
        // `engine_qty`, never the edited figure: it is the formula's own answer.
        title={`${fmtInt(original.open_so_need)} need - ${fmtInt(original.on_hand)} on hand - ${fmtInt(original.incoming_spo)} incoming SPO = ${fmtInt(original.engine_qty)}`}
        onChange={(e) => {
          const next = Math.max(0, Number(e.target.value) || 0);
          onQtyChangeRef.current(original.row_key, next);
        }}
      />
    );
  }, []);

  const columns = useMemo<ColumnDef<ContainerRequestRow>[]>(
    () => [
      {
        id: 'rank',
        header: ({ column }) => (
          <span className="flex items-center gap-1">
            <DataGridColumnHeader title="Rank" column={column} />
            <FormulaTip
              label="How the rank is worked out"
              formula="score = sum(weight x value) / sum(weight)"
              terms={[
                { name: 'Need-by date', weight: 'x3', note: 'earliest SO date, sooner is higher' },
                { name: 'Demand class', weight: 'x3', note: 'project 1.0, retail 0.4' },
                { name: 'Document age', weight: 'x1', note: 'oldest SO date, older is higher' },
              ]}
              footer="Each value is scaled against the other rows here; a factor with no value is left out. Rank 1 = highest score. Hover a score for its factors; weights live in Policies."
            />
          </span>
        ),
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
              onClick={() => setOpenRowKey(original.row_key)}
              title="What this row is made of"
              className={cn(
                'flex min-w-0 flex-col text-start underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40',
                muted && 'opacity-70',
              )}
            >
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="truncate font-medium" title={original.item_code ?? ''}>
                  {original.item_code ?? EM_DASH}
                </span>
                {original.row_kind === 'set' ? (
                  // The supplier's code names our SET, so the row is the whole WC and every
                  // figure on it is the driver member's (R19). Badged rather than explained:
                  // the driver's own code sits underneath, which is the explanation.
                  <Badge
                    variant="secondary"
                    appearance="light"
                    size="sm"
                    className="shrink-0"
                    data-testid="set-badge"
                  >
                    Set
                  </Badge>
                ) : null}
              </span>
              <span
                className="truncate text-2xs text-muted-foreground"
                title={
                  original.row_kind === 'set'
                    ? `Figures from ${original.driver_item_code ?? 'its driver member'}`
                    : (original.product_name ?? '')
                }
              >
                {original.row_kind === 'set'
                  ? (original.driver_item_code ?? EM_DASH)
                  : (original.product_name ?? EM_DASH)}
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
            <FormulaTip
              label="How the suggested quantity is worked out"
              formula="suggested = need - on hand - incoming SPO"
              terms={[
                { name: 'Need', note: 'open SO lines, project and retail, until the plan date' },
                { name: 'On hand', note: 'site pools only' },
                { name: 'Incoming SPO', note: 'site pools only' },
              ]}
              footer="Never below 0. Incoming packing lists and open POs are shown beside it, not subtracted."
            />
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
          <PlanNumberButton
            value={fmtInt(row.original.project_qty)}
            label="Open project sales orders"
            // Nothing to open is not a link: a figure of zero with no line behind it would
            // open an empty table, which teaches the eye to stop clicking every one of them.
            disabled={
              !row.original.project_qty ||
              (linesByProduct.get(row.original.product_id) ?? []).every(
                (l) => l.demand_class !== 'project',
              )
            }
            onClick={() => setDialog({ kind: 'project', row: row.original })}
          />
        ),
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Project' },
      },
      {
        accessorKey: 'retail_qty',
        header: ({ column }) => <DataGridColumnHeader title="Retail" column={column} />,
        // Retail carries the unclassified lines too: the column already counts them (no
        // Unclassified column, AC-A2.2), so the drill lists what the figure counts.
        cell: ({ row }) => (
          <PlanNumberButton
            value={fmtInt(row.original.retail_qty)}
            label="Open retail sales orders"
            disabled={
              !row.original.retail_qty ||
              (linesByProduct.get(row.original.product_id) ?? []).every(
                (l) => l.demand_class === 'project',
              )
            }
            onClick={() => setDialog({ kind: 'retail', row: row.original })}
          />
        ),
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Retail' },
      },
      {
        accessorKey: 'on_hand',
        header: ({ column }) => <DataGridColumnHeader title="On hand" column={column} />,
        // Openable at zero too, unlike the demand cells: "nothing in any of the six pools" is
        // the answer the location table gives, and it is the one the buyer came for.
        cell: ({ row }) => (
          <PlanNumberButton
            value={fmtInt(row.original.on_hand)}
            label="Stock by location"
            onClick={() => setDialog({ kind: 'on_hand', row: row.original })}
          />
        ),
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'On hand' },
      },
      {
        accessorKey: 'incoming_spo',
        header: ({ column }) => <DataGridColumnHeader title="SPO" column={column} />,
        cell: ({ row }) => (
          <PlanNumberButton
            value={fmtInt(row.original.incoming_spo)}
            label="Shipping orders on their way to a site pool"
            onClick={() => setDialog({ kind: 'spo', row: row.original })}
          />
        ),
        size: 80,
        enableSorting: false,
        meta: { headerTitle: 'SPO' },
      },
      {
        accessorKey: 'incoming_pl',
        header: ({ column }) => <DataGridColumnHeader title="Incoming PL" column={column} />,
        // A reference: a packing list names no destination, so it can be read beside the ask
        // but never subtracted from it (Q1). The lightbox says which lists they are.
        cell: ({ row }) => (
          <PlanNumberButton
            value={fmtInt(row.original.incoming_pl)}
            label="Packing lists on their way, reference only"
            onClick={() => setDialog({ kind: 'incoming_pl', row: row.original })}
          />
        ),
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Incoming PL' },
      },
      {
        accessorKey: 'outstanding_po',
        header: ({ column }) => <DataGridColumnHeader title="PO" column={column} />,
        cell: ({ row }) => (
          <PlanNumberButton
            value={fmtInt(row.original.outstanding_po)}
            label="Purchase orders still to come, reference only"
            onClick={() => setDialog({ kind: 'po', row: row.original })}
          />
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
        cell: ({ row }) => (
          <HoldingCell
            row={row.original}
            onOpenBlocks={() => setDialog({ kind: 'blocks', row: row.original })}
          />
        ),
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
          <PeakCell
            history={historyRef.current.get(row.original.product_id)}
            loading={historyLoadingRef.current}
            kind="project"
            onOpen={() => setDialog({ kind: 'project', row: row.original, onHistory: true })}
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
          <PeakCell
            history={historyRef.current.get(row.original.product_id)}
            loading={historyLoadingRef.current}
            kind="retail"
            onOpen={() => setDialog({ kind: 'retail', row: row.original, onHistory: true })}
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
    data: rankedRows,
    getRowId: (row) => row.row_key,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // The fold's own table (S5): SAME column defs as the ranked grid, its own pagination and
  // sorting so the two scroll independently, no `listingKey` passed on either grid so both
  // fall back to the pathname - one preference store, one look.
  const foldTable = useReactTable({
    columns,
    data: foldedRows,
    getRowId: (row) => row.row_key,
    state: { pagination: foldPagination, sorting: foldSorting },
    onPaginationChange: setFoldPagination,
    onSortingChange: setFoldSorting,
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
    [table, rankedRows, pagination, sorting],
  );
  // Folded rows only pay for their own page of history once the fold is actually open -
  // collapsed is the default on every load, so asking for it up front would be the same
  // overfetch AC-B8 exists to avoid.
  const foldPageProductIds = useMemo(
    () => (foldOpen ? foldTable.getRowModel().rows.map((r) => r.original.product_id) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [foldTable, foldedRows, foldPagination, foldSorting, foldOpen],
  );
  const historyProductIds = useMemo(
    () => Array.from(new Set([...pageProductIds, ...foldPageProductIds])),
    [pageProductIds, foldPageProductIds],
  );
  const history = useContainerRequestHistory(supplierId, historyProductIds);
  historyRef.current = useMemo(() => {
    const map = new Map<string, ContainerRequestHistoryProduct>();
    for (const p of history.data?.products ?? []) map.set(p.product_id, p);
    return map;
  }, [history.data]);
  historyLoadingRef.current = history.isFetching;

  // `qtyFor` follows the record page's edits, so the cards move as she types - which is the
  // whole point of putting them above the grid.
  const summary = summariseContainerRequest(rows, qtyFor);

  const openRow = openRowKey
    ? (rows.find((r) => r.row_key === openRowKey) ?? null)
    : null;

  if (build.isLoading) {
    return (
      <div className="space-y-4">
        <Card className="p-4">
          <Skeleton className="h-6 w-64" />
          <Skeleton className="mt-3 h-24 w-full rounded-lg" />
        </Card>
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
            No open customer demand on what they supply, and nothing of theirs on file. Start a
            new plan from the loading plans list to hand over a newer stock list or proforma.
          </p>
        </Card>
      </div>
    );
  }


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
        recordCount={rankedRows.length}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No open customer demand for what this supplier supplies."
      >
        <Card>
          {/* The heading, and nothing else (R5): Send and the gear moved to the record's own
              toolbar, where the rest of the plan's actions already sit. */}
          <CardHeader className="py-3">
            <h3 className="text-sm font-semibold">
              What to ask {supplierName}
              {build.data.plan_horizon_date
                ? ` to cover until ${formatDateInMalaysia(build.data.plan_horizon_date)}`
                : ' for'}
            </h3>
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
                <DataGridTable />
              </CardTable>
              <CardFooter>
                <DataGridPagination />
              </CardFooter>
              {foldedRows.length > 0 ? (
                <Collapsible
                  open={foldOpen}
                  onOpenChange={setFoldOpen}
                  className="border-t border-border"
                >
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className={cn(
                        PRESSED_CLASS,
                        COARSE_HIT_TARGET_CLASS,
                        'flex w-full items-center gap-2 px-4 py-2.5 text-start text-sm text-muted-foreground hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 [&[data-state=open]_svg]:rotate-180',
                      )}
                    >
                      {/* The chevron flips without a transition: this fold is opened and
                          closed tens of times a day, and the frequency gate says an
                          interaction that often gets no motion of its own. */}
                      <ChevronDown className="size-4 shrink-0" aria-hidden />
                      {foldedRows.length} products held with no open demand
                    </button>
                  </CollapsibleTrigger>
                  {/* Tens-per-day interaction (row expand/collapse): no motion beyond what the
                      trigger's own chevron does. The shared primitive's height keyframes are
                      switched off here rather than reused as-is. */}
                  <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-none data-[state=open]:animate-none">
                    <DataGrid
                      table={foldTable}
                      recordCount={foldedRows.length}
                      tableLayout={{ width: 'fixed', columnsResizable: true }}
                    >
                      <CardTable>
                        <DataGridTable />
                      </CardTable>
                      <CardFooter>
                        <DataGridPagination />
                      </CardFooter>
                    </DataGrid>
                  </CollapsibleContent>
                </Collapsible>
              ) : null}
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

      {openRow ? (
        <ContainerRequestRowDialog
          row={openRow}
          askQty={qtyFor(openRow)}
          soLines={linesByProduct.get(openRow.product_id) ?? []}
          history={historyRef.current.get(openRow.product_id)}
          historyLoading={history.isFetching}
          onClose={() => setOpenRowKey(null)}
        />
      ) : null}

      {/* The documents behind one figure (R7). Every column's lightbox is this one dialog, so
          the eight of them cannot drift apart; only the body inside it changes. */}
      {dialog ? (
        <PlanRowDialog
          kind={dialog.kind}
          productCode={dialog.row.item_code ?? dialog.row.product_name ?? 'This product'}
          productName={
            dialog.row.row_kind === 'set'
              ? // A set row's figures are the driver member's (R19), and so are its documents:
                // the dialog says whose rather than leaving the reader to guess.
                `${dialog.row.set_name ?? dialog.row.product_name ?? ''} · figures from ${dialog.row.driver_item_code ?? 'its driver member'}`
              : dialog.row.product_name
          }
          context={dialogContext(dialog, build.data?.plan_horizon_date ?? null)}
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
        >
          {dialog.kind === 'project' || dialog.kind === 'retail' ? (
            <ProjectRetailTabs
              channel={dialog.kind}
              lines={toDemandLines(
                (linesByProduct.get(dialog.row.product_id) ?? []).filter((l) =>
                  dialog.kind === 'project'
                    ? l.demand_class === 'project'
                    : l.demand_class !== 'project',
                ),
              )}
              history={toHistoryPoints(historyRef.current.get(dialog.row.product_id))}
              initialTab={dialog.onHistory ? 'history' : 'open'}
              focus={dialog.kind}
              loading={build.isFetching || (dialog.onHistory && history.isFetching)}
            />
          ) : dialog.kind === 'on_hand' ? (
            <OnHandTable productId={dialog.row.product_id} />
          ) : dialog.kind === 'spo' ? (
            <SpoTabs supplierId={supplierId} productId={dialog.row.product_id} />
          ) : dialog.kind === 'blocks' ? (
            <BlocksTable row={dialog.row} />
          ) : dialog.kind === 'incoming_pl' ? (
            <IncomingPlTable
              supplierId={supplierId}
              productId={dialog.row.product_id}
              onOpenShipment={(shipmentId) =>
                router.push(`/procurement-management/packing-lists/${shipmentId}`)
              }
            />
          ) : (
            <PoTabs supplierId={supplierId} productId={dialog.row.product_id} />
          )}
        </PlanRowDialog>
      ) : null}
    </div>
  );
}

export default ContainerRequestSection;
