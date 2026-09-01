'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import {
  ColumnDef,
  ExpandedState,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { EM_DASH, fmtDecimal, fmtInt, fmtMoney, fmtSigned } from '../../lib/format';
import {
  PLAN_LINE_STATUS_LABEL,
  PLAN_LINE_STATUS_ORDER,
  type PlanLine,
  type PlanLineStatus,
} from '../lib/planLine';
import {
  decidedCost,
  decidedQty,
  groupDecisionState,
  type PlanDecisionMap,
} from '../lib/planDecisions';
import {
  planPillReading,
  suggestedDecisionFor,
  type PlanRowEdit,
  type PlanRowEditMap,
} from '../lib/planEdits';
import { NO_COVER, type CoverProposal } from '../lib/coverPlan';
import {
  PRICE_ADVICE_LABEL,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';
import { levelActionLabel, type LevelSuggestion } from '../lib/levelSuggestion';
import { poOffset, type PoReceipt } from '../lib/poCover';
import type { TrajectoryEntry } from '../lib/trajectory';
import type { ProductPurchaseTrend } from '../lib/purchaseTrend';
import { PlanTrendPopover } from './PlanTrendPopover';
import { PlanDecisionPill } from './PlanDecisionPill';
import { PlanNumberButton } from './PlanNumberButton';
import { PlanRowPanel } from './PlanRowPanel';
import { PlanRowDialog, type PlanDialogRequest } from './PlanRowDialogs';
import type { ProductEconomics } from '../lib/productHealth';
import { PlanChecklistPopover } from './PlanChecklistPopover';
import { PlanDemandPopover } from './PlanDemandPopover';
import { ProductPhotoPopover, type ProductPhotoStatus } from './ProductPhotoPopover';
import {
  DaysCoverDrill,
  ExplainNumber,
  NetDrill,
} from './PlanExplainDrills';
import { OrderQtyLedger } from './PlanOrderQtyLedger';
import {
  groupPlanLinesByChannel,
  isGroupedLine,
  PLAN_CHANNEL_ORDER,
  PLAN_CHANNEL_LABEL,
  type PlanChannel,
} from '../lib/planLineGrouping';
import { DynamicFilterBuilder } from '@/components/list/DynamicFilterBuilder';
import { SavedViewsMenu } from '@/components/list/SavedViewsMenu';
import { countFilterConditions, evaluateFilterGroup } from '@/lib/list-query/dynamicFilter';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import type { SavedView, SavedViewConfig } from '@/services/savedViewsService';
import { planLineFilterFields } from '../lib/planLineFilterFields';

/** The listing key `PlanLinesGrid` personalizes column config AND saved segments
 *  under (S4, PLAN-scm-reorder-oi-feedback-1sep.md) - one constant, so the two
 *  cannot drift apart. */
const REORDER_PLAN_LINES_LISTING_KEY = 'scm.dashboard.view::reorder-plan-lines';

/**
 * ONE grid for every line of a plan.
 *
 * > "ALL should be in 1 table, 1 list, 1 data grid table, you don't tell me what's over or
 * >  within budget, because I haven't decided which one i want to buy"
 *
 * Replaces six separate surfaces. `status` is still a field on the row (it drives the
 * Filters popover and the summary tiles above), but it is not a COLUMN (user markup,
 * 2026-08-12: "the status is not needed" - the merged Decision cell already says what a line
 * is via its own mix). There is deliberately NO budget here: within and over are the result
 * of step 4, not a property of a line.
 *
 * The offsets the engine netted (on hand, incoming, on order) are COLUMNS, because burying
 * them in a popover is what made the netting feel like a decision taken on the buyer's behalf.
 *
 * Column order is a STORY, result first and explanation after, in chapters (user markup,
 * 2026-08-11: "we should always tell the result / suggestive columns, then followed by
 * explanation columns"):
 *   1. what and how much - product, location, SUGGESTED QTY, then the arithmetic behind
 *      it (SO / On hand / SPO / PO, named the way the source documents are named);
 *   2. the action - ONE Decision cell that carries the suggestion AND takes it (user markup,
 *      2026-08-12: "I want the decision and suggestion to be made in 1 place");
 *   3. the money - suggested price, suggested supplier, then the total cost they produce;
 *   4. the AutoCount round-trip - suggested level + reorder qty.
 * Net and runway are computed steps, not decisions, so they ship hidden and live on in
 * the row-click derivation; the columns menu brings them back for whoever wants them.
 */

/**
 * Swallows a click so it never reaches the row.
 *
 * The row opens the full derivation, and `onRowClick` is handed the row rather than the
 * event, so it cannot tell an interactive cell from the row itself. Without this, adjusting a
 * quantity or opening a drill would also open the dialog on top of what you were doing.
 */
function StopClick({ children }: { children: React.ReactNode }) {
  return (
    <span onClick={(e) => e.stopPropagation()} className="contents">
      {children}
    </span>
  );
}

/**
 * One channel demand figure (AC-F07).
 *
 * NULL is UNAVAILABLE - a legacy run has no breakdown and it is never inferred or
 * backfilled (AC-F10) - which is a different fact from a channel that genuinely
 * needs nothing, and must not be printed as 0.
 */
function ChannelNeed({
  value,
  title,
  tone,
  onOpen,
}: {
  value: number | null | undefined;
  title: string;
  tone?: 'exception';
  /** The number IS the trigger (plan 4.6) - no (i) icon beside it, no hover popover. */
  onOpen?: () => void;
}) {
  if (value === null || value === undefined) {
    return (
      <span className="text-2xs text-muted-foreground" title="Unavailable on a legacy plan">
        Unavailable
      </span>
    );
  }
  return (
    <span className={cn(tone === 'exception' && value > 0 && 'text-scm-overstock')}>
      <PlanNumberButton
        value={fmtInt(value)}
        label={title}
        onClick={() => onOpen?.()}
        disabled={!onOpen}
      />
    </span>
  );
}

/**
 * One channel COLUMN cell on the grouped (product-grain) grid (5.3 follow-up, 19-20 Aug):
 * the channel's whole open demand (`committed_v`'s split, summed across the product's
 * locations) - never `project_need`, the confirmed-for-buy SUBSET. `confirmedNote` is the
 * Project cell's own aside ("N confirmed for buy"), passed only for the Project column
 * and only when > 0.
 *
 * The trend subline this cell used to carry ("Orders rising - consider more - avg N/day")
 * is gone (captain, 21 Aug: "i don't think we need the orders rising thingy") - the
 * number plus the drill trigger (`drill`, below) replace it: the buyer opens the actual
 * orders rather than reading a verdict about them. Its wording helper, `channelTrendLine`,
 * had no other caller and is deleted with it (`lib/trajectory.ts`); `TRAJECTORY_ROW_LABEL`
 * stays - `PlanTrendPopover`'s own row-level trend still reads it. `channelTrendFor` /
 * `ChannelTrendEntry` / `channel_trends` still flow from `usePlanLines.ts` through
 * `PlanLinesSection.tsx` into this component's own props with no call site left inside
 * it - a follow-up outside this file's scope to remove that plumbing too.
 */
function ChannelColumnCell({
  value,
  confirmedNote,
  label,
  onOpen,
}: {
  value: number | null | undefined;
  confirmedNote?: string | null;
  label: string;
  /** The number IS the trigger (plan 4.6): the (i) icon and its hover popover are gone. */
  onOpen?: () => void;
}) {
  if (value === null || value === undefined) {
    return (
      <span className="text-2xs text-muted-foreground" title="Unavailable on a legacy plan">
        Unavailable
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5" title={confirmedNote ?? undefined}>
      <PlanNumberButton
        value={fmtInt(value)}
        label={label}
        onClick={() => onOpen?.()}
        disabled={!onOpen}
      />
    </span>
  );
}

/** A dash means "not on file", which is a different fact from zero and must not read as it. */
function numCell(value: number | null | undefined) {
  return value === null || value === undefined ? (
    <span className="text-muted-foreground">{EM_DASH}</span>
  ) : (
    fmtInt(value)
  );
}

export function PlanLinesGrid({
  lines,
  decisions,
  edits = {},
  onRowEdit,
  onResetRow,
  toolbarPrimary,
  coverFor,
  priceFor,
  cheaperFor,
  levelFor,
  poFor,
  trendFor,
  trendSeriesMonths = 24,
  purchaseTrendFor,
  purchaseTrendReady,
  purchaseTrendWindowMonths = 3,
  onOpenPurchaseTrend,
  hasPhotoFor,
  photoStatus = 'idle',
  onOpenPhoto,
  economicsFor,
  healthThresholds = { margin_floor_pct: 15, dead_turnover_months: 6 },
  healthWindows,
  statusFilter: statusFilterProp = null,
  onStatusFilterChange,
  decidedFilter: decidedFilterProp,
  onDecidedFilterChange,
  secondaryActions,
  runId,
  decisionsReadOnly = false,
  readOnlyReason = null,
  groupByChannel = false,
  isLoading,
}: {
  lines: PlanLine[];
  decisions: PlanDecisionMap;
  /** The unsaved drafts on this plan, keyed by ROW id (plan 4.5). Empty = nothing edited. */
  edits?: PlanRowEditMap;
  /** Write one field of a row's draft. Nothing on this grid writes to the backend any more:
   *  the panel edits a draft and Save persists the lot in one request. */
  onRowEdit?: (line: PlanLine, patch: PlanRowEdit) => void;
  /** Drop a row's draft ("Use suggestion"). */
  onResetRow?: (line: PlanLine) => void;
  /** Save (N) and Confirm (N), rendered at the right end of the grid's own toolbar, after
   *  Actions (R11). The SECTION owns them - it owns the draft map they act on. */
  toolbarPrimary?: React.ReactNode;
  /** What the plan suggests for a line: buy, cover from elsewhere, or a split of the two. */
  coverFor?: (line: PlanLine) => CoverProposal;
  /** What we last paid this line's supplier, and how old that is. Undefined = no opinion. */
  priceFor?: (line: PlanLine) => PriceAdvice | undefined;
  /** S13e: a materially cheaper supplier on the line's own shortlist, when one exists. */
  cheaperFor?: (line: PlanLine) => CheaperAlternative | null;
  /** S13f: the AutoCount level this run suggests for the line's product+location. */
  levelFor?: (line: PlanLine) => LevelSuggestion | undefined;
  /** S15: the open PO lines already carrying this product to this warehouse. */
  poFor?: (line: PlanLine) => PoReceipt[];
  /** Is this product's demand sustaining or dying off, on this line's side. */
  trendFor?: (line: PlanLine) => TrajectoryEntry | undefined;
  /** How far back that trend's series reaches, for the "no orders dated in the last N
   *  months" line. Off the payload, never a literal on the screen. */
  trendSeriesMonths?: number;
  /** The mirror of `trendFor`, on the buy side: what we have actually purchased. */
  purchaseTrendFor?: (line: PlanLine) => ProductPurchaseTrend | undefined;
  /** The window the purchase-trend sentence compares (months). */
  purchaseTrendWindowMonths?: number;
  /** Whether the lazy purchase-trend fetch has answered - "no purchases" and "not asked
   *  yet" are the same `undefined` otherwise, and the ledger's History block must not
   *  print the first for the second. */
  purchaseTrendReady?: boolean;
  /** Fired the first time a PO cell's popover opens - lets the caller lazily start the
   *  purchase-trend fetch instead of it running for every product on plan mount. */
  onOpenPurchaseTrend?: () => void;
  /** Whether the run's photo map says this line's product has a photo at all. */
  hasPhotoFor?: (line: PlanLine) => boolean;
  /** Where the run's photo map is. Until it is `ready`, "no photo" is not yet a fact. */
  photoStatus?: ProductPhotoStatus;
  /** Fired the first time a photo popover opens - starts the run-wide photo fetch, the same
   *  laziness `onOpenPurchaseTrend` gives the PO cell. */
  onOpenPhoto?: () => void;
  /** What the product sells for and how fast it moves. Undefined = no opinion. */
  economicsFor?: (line: PlanLine) => ProductEconomics | undefined;
  /** The policy's lines for "thin margin" and "dead turnover". */
  healthThresholds?: { margin_floor_pct: number; dead_turnover_months: number };
  /** The windows the movement class was judged on, so the popup can say them. */
  healthWindows?: { sold_window_months?: number; bought_window_months?: number };
  /** Status the list is narrowed to, or null for the whole plan. Controlled so the summary
   *  tiles can narrow it: they used to reveal a band, and there are no bands now. */
  statusFilter?: PlanLineStatus | null;
  onStatusFilterChange?: (next: PlanLineStatus | null) => void;
  /** Undecided/decided the list is narrowed to, or 'all'. Controlled the same way
   *  `statusFilter` is, so the decision-progress tile can toggle it - "clicking it shows
   *  only what is left" - without owning a second copy of the filter. */
  decidedFilter?: 'all' | 'undecided' | 'decided';
  onDecidedFilterChange?: (next: 'all' | 'undecided' | 'decided') => void;
  /** Quiet links to the reports this grid does not carry rows for (Order summary, Plan
   *  exceptions, PO worklist) - rendered in the SAME row as Filters / Columns / Export,
   *  never as a tile. Omit to hide them (e.g. the SCM simulation tab, which has none of
   *  those reports). */
  secondaryActions?: ToolbarAction[];
  /** The run on screen, threaded to each row's demand drill so it can fetch its order lines. */
  runId?: string | null;
  /**
   * S16 (captain, 21 Aug, 3rd time requested): the row IS the decision surface now, on
   * every grain and every rec_type this can be decided over - the old grain-based lock
   * ("Decided at Product grain - open the Product sheet") is gone; a grouped row decides
   * by fanning the SAME decision out to its members (see `groupDecisionState` /
   * `usePlanLines.decide`). The ONE thing that still genuinely cannot be recorded here is
   * a run that predates the front-planning contract - its decisions are history, and
   * `readOnlyReason` carries that sentence.
   */
  decisionsReadOnly?: boolean;
  /** What the disabled control says, in place of the decision cell's own controls. */
  readOnlyReason?: string | null;
  /**
   * Product-grain runs only (5.3, follow-up 19-20 Aug): group the fetched per-warehouse
   * rows into one row per PRODUCT - "1 line of retail, 1 line of project" folded into ONE
   * line, with Project/Retail as dynamic COLUMNS on it instead of a row each -
   * rather than one row per (product, warehouse). A group row sums the shared display
   * fields across its warehouses; every location-only fact (price, supplier, MOQ,
   * AutoCount level) stays on the per-warehouse rows reachable by expanding it. Omit or
   * pass false to render the per-warehouse rows exactly as before (Location grain, a
   * legacy run, or any other caller of this grid).
   */
  groupByChannel?: boolean;
  isLoading?: boolean;
}) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  // No column is actively sorted by default: the DEFAULT order comes from `ordered` below
  // (undecided first, decided sunk to the bottom, rank-ordered within each). Clicking a
  // header still sorts normally - the buyer overriding the default is a real request.
  const [sorting, setSorting] = useState<SortingState>([]);
  // Which grouped rows (5.3) are drilled open. Keyed by row id, same as the table's own
  // `getRowId` - a group row is never expanded by default, matching "1 line of retail, 1
  // line of project" being the resting state the buyer asked for.
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
  } = useDebouncedSearch();
  const statusFilter: string = statusFilterProp ?? 'all';
  const setStatusFilter = useCallback(
    (next: string) => onStatusFilterChange?.(next === 'all' ? null : (next as PlanLineStatus)),
    [onStatusFilterChange],
  );
  // Undecided/decided is its own filter, controllable the same way statusFilter is: the
  // reorder page's decision-progress tile drives it from outside, and every other caller
  // (the SCM simulation tab) leaves it uncontrolled and gets its own local toggle.
  const [ownDecidedFilter, setOwnDecidedFilter] = useState<'all' | 'undecided' | 'decided'>('all');
  const decidedFilter = decidedFilterProp ?? ownDecidedFilter;
  const setDecidedFilter = useCallback(
    (next: string) => (onDecidedFilterChange ?? setOwnDecidedFilter)(next as 'all' | 'undecided' | 'decided'),
    [onDecidedFilterChange],
  );
  // S14: one filter per suggestion column, so the buyer can work one question at a time
  // ("show me every stale price", "every level change", "project side only").
  const [priceFilter, setPriceFilter] = useState<string>('all');
  const [actionFilter, setActionFilter] = useState<string>('all');
  const [levelFilter, setLevelFilter] = useState<string>('all');
  // Which number a buyer pressed, and on which row (plan 4.6). ONE dialog per grid: only
  // one can be open at a time, and six mounted bodies per row is what the popovers cost.
  const [dialogRequest, setDialogRequest] = useState<PlanDialogRequest | null>(null);
  // S4 (PLAN-scm-reorder-oi-feedback-1sep.md): the dynamic filter builder + saved
  // segments, first consumer of the reusable pair. `segmentId` is which saved view is
  // currently applied (null = none) - kept separate from `filterGroup` because applying
  // a segment also sets sort/columns, and the menu needs to know WHICH one is active to
  // badge it and offer Delete/Publish.
  const [filterGroup, setFilterGroup] = useState<ListQueryFilterGroup | null>(null);
  const [segmentId, setSegmentId] = useState<string | null>(null);
  const filterFields = useMemo(() => planLineFilterFields(decisions), [decisions]);

  const filtered = useMemo(() => {
    const needle = searchQuery.trim().toLowerCase();
    return lines.filter((l) => {
      if (statusFilter !== 'all' && l.status !== statusFilter) return false;
      if (decidedFilter === 'undecided' && decisions[l.id]) return false;
      if (decidedFilter === 'decided' && !decisions[l.id]) return false;
      if (priceFilter !== 'all') {
        const advice = l.purchasable ? priceFor?.(l)?.advice : undefined;
        if ((advice ?? 'none') !== priceFilter) return false;
      }
      if (actionFilter !== 'all') {
        // "Includes X": the same derivation the Suggested-action cell renders. A row can
        // suggest several parts (use stock + use PO + buy), so the filter matches any row
        // whose suggestion CONTAINS the picked one rather than demanding an exact shape.
        const cover = l.purchasable ? (coverFor?.(l) ?? NO_COVER) : NO_COVER;
        const afterStock = cover.coverQty > 0 ? cover.buyQty : Math.ceil(l.order_qty);
        const poQty = (poFor?.(l) ?? []).reduce((t, r) => t + r.remaining, 0);
        const { usePo, buy } = poOffset(afterStock, poQty);
        const parts = new Set<string>();
        if (l.purchasable && cover.coverQty > 0) parts.add('use_stock');
        if (l.purchasable && usePo > 0) parts.add('use_po');
        if (l.purchasable && buy > 0) parts.add('buy');
        if (!parts.has(actionFilter)) return false;
      }
      if (levelFilter !== 'all') {
        const s = levelFor?.(l);
        const state = !s ? 'none' : levelActionLabel(s).changed ? 'change' : 'keep';
        if (state !== levelFilter) return false;
      }
      // S4: the dynamic filter builder / applied segment, evaluated client-side over
      // the same already-fetched rows (AC-4.1) - no server round trip.
      if (!evaluateFilterGroup(filterGroup, l, filterFields)) return false;
      if (!needle) return true;
      return (
        l.sku.toLowerCase().includes(needle) ||
        l.product_name.toLowerCase().includes(needle) ||
        l.warehouse.toLowerCase().includes(needle) ||
        l.supplier.name.toLowerCase().includes(needle)
      );
    });
  }, [lines, searchQuery, statusFilter, decidedFilter, priceFilter,
      actionFilter, levelFilter, decisions, priceFor, coverFor, levelFor, poFor,
      filterGroup, filterFields]);

  // Undecided first, decided sunk to the bottom (user markup, 2026-08-12: "so they can decide
  // until all outstanding decisions are cleared"). `filtered` is already rank-ordered (`lines`
  // comes out of `toPlanLines` sorted by rank), and `Array.prototype.sort` is stable, so this
  // grouping never disturbs the rank order WITHIN either group - only the two groups move.
  const ordered = useMemo(
    () => [...filtered].sort((a, b) => (decisions[a.id] ? 1 : 0) - (decisions[b.id] ? 1 : 0)),
    [filtered, decisions],
  );

  // 5.3: one row per PRODUCT on a Product-grain run, each expandable to the per-warehouse
  // rows it summed. Grouping runs AFTER the existing filter/sort pipeline, so search/
  // status/side/price/action/level all narrow the same per-warehouse facts they always
  // did; only the rendered ROW count changes.
  const tableData = useMemo<PlanLine[]>(
    () => (groupByChannel ? groupPlanLinesByChannel(ordered) : ordered),
    [groupByChannel, ordered],
  );

  // The channel COLUMN set: Project and Retail, always (captain, 28 Aug 2026: "where is my
  // project quantity column" on a run whose rows were all retail). The 19-20 Aug rule
  // derived the set from the WAREHOUSE SEGMENTS the run happened to touch, so Project
  // vanished for a whole plan with no project demand - a missing column, where the answer
  // was a zero. R17 ended the derivation outright: a demand channel is the sales order's
  // own class, never where the stock sits. Empty on the ungrouped grid, which has no
  // channel columns at all.
  const dynamicChannels = useMemo<PlanChannel[]>(
    () => (groupByChannel ? PLAN_CHANNEL_ORDER : []),
    [groupByChannel],
  );

  // Channel-column totals (captain follow-up, 2026-08-20: "I wonder what is the total for
  // project & retail, anyway to indicate that in a nice way"). Summed over `tableData` -
  // the FILTERED, grouped rows on screen right now, not the whole run - so the figure
  // moves with search/status/side/etc. the way the grid itself does. `tableData` in
  // grouped mode is already one row per product with no member subrows folded in, so
  // nothing here is double-counted.
  const channelTotals = useMemo(() => {
    const totals: Partial<Record<PlanChannel, number>> = {};
    if (!groupByChannel) return { totals, count: 0 };
    for (const line of tableData) {
      if (!isGroupedLine(line)) continue;
      for (const channel of dynamicChannels) {
        const v = line.__group.channelQty[channel];
        if (v === null || v === undefined) continue;
        totals[channel] = (totals[channel] ?? 0) + v;
      }
    }
    return { totals, count: tableData.length };
  }, [groupByChannel, tableData, dynamicChannels]);

  /**
   * The engine's own mixture for a row, and the pill that reports where it stands. Read from
   * ONE derivation (`suggestedDecisionFor`) so the pill, the panel and Confirm can never
   * disagree about what "the suggestion" is.
   */
  const readingFor = useCallback(
    (line: PlanLine) => {
      const suggested = suggestedDecisionFor(line, coverFor?.(line) ?? NO_COVER, poFor?.(line) ?? []);
      const { decision } = isGroupedLine(line)
        ? groupDecisionState(line.__group.members.map((m) => m.id), decisions)
        : { decision: decisions[line.id] };
      return planPillReading(edits[line.id], decision, suggested);
    },
    [coverFor, poFor, decisions, edits],
  );

  /** Open one of the six lightboxes on a row (plan 4.6). */
  const openDialog = useCallback(
    (kind: PlanDialogRequest['kind'], line: PlanLine) => setDialogRequest({ kind, line }),
    [],
  );


  const columns = useMemo<ColumnDef<PlanLine>[]>(
    () => [
      {
        id: 'rank',
        accessorFn: (row) => row.rankOrder ?? Number.MAX_SAFE_INTEGER,
        header: ({ column }) => <DataGridColumnHeader title="#" visibility column={column} />,
        // An unranked line shows a dash rather than a number the engine never assigned.
        cell: ({ row }) =>
          row.original.rankOrder === null ? (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ) : (
            <span className="tabular-nums">{row.original.rankOrder}</span>
          ),
        // Wide enough for a four-digit rank: it is the FIRST column, so it carries the
        // grid's edge padding too, and at 36 a plan of more than 99 rows truncated its
        // own rank to "1...".
        size: 60,
        enableSorting: true,
        meta: { headerTitle: 'Priority', skeleton: <Skeleton className="h-4 w-6" /> },
      },
      {
        id: 'sku',
        accessorKey: 'sku',
        header: ({ column }) => <DataGridColumnHeader title="Product" visibility column={column} />,
        cell: ({ row }) => {
          const group = isGroupedLine(row.original) ? row.original.__group : null;
          return (
            <div className="min-w-0 space-y-px">
              <div className="flex items-center gap-1.5">
                {/* The chevron is purely a state indicator - the whole row toggles the
                    decision panel open (`onRowClick`). EVERY row carries one now: the panel
                    is where a decision is made, and a per-warehouse row is as decidable as a
                    grouped product row. */}
                {row.getIsExpanded() ? (
                  <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                ) : (
                  <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                )}
                <span className="truncate text-sm font-medium" title={row.original.sku}>
                  {row.original.sku}
                </span>
                {/* Which orders this quantity is for, and the lookups the buyer used to do by
                    hand. Both were on the old row and are the reason a number is trustworthy.
                    A group row carries none of these: they are keyed to ONE recommendation
                    (the demand/checklist popovers) or would repeat once per member. */}
                <StopClick>
                  {!group && (
                    <>
                      <PlanDemandPopover runId={runId ?? null} recId={row.original.id} />
                      <PlanChecklistPopover rec={row.original.rec} />
                    </>
                  )}
                  {/* What the thing IS - keyed by product, so it reads the same at either
                      grain. */}
                  <ProductPhotoPopover
                    runId={runId ?? null}
                    productId={row.original.product_id}
                    sku={row.original.sku}
                    productName={row.original.product_name}
                    hasPhoto={hasPhotoFor?.(row.original) ?? false}
                    status={photoStatus}
                    onOpen={onOpenPhoto}
                  />
                </StopClick>
              </div>
              <div className="truncate text-xs text-muted-foreground" title={row.original.product_name}>
                {row.original.product_name}
              </div>
            </div>
          );
        },
        size: 150,
        enableSorting: true,
        enableHiding: false,
        meta: {
          headerTitle: 'Product',
          skeleton: (
            <div className="space-y-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-24" />
            </div>
          ),
          // The decision itself (plan 4.4). `DataGridTable` renders this full-width below
          // any row whose `getIsExpanded()` is true, same mechanism as `POIntakeLinesGrid`'s
          // note panel. Every row can open it, and several can be open at once - Expand all
          // needs that, and a buyer comparing two products should not have to close one.
          expandedContent: (line: PlanLine) => (
            <PlanRowPanel
              line={line}
              edit={edits[line.id]}
              decision={
                isGroupedLine(line)
                  ? groupDecisionState(line.__group.members.map((m) => m.id), decisions).decision
                  : decisions[line.id]
              }
              cover={coverFor?.(line) ?? NO_COVER}
              poReceipts={poFor?.(line) ?? []}
              price={priceFor?.(line)}
              cheaper={cheaperFor?.(line) ?? null}
              levelSuggestion={levelFor?.(line)}
              economics={economicsFor?.(line)}
              healthWindows={healthWindows}
              disabled={decisionsReadOnly}
              lockReason={decisionsReadOnly ? readOnlyReason : null}
              onEdit={(patch) => onRowEdit?.(line, patch)}
              onUseSuggestion={() => onResetRow?.(line)}
            />
          ),
        },
      },
      // Grouped mode drops the Location column entirely (19-20 Aug follow-up, captain:
      // "i don't need locations column") - the group's own locations are already reachable
      // by expanding the row (`GroupMembersPanel`), so the column would only repeat what the
      // expand already carries. Ungrouped (Location-grain) mode keeps it: there it IS the
      // row's identity.
      ...(!groupByChannel ? [{
        id: 'warehouse',
        accessorKey: 'warehouse',
        header: ({ column }) => <DataGridColumnHeader title="Location" visibility column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={row.original.warehouse}>
            {row.original.warehouse}
          </span>
        ),
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-20" /> },
      } satisfies ColumnDef<PlanLine>] : []),
      // The SO and Project/Retail columns are an UNGROUPED-only chapter (5.3 follow-up,
      // 19-20 Aug): grouped mode replaces them with the channel columns below - "instead
      // of 1 column SO, 1 column project, 1 column retail, it should be 2 columns".
      //
      // There is no "Order type" chip beside them any more (R17, captain 28 Aug). It read
      // Project or Retail off the WAREHOUSE'S SEGMENT, which is a fact about where stock
      // sits, not about who ordered it - so a retail order into a project bin was labelled
      // Project beside a Retail column that counted it correctly. A demand channel is
      // `sales_orders.demand_class` on this screen and nothing else.
      ...(!groupByChannel ? [{
        id: 'needed',
        accessorFn: (row) => row.rec.outstanding_sales ?? 0,
        // Named after the DOCUMENT it comes from (user markup, 2026-08-11: "the needed is
        // SO right? I want to name it SO ... to make it relatable"). Same for SPO and PO
        // below: the buyer reconciles these against AutoCount extracts carrying exactly
        // these names, and a synonym is one more translation they have to hold in their
        // head.
        header: ({ column }) => (
          <DataGridColumnHeader title="SO" visibility column={column} />
        ),
        cell: ({ row }) => (
          <div className="min-w-0">
            <span
              className="tabular-nums"
              title="Outstanding sales-order quantity - the demand this line covers"
            >
              {numCell(row.original.rec.outstanding_sales)}
            </span>
            {/* The trend lives on the DEMAND column: it is a statement about the orders
                behind this number, not about the action (user markup, 2026-08-11). */}
            <StopClick>
              <PlanTrendPopover
                trend={trendFor?.(row.original)}
                sellingPrice={economicsFor?.(row.original)?.avg_sell_price ?? null}
                runId={runId ?? null}
                productId={row.original.product_id}
                segment={row.original.rec.segment ?? 'project'}
                outstandingSales={row.original.rec.outstanding_sales ?? null}
                seriesMonths={trendSeriesMonths}
              />
            </StopClick>
            {/* The velocity behind the trend verdict - the fast/slow, high/low evidence a
                bare "rising"/"falling" pill does not carry on its own. */}
            {row.original.forecast_daily_demand ? (
              <span
                className="block truncate text-2xs text-muted-foreground"
                title={`Average demand: ${fmtDecimal(row.original.forecast_daily_demand)}/day`}
              >
                {`avg ${fmtDecimal(row.original.forecast_daily_demand)}/day`}
              </span>
            ) : null}
          </div>
        ),
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'SO (needed)', skeleton: <Skeleton className="h-4 w-10" /> },
      } satisfies ColumnDef<PlanLine>,
      // The SO column's channel split (AC-F05 / AC-F07). TWO demand columns; the supply
      // columns below stay single shared facts of this product-location and are
      // deliberately NOT repeated per channel. There is no third: a sales order with no
      // class reads as retail and the SO import refuses a file that would create one (P4).
      {
        id: 'project_need',
        accessorFn: (row) => row.rec.project_need ?? -1,
        header: ({ column }) => (
          <DataGridColumnHeader title="Project" visibility column={column} />
        ),
        cell: ({ row }) => (
          <ChannelNeed
            value={row.original.rec.project_need}
            title="Project demand - open the orders behind it"
            onOpen={() => openDialog('project', row.original)}
          />
        ),
        size: 74,
        enableSorting: true,
        meta: { headerTitle: 'Project need', skeleton: <Skeleton className="h-4 w-10" /> },
      } satisfies ColumnDef<PlanLine>,
      {
        id: 'retail_need',
        accessorFn: (row) => row.rec.retail_need ?? -1,
        header: ({ column }) => (
          <DataGridColumnHeader title="Retail" visibility column={column} />
        ),
        cell: ({ row }) => (
          <ChannelNeed
            value={row.original.rec.retail_need}
            title="Retail demand - open the orders behind it"
            onOpen={() => openDialog('retail', row.original)}
          />
        ),
        size: 74,
        enableSorting: true,
        meta: { headerTitle: 'Retail need', skeleton: <Skeleton className="h-4 w-10" /> },
      } satisfies ColumnDef<PlanLine>] : []),
      // The dynamic channel columns (5.3 follow-up, 19-20 Aug): one per channel present in
      // the run (`dynamicChannels`), each showing that channel's WHOLE open demand
      // (`committed_v`'s split, summed across the product's locations), plus the SAME
      // demand-drill trigger the per-location group panel already carries (21 Aug
      // follow-up), scoped to the WHOLE product (`scope="product"`) since this cell's own
      // number is the union across every one of the product's recommendations. The
      // Project column carries the confirmed-for-buy subset as an info aside, never as
      // its own figure - the columns sum to the product's SO total the same way
      // `committed_v` sums per location.
      ...(groupByChannel
        ? dynamicChannels.map((channel): ColumnDef<PlanLine> => ({
            id: `channel_${channel}`,
            accessorFn: (row) =>
              (isGroupedLine(row) ? row.__group.channelQty[channel] : null) ?? -1,
            header: ({ column }) => (
              <DataGridColumnHeader title={PLAN_CHANNEL_LABEL[channel]} visibility column={column} />
            ),
            // A total of the rows on screen right now (not the whole run), lined up under
            // its own column the way a spreadsheet totals a column - so it reads with the
            // header above it and needs no caption of its own.
            footer: () => {
              const value = channelTotals.totals[channel];
              return (
                <span
                  className="tabular-nums text-muted-foreground"
                  title={`Total across the ${channelTotals.count} product${channelTotals.count === 1 ? '' : 's'} listed`}
                >
                  {value !== undefined ? fmtInt(value) : EM_DASH}
                </span>
              );
            },
            cell: ({ row }) => {
              const line = row.original;
              if (!isGroupedLine(line)) return null;
              const value = line.__group.channelQty[channel];
              const confirmed =
                channel === 'project' && (line.__group.projectConfirmedQty ?? 0) > 0
                  ? `${fmtInt(line.__group.projectConfirmedQty as number)} confirmed for buy`
                  : null;
              // Only the two demand channels open a document list - `unclassified` has no
              // configured window and no book of its own to show.
              const openable = channel === 'project' || channel === 'retail';
              return (
                <ChannelColumnCell
                  value={value}
                  confirmedNote={confirmed}
                  label={`${PLAN_CHANNEL_LABEL[channel]} demand - open the orders behind it`}
                  onOpen={openable ? () => openDialog(channel, line) : undefined}
                />
              );
            },
            size: 74,
            enableSorting: true,
            meta: {
              headerTitle: `${PLAN_CHANNEL_LABEL[channel]} (open demand)`,
              skeleton: <Skeleton className="h-4 w-10" />,
            },
          }))
        : []),
      // The three offsets, on the row rather than behind a popover. This is the arithmetic
      // that produced the suggested quantity, and the buyer has to be able to see it without
      // opening anything.
      {
        id: 'on_hand',
        accessorFn: (row) => row.rec.on_hand ?? 0,
        header: ({ column }) => (
          <DataGridColumnHeader title="On hand BRW" visibility column={column} />
        ),
        cell: ({ row }) =>
          row.original.rec.on_hand === null || row.original.rec.on_hand === undefined ? (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ) : (
            <PlanNumberButton
              value={fmtInt(row.original.rec.on_hand)}
              label="On hand in the site pool - open the stock by location"
              onClick={() => openDialog('on_hand', row.original)}
              disabled={!row.original.product_id}
            />
          ),
        size: 74,
        enableSorting: true,
        meta: { headerTitle: 'On hand BRW', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'incoming_spo',
        accessorFn: (row) => row.rec.incoming_spo ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="SPO" visibility column={column} />,
        // On the water. The figure opens the shipments themselves (plan 4.6) rather than
        // linking out to the SPO allocations list, which answered a wider question than the
        // one this cell asks and lost the product's own context on the way.
        cell: ({ row }) =>
          row.original.rec.incoming_spo === null || row.original.rec.incoming_spo === undefined ? (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ) : (
            <PlanNumberButton
              value={fmtInt(row.original.rec.incoming_spo)}
              label="SPO - open the shipments arriving"
              onClick={() => openDialog('spo', row.original)}
              disabled={!row.original.product_id}
            />
          ),
        size: 56,
        enableSorting: true,
        meta: { headerTitle: 'SPO (incoming)', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'outstanding_po',
        accessorFn: (row) => row.rec.outstanding_po ?? 0,
        // R13: "PO", not "PO outstanding" - the column already sits among the other supply
        // offsets, and the longer name was the only one on the row needing two lines.
        header: ({ column }) => <DataGridColumnHeader title="PO" visibility column={column} />,
        cell: ({ row }) =>
          row.original.rec.outstanding_po === null ||
          row.original.rec.outstanding_po === undefined ? (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ) : (
            <PlanNumberButton
              value={fmtInt(row.original.rec.outstanding_po)}
              label="PO - open what is already ordered"
              onClick={() => openDialog('po', row.original)}
              disabled={!row.original.product_id}
            />
          ),
        size: 56,
        enableSorting: true,
        meta: { headerTitle: 'PO (on order)', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'suggested',
        accessorFn: (row) => row.order_qty,
        header: ({ column }) => (
          <DataGridColumnHeader title="Suggested qty" visibility column={column} />
        ),
        // The number opens the ledger in a dialog (plan 4.6). A covered row is telling the
        // buyer they already have it, so the quantity it SUGGESTS is 0 - never the rounded
        // "buy anyway" offer, which the engine still stores on the row for the Covered-by-
        // stock view and for the decision the buyer records if they take it.
        cell: ({ row }) => {
          const line = row.original;
          if (!line.purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;
          const suggested = line.status === 'covered_by_stock' ? 0 : line.order_qty;
          return (
            <PlanNumberButton
              value={fmtInt(suggested)}
              label="Suggested qty - open how we got it"
              onClick={() => openDialog('suggested', line)}
            />
          );
        },
        size: 84,
        enableSorting: true,
        meta: { headerTitle: 'Suggested qty', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'net',
        accessorFn: (row) => row.net ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Net" visibility column={column} />,
        cell: ({ row }) => (
          <StopClick>
            <ExplainNumber value={fmtSigned(row.original.net)} title="Explain net">
              <NetDrill row={row.original} />
            </ExplainNumber>
          </StopClick>
        ),
        size: 96,
        enableSorting: true,
        meta: { headerTitle: 'Net', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'days_cover',
        accessorFn: (row) => row.days_cover ?? -1,
        header: ({ column }) => <DataGridColumnHeader title="Runway" visibility column={column} />,
        cell: ({ row }) => (
          <StopClick>
            <ExplainNumber
              value={row.original.days_cover === null ? EM_DASH : fmtInt(row.original.days_cover)}
              title="Explain runway"
            >
              <DaysCoverDrill row={row.original} />
            </ExplainNumber>
          </StopClick>
        ),
        size: 96,
        enableSorting: true,
        meta: { headerTitle: 'Runway', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'cost',
        accessorFn: (row) => decidedCost(row, decisions[row.id]) ?? -1,
        header: ({ column }) => <DataGridColumnHeader title="Total cost" visibility column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (!line.purchasable) return <span className="text-muted-foreground">{EM_DASH}</span>;
          const edit = edits[line.id];
          const decided = edit?.decision ?? decisions[line.id];
          const qty = decidedQty(line, decided) || line.order_qty;
          // A row waiting on a new price has no cost yet either - a figure here beside the
          // panel's own "Line cost -" would put two answers on one row.
          const asking =
            (edit?.priceMode ?? decided?.priceMode ?? 'use_last') === 'ask_new';
          const cost = asking ? null : decidedCost({ ...line }, { buy: qty });
          // A price we do not hold is never rendered as a number: it is the reason the line
          // cannot be weighed against a budget. A dash rather than the words, so the row does
          // not repeat "No price" twice; the title carries the detail.
          return cost === null ? (
            <span
              className="text-muted-foreground"
              title={
                asking
                  ? 'Waiting on a new price, so this line cannot be costed yet'
                  : 'No price on file, so this line cannot be costed'
              }
            >
              {EM_DASH}
            </span>
          ) : (
            <span className="tabular-nums">{fmtMoney(cost)}</span>
          );
        },
        size: 104,
        enableSorting: true,
        meta: { headerTitle: 'Total cost', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'reorder_level',
        // The STORED level, distinct from the `level` column below (the engine's
        // SUGGESTION for what it should be). The buyer's own figure wins when set;
        // AutoCount's master figure is the fallback so the column is never blank just
        // because nobody has set a level here yet.
        accessorFn: (row) => row.rec.reorder_level ?? row.rec.master_reorder_level ?? -1,
        header: ({ column }) => (
          <DataGridColumnHeader title="Reorder level" visibility column={column} />
        ),
        cell: ({ row }) => {
          const rec = row.original.rec;
          const hasOwn = rec.reorder_level !== null && rec.reorder_level !== undefined;
          const hasMaster =
            rec.master_reorder_level !== null && rec.master_reorder_level !== undefined;
          const level = hasOwn ? rec.reorder_level : hasMaster ? rec.master_reorder_level : null;
          const source = hasOwn ? 'buyer level' : hasMaster ? 'AutoCount master' : 'not set';
          return (
            <span className="tabular-nums" title={`Source: ${source}`}>
              {numCell(level)}
            </span>
          );
        },
        size: 82,
        enableSorting: true,
        meta: { headerTitle: 'Reorder level', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'reorder_qty',
        // AutoCount's own reorder quantity, uploaded (S13c) and read-only here - never
        // computed by the engine. Distinct from `suggested_quantity` in the `level` column,
        // which IS the engine's own arithmetic.
        accessorFn: (row) => row.rec.master_reorder_quantity ?? -1,
        header: ({ column }) => (
          <DataGridColumnHeader title="Reorder qty" visibility column={column} />
        ),
        cell: ({ row }) => (
          <span className="tabular-nums" title="AutoCount's own reorder quantity, as uploaded">
            {numCell(row.original.rec.master_reorder_quantity)}
          </span>
        ),
        size: 82,
        enableSorting: true,
        meta: { headerTitle: 'Reorder qty', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'decision',
        // A STATUS, not a control (plan 4.3, C6). Deciding happens in the expanded row,
        // where the numbers behind the decision are on screen; this cell answers the one
        // question the collapsed row can usefully answer - where is this up to - and carries
        // the mixture in words so reading down the column still says what was decided.
        header: ({ column }) => <DataGridColumnHeader title="Decision" visibility column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          // A legacy run's decisions are history: the panel still renders, every input in it
          // is dead, and the cell says so once rather than showing a pill that invites a
          // change nothing can accept.
          if (decisionsReadOnly) {
            return (
              <span
                className="text-2xs text-muted-foreground"
                data-testid={`decision-read-only-${line.id}`}
                title={readOnlyReason ?? 'Read only.'}
              >
                {readOnlyReason ?? 'Read only.'}
              </span>
            );
          }
          return <PlanDecisionPill reading={readingFor(line)} />;
        },
        size: 170,
        enableSorting: false,
        enableHiding: false,
        meta: { headerTitle: 'Decision', skeleton: <Skeleton className="h-5 w-32" /> },
      },
    ],
    [decisions, edits, runId, decisionsReadOnly, readOnlyReason,
     coverFor, priceFor, cheaperFor, levelFor, economicsFor, healthWindows,
     trendFor, trendSeriesMonths, groupByChannel, dynamicChannels,
     poFor,
     hasPhotoFor, photoStatus, onOpenPhoto,
     onRowEdit, onResetRow, openDialog, readingFor, channelTotals],
  );

  // The story order (see the header comment): each chapter leads with its result and is
  // followed by the columns that explain it. Deliberately NOT the definition order.
  //
  // Computed once at mount from `groupByChannel`/`dynamicChannels` (a run's grain is fixed
  // for its lifetime - 5.1 - so this never needs to react to either changing later); the
  // buyer's own drag-reorder still lives on in `setColumnOrder` from there.
  const [columnOrder, setColumnOrder] = useState<string[]>(() =>
    groupByChannel
      ? [
          'rank', 'sku',
          'suggested', 'reorder_level', 'reorder_qty',
          ...dynamicChannels.map((c) => `channel_${c}`),
          'on_hand', 'incoming_spo', 'outstanding_po',
          'decision',
          'cost', 'warehouse', 'net', 'days_cover',
        ]
      : [
          'rank', 'sku', 'warehouse',
          'suggested', 'reorder_level', 'reorder_qty',
          'project_need', 'retail_need',
          'on_hand', 'incoming_spo', 'outstanding_po',
          'decision',
          'cost', 'needed', 'net', 'days_cover',
        ],
  );
  // Off by default, one columns-menu click to bring back. `cost` joins them (plan 4.3): the
  // panel states the line cost where the buy is actually decided, so a column repeating it
  // on every row is a second place to read the same figure. `net`/`days_cover` are computed
  // steps rather than decisions, and `needed` restates the two channel columns beside it.
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({
    cost: false,
    net: false,
    days_cover: false,
    needed: false,
  });

  const table = useReactTable({
    columns,
    data: tableData,
    pageCount: Math.ceil(tableData.length / pagination.pageSize),
    getRowId: (row: PlanLine) => row.id,
    state: { pagination, sorting, columnOrder, columnVisibility, expanded },
    columnResizeMode: 'onChange',
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    onExpandedChange: setExpanded,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  // S4 (PLAN-scm-reorder-oi-feedback-1sep.md, AC-4.2): the FULL view a segment saves -
  // filters + sort + visible columns + column order - and the handler that restores all
  // four exactly when a segment is applied (or clears them for "No segment").
  //
  // S4 shortfall (PR #489 review round): the FULL Filters popover per G9 also means
  // the five FIXED dropdowns (status/decided/price/action/level) - they are ANDed
  // into `filtered` above and counted in the toolbar's `activeCount` beside the
  // recursive `filterGroup`, so a segment that left them out would not be "the full
  // view" the AC promises. Carried in `quick_filters`, opaque like `filters` itself.
  const visibleColumnIds = useMemo(
    () => columnOrder.filter((id) => columnVisibility[id] !== false),
    [columnOrder, columnVisibility],
  );
  const savedViewConfig = useMemo<SavedViewConfig>(
    () => ({
      filters: filterGroup,
      sort: sorting.map((s) => ({ id: s.id, desc: Boolean(s.desc) })),
      columns: visibleColumnIds,
      column_order: columnOrder,
      quick_filters: {
        status: statusFilter,
        decided: decidedFilter,
        price: priceFilter,
        action: actionFilter,
        level: levelFilter,
      },
    }),
    [filterGroup, sorting, visibleColumnIds, columnOrder,
     statusFilter, decidedFilter, priceFilter, actionFilter, levelFilter],
  );
  // B1 (PR #489 review round): the column layout the reader had BEFORE the first
  // segment ever applied this session - taken once, restored verbatim by "No
  // segment", so a segment (published-default ones apply automatically, AC-4.4)
  // never permanently overwrites what was there. Persistence itself is also
  // suppressed for as long as `segmentId` is set (`suppressPersist` below), so a
  // segment's columns are never written back as the reader's OWN saved layout in
  // the first place - the snapshot only covers restoring the on-screen state.
  const preSegmentColumnsRef = useRef<{
    order: string[];
    visibility: Record<string, boolean>;
  } | null>(null);

  const applySegment = useCallback(
    (view: SavedView | null) => {
      if (!view) {
        setSegmentId(null);
        setFilterGroup(null);
        // S4 shortfall: the quick filters are part of "the full view" the same way
        // `filterGroup` already is above - cleared unconditionally on "No segment",
        // the same rule `filterGroup` follows regardless of whether a segment was
        // ever applied this session.
        setStatusFilter('all');
        setDecidedFilter('all');
        setPriceFilter('all');
        setActionFilter('all');
        setLevelFilter('all');
        const snapshot = preSegmentColumnsRef.current;
        preSegmentColumnsRef.current = null;
        if (snapshot) {
          setColumnOrder(snapshot.order);
          setColumnVisibility(snapshot.visibility);
        }
        return;
      }
      // Snapshot BEFORE this segment's own columns overwrite the state - only on the
      // FIRST segment applied (switching straight from one segment to another must
      // not re-snapshot the segment we are leaving as if it were the personal layout).
      if (!preSegmentColumnsRef.current) {
        preSegmentColumnsRef.current = { order: columnOrder, visibility: columnVisibility };
      }
      setSegmentId(view.id);
      setFilterGroup(view.view.filters ?? null);
      setSorting(view.view.sort.map((s) => ({ id: s.id, desc: s.desc })));
      // S4 shortfall: restore the five fixed dropdowns the segment captured -
      // missing from an older segment (saved before this fix) falls back to "all",
      // the same default the dropdowns themselves start from.
      const quick = view.view.quick_filters ?? {};
      setStatusFilter(quick.status ?? 'all');
      setDecidedFilter(quick.decided ?? 'all');
      setPriceFilter(quick.price ?? 'all');
      setActionFilter(quick.action ?? 'all');
      setLevelFilter(quick.level ?? 'all');
      // Nit (PR #489 review round): restored unconditionally - a saved segment's own
      // `column_order` is always this grid's full leaf-column list (`savedViewConfig`
      // never saves an empty one), so the length guard only hid a real segment doing
      // nothing behind what looked like "no order to restore".
      setColumnOrder(view.view.column_order);
      if (view.view.columns.length) {
        const visible = new Set(view.view.columns);
        setColumnVisibility((prev) => {
          const next: Record<string, boolean> = { ...prev };
          for (const id of view.view.column_order.length ? view.view.column_order : Object.keys(prev)) {
            next[id] = visible.has(id);
          }
          return next;
        });
      }
    },
    [columnOrder, columnVisibility, setStatusFilter, setDecidedFilter],
  );

  /** Whether Expand all / Collapse all have anything to do (C3). A control that is always
   *  live tells the reader nothing about the state it would change. */
  const pageRows = table.getRowModel().rows;
  const anyCollapsed = pageRows.some((r) => !r.getIsExpanded());
  const anyExpanded = pageRows.some((r) => r.getIsExpanded());

  const statusOptions = useMemo(
    () => [
      { value: 'all', label: 'All statuses' },
      ...PLAN_LINE_STATUS_ORDER.map((s) => ({ value: s, label: PLAN_LINE_STATUS_LABEL[s] })),
    ],
    [],
  );

  // A plain element, NOT a component defined in the render body: that would be a new
  // component type on every render, so React would unmount the toolbar and the search
  // input would lose focus after each keystroke.
  const toolbar = (
    <CardHeader className="block">
      <DataGridListToolbar
        table={table}
        secondaryActions={secondaryActions}
        primaryAction={toolbarPrimary}
        leftActions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              mode="icon"
              className="h-8 w-8"
              onClick={() => table.toggleAllRowsExpanded(true)}
              disabled={!anyCollapsed}
              title="Expand all"
              aria-label="Expand all"
            >
              <ChevronsUpDown className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              mode="icon"
              className="h-8 w-8"
              onClick={() => table.toggleAllRowsExpanded(false)}
              disabled={!anyExpanded}
              title="Collapse all"
              aria-label="Collapse all"
            >
              <ChevronsDownUp className="size-4" />
            </Button>
            {/* S4: segments dropdown, beside Filters (AC-4.4) - never chips. */}
            <SavedViewsMenu
              listingKey={REORDER_PLAN_LINES_LISTING_KEY}
              currentViewId={segmentId}
              currentConfig={savedViewConfig}
              onApply={applySegment}
            />
          </div>
        }
        searchSlot={
          <ListSearchInput
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Search product, location, or supplier"
            className="w-full sm:w-64 md:w-80"
          />
        }
        filters={{
          kind: 'custom',
          active: [statusFilter, decidedFilter, priceFilter, actionFilter,
                   levelFilter].some((f) => f !== 'all') || countFilterConditions(filterGroup) > 0,
          activeCount: [statusFilter, decidedFilter, priceFilter, actionFilter,
                        levelFilter].filter((f) => f !== 'all').length
                        + countFilterConditions(filterGroup),
          content: (
            <div className="space-y-3">
              <p className="text-sm font-medium">Filters</p>
              <SearchableSelect
                value={statusFilter}
                onChange={setStatusFilter}
                options={statusOptions}
                placeholder="Status"
              />
              <SearchableSelect
                value={decidedFilter}
                onChange={setDecidedFilter}
                options={[
                  { value: 'all', label: 'Decided and undecided' },
                  { value: 'undecided', label: 'Still to decide' },
                  { value: 'decided', label: 'Already decided' },
                ]}
                placeholder="Decision"
              />
              <SearchableSelect
                value={priceFilter}
                onChange={setPriceFilter}
                options={[
                  { value: 'all', label: 'Every price answer' },
                  { value: 'zero_cost', label: PRICE_ADVICE_LABEL.zero_cost },
                  { value: 'no_history', label: PRICE_ADVICE_LABEL.no_history },
                  { value: 'unknown_age', label: PRICE_ADVICE_LABEL.unknown_age },
                  { value: 'stale', label: PRICE_ADVICE_LABEL.stale },
                  { value: 'moving', label: PRICE_ADVICE_LABEL.moving },
                  { value: 'recent', label: PRICE_ADVICE_LABEL.recent },
                  { value: 'none', label: 'No price information' },
                ]}
                placeholder="Suggested price"
              />
              <SearchableSelect
                value={actionFilter}
                onChange={setActionFilter}
                options={[
                  { value: 'all', label: 'Every suggested action' },
                  { value: 'buy', label: 'Includes a buy' },
                  { value: 'use_stock', label: 'Includes use stock' },
                  { value: 'use_po', label: 'Includes use PO (already ordered)' },
                ]}
                placeholder="Suggested action"
              />
              <SearchableSelect
                value={levelFilter}
                onChange={setLevelFilter}
                options={[
                  { value: 'all', label: 'Every level answer' },
                  { value: 'change', label: 'Level change suggested' },
                  { value: 'keep', label: 'Level already fits' },
                  { value: 'none', label: 'No level suggestion' },
                ]}
                placeholder="AutoCount level"
              />
              {/* S4 (PLAN-scm-reorder-oi-feedback-1sep.md): the dynamic filter builder,
                  reusable and fully recursive (AC-4.1) - additional to the five quick
                  filters above, for a question none of them name. */}
              <div className="space-y-2 border-t border-border pt-3">
                <p className="text-sm font-medium">Advanced filters</p>
                <DynamicFilterBuilder fields={filterFields} value={filterGroup} onChange={setFilterGroup} />
              </div>
            </div>
          ),
        }}
      />
    </CardHeader>
  );

  return (
    <DataGrid
      table={table}
      recordCount={tableData.length}
      isLoading={isLoading}
      standardToolbar={false}
      tableLayout={{
        width: 'fixed',
        columnsResizable: true,
        columnsPinnable: true,
        columnsMovable: true,
        columnsVisibility: true,
      }}
      // Saved column order/visibility belongs to the SCREEN, not to one plan: defaulted to
      // the pathname it keyed off `/scm/reorder/{run_id}`, so every plan a buyer opened
      // started from the defaults again and their own layout was never seen twice.
      listingKey={REORDER_PLAN_LINES_LISTING_KEY}
      // B1 (PR #489 review round): while a segment is driving the columns, never
      // write them back as the reader's own saved layout - see `applySegment` above.
      suppressPersist={Boolean(segmentId)}
      tableClassNames={{ edgeCell: 'px-5' }}
      onRowClick={(row) => {
        // The whole row toggles its decision panel (D1). Several may be open at once -
        // Expand all needs that, and there is no unsaved-edit prompt between rows because
        // the drafts live in a page-level map rather than inside the open panel.
        setExpanded((prev) => {
          const current = typeof prev === 'boolean' ? {} : prev;
          return { ...current, [row.id]: !current[row.id] };
        });
      }}
    >
      <Card>
        {toolbar}
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      {/* The one lightbox (plan 4.6). The Suggested-qty body is the existing ledger, built
          here because only this component holds the plan context it reads; its own cover
          toggles write to the DRAFT, never straight to the backend. */}
      <PlanRowDialog
        request={dialogRequest}
        onOpenChange={(o) => !o && setDialogRequest(null)}
        runId={runId ?? null}
        poReceipts={dialogRequest ? (poFor?.(dialogRequest.line) ?? []) : []}
        ledger={
          dialogRequest?.kind === 'suggested' ? (
            <OrderQtyLedger
              line={dialogRequest.line}
              decision={
                edits[dialogRequest.line.id]?.decision ?? decisions[dialogRequest.line.id]
              }
              cover={coverFor?.(dialogRequest.line) ?? NO_COVER}
              poReceipts={poFor?.(dialogRequest.line) ?? []}
              economicsFor={economicsFor}
              healthThresholds={healthThresholds}
              trend={trendFor?.(dialogRequest.line)}
              onDecide={(next) => onRowEdit?.(dialogRequest.line, { decision: next })}
              runId={runId ?? null}
              purchaseTrend={purchaseTrendFor?.(dialogRequest.line)}
              purchaseWindowMonths={purchaseTrendWindowMonths}
              purchaseTrendReady={purchaseTrendReady}
              onNeedPurchaseTrend={onOpenPurchaseTrend}
            />
          ) : null
        }
      />
    </DataGrid>
  );
}
