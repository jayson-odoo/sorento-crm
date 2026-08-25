'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import {
  CellContext,
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
import { ChevronDown, ChevronRight, Info, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { Skeleton } from '@/components/ui/skeleton';
import { EM_DASH, fmtDecimal, fmtInt, fmtMoney, fmtSigned } from '../../lib/format';
import { useLocationStock } from '../hooks/useReorderRun';
import type { LocationStockLocation } from '../services/reorderRunService';
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
  type PlanDecision,
  type PlanDecisionMap,
} from '../lib/planDecisions';
import { NO_COVER, type CoverProposal } from '../lib/coverPlan';
import {
  PRICE_ADVICE_LABEL,
  PRICE_ADVICE_SORT,
  type CheaperAlternative,
  type PriceAdvice,
} from '../lib/priceAdvice';
import { levelActionLabel, type LevelSuggestion } from '../lib/levelSuggestion';
import { poOffset, type PoReceipt } from '../lib/poCover';
import { PlanLevelCell } from './PlanLevelCell';
import { PlanMoqCell } from './PlanMoqCell';
import type { TrajectoryEntry } from '../lib/trajectory';
import type { ProductPurchaseTrend } from '../lib/purchaseTrend';
import { PlanTrendPopover } from './PlanTrendPopover';
import { PlanPurchaseTrendPopover } from './PlanPurchaseTrendPopover';
import { PlanHealthCell } from './PlanHealthCell';
import { PlanLineDecisionCell } from './PlanLineDecisionCell';
import { PlanPriceCell } from './PlanPriceCell';
import { PlanSupplierCell } from './PlanSupplierCell';
import {
  discontinueAdvice,
  marginOf,
  moqGap,
  moqGapNote,
  type ProductEconomics,
} from '../lib/productHealth';
import { PlanChecklistPopover } from './PlanChecklistPopover';
import { PlanDemandPopover } from './PlanDemandPopover';
import { ProductPhotoPopover, type ProductPhotoStatus } from './ProductPhotoPopover';
import {
  DaysCoverDrill,
  ExplainNumber,
  NetDrill,
} from './PlanExplainDrills';
import { OrderQtyLedger } from './PlanOrderQtyLedger';
import { ReorderExplanationDialog } from './ReorderExplanationDialog';
import type { ReorderRecommendation } from '../types/reorder.types';
import {
  groupPlanLinesByChannel,
  isGroupedLine,
  presentChannels,
  PLAN_CHANNEL_LABEL,
  type PlanChannel,
  type PlanChannelGroupMeta,
} from '../lib/planLineGrouping';
import type { ChannelTrendEntry } from '../lib/trajectory';

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
}: {
  value: number | null | undefined;
  title: string;
  tone?: 'exception';
}) {
  if (value === null || value === undefined) {
    return (
      <span className="text-2xs text-muted-foreground" title="Unavailable on a legacy plan">
        Unavailable
      </span>
    );
  }
  return (
    <span
      className={cn('tabular-nums', tone === 'exception' && value > 0 && 'text-scm-overstock')}
      title={title}
    >
      {fmtInt(value)}
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
  drill,
}: {
  value: number | null | undefined;
  confirmedNote?: string | null;
  /** The demand drill trigger for this cell (21 Aug follow-up: "where is the tooltip for
   *  me to open at project and retail" - the TOP product-grain row had none). `undefined`
   *  when no member recommendation exists to open one against. */
  drill?: React.ReactNode;
}) {
  if (value === null || value === undefined) {
    return (
      <span className="text-2xs text-muted-foreground" title="Unavailable on a legacy plan">
        Unavailable
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 tabular-nums">
      {fmtInt(value)}
      {confirmedNote ? (
        <span title={confirmedNote} className="text-muted-foreground/70">
          <Info className="size-3" aria-hidden />
        </span>
      ) : null}
      {drill}
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

/**
 * Whether this member has anything at all to show - either side of the channel split, or a
 * suggested qty. A location where every one of those reads zero adds nothing to the drill and
 * is noise on the way to the ones that do (captain, 19 Aug: "if 0 quantity why show here"). A
 * figure the run genuinely never populated (null/undefined) is NOT the same claim as a stated
 * zero - it counts as "nothing to show" here too, since a location with no stated data AND no
 * zero data still has nothing worth a drill row.
 *
 * N-1 (reviewer, 20 Aug): gated on the COLUMNS this panel actually renders - the three
 * `*_committed` splits and `order_qty` - not on `outstanding_sales`/`on_hand`/`incoming_spo`/
 * `outstanding_po`, which this rebuilt panel no longer shows at all (those moved to the LIVE
 * on-hand/SPO/available columns below, sourced from `useLocationStock`, not the frozen `rec`).
 * A member alive only via a frozen `outstanding_po` figure the panel never renders would
 * otherwise pass this gate and still show an all-dash row.
 */
function memberHasActivity(m: PlanLine): boolean {
  const figures = [
    m.rec.project_committed,
    m.rec.retail_committed,
    m.rec.unclassified_committed,
    m.order_qty,
  ];
  return figures.some((v) => typeof v === 'number' && v !== 0);
}

/** A live stock cell while the fetch is in flight, honest about not knowing yet. */
function liveCellSkeleton() {
  return <Skeleton className="ml-auto h-3 w-8" />;
}

/**
 * One LIVE figure for a member's warehouse, or an honest "nothing here" when the live
 * response never named this location at all (never a fabricated 0 - see the file's other
 * `numCell`, same reasoning). `negative` mirrors `CellStockTable`'s own tone for Available
 * (`app/(protected)/project-sales/fulfilment-planning/components/CellStockTable.tsx`):
 * signed and never clamped, coloured only when it actually runs below zero.
 */
function liveCell(value: number | null | undefined, negative?: boolean) {
  if (value === null || value === undefined) {
    return (
      <span className="text-muted-foreground" title="No live stock data for this location">
        {EM_DASH}
      </span>
    );
  }
  return (
    <span className={cn('tabular-nums', negative && value < 0 && 'text-destructive')}>
      {fmtInt(value)}
    </span>
  );
}

/**
 * The drill under a grouped PRODUCT row - the per-warehouse rows it summed, unsummed, one
 * per line (5.3/5.4: Location grain stays a read and drill view under Product grain;
 * nothing here is a decision).
 *
 * The Project / Retail / Unclass. columns read the FROZEN COMMITTED split
 * (`project_committed` etc.), the same figures the group row's channel columns read - NOT
 * the engine's `project_need` / `retail_need`. Those two are different facts with
 * misleading names here: `project_need` is only the CONFIRMED-for-buy leg (0 with no CS
 * decision), and `retail_need` is the netted sized buy, which swallows the project SHEET
 * leg - so a location whose demand was 100% project-class read "Retail 1,872" (captain,
 * SRT-H3005 BRW-BB, 20 Aug). There is no SO column: the split sums to the SO figure by
 * construction, so stating both said the same thing twice (captain, same day). Unclass. is
 * rendered only when some visible member actually carries a nonzero figure for it - the
 * captain's own words are "nothing should be unclassified", so a column that would read all
 * zeros is a column that should not exist here at all.
 *
 * On hand / Reserved / Free / SPO / Available are a SEPARATE chapter: LIVE, fetched from
 * the location-stock endpoint the moment the panel mounts (which is to say, on expand -
 * `GroupMembersPanel` only ever renders under an expanded row). This is the "fulfilment
 * planning" read the captain asked for - what the book says RIGHT NOW, not what the plan
 * committed to when it ran - joined onto each frozen member row by warehouse id (falling
 * back to warehouse code for a payload that predates the id). A member the live response
 * never named is an honest dash, not a fabricated zero.
 *
 * All-zero locations are filtered out (`memberHasActivity`) - UNLESS filtering would empty
 * the panel entirely, in which case every member is shown anyway: a group row only exists
 * because something summed to a nonzero suggested qty, so an all-zero-looking group is far
 * more likely a stale/legacy fixture than a real one, and a panel with nothing in it reads
 * as broken rather than as "nothing to see here".
 */
function GroupMembersPanel({
  group,
  runId,
  onOpenMember,
}: {
  group: PlanChannelGroupMeta;
  /** Threaded to each member's own demand popover (below), same as the ungrouped grid's
   *  SO/product cells already do. */
  runId: string | null;
  onOpenMember: (rec: ReorderRecommendation) => void;
}) {
  const active = group.members.filter(memberHasActivity);
  const visible = active.length > 0 ? active : group.members;
  const showUnclassified = visible.some((m) => (m.rec.unclassified_committed ?? 0) !== 0);
  const productId = group.members[0]?.product_id ?? null;
  const { data: liveStock, isLoading: liveLoading } = useLocationStock(productId, true);

  const liveByWarehouse = useMemo(() => {
    const byId = new Map<string, LocationStockLocation>();
    const byCode = new Map<string, LocationStockLocation>();
    for (const loc of liveStock?.locations ?? []) {
      if (loc.warehouse_id) byId.set(loc.warehouse_id, loc);
      if (loc.warehouse_code) byCode.set(loc.warehouse_code, loc);
    }
    return { byId, byCode };
  }, [liveStock]);

  function liveFor(m: PlanLine): LocationStockLocation | undefined {
    const id = m.warehouse_id ?? m.rec.warehouse_id ?? null;
    if (id) {
      const hit = liveByWarehouse.byId.get(id);
      if (hit) return hit;
    }
    const code = m.rec.warehouse_code;
    return code ? liveByWarehouse.byCode.get(code) : undefined;
  }

  return (
    <div className="border-t bg-muted/30 px-5 py-3">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground">
              <th className="max-w-28 px-2 py-1 text-left font-medium">Location</th>
              <th className="px-2 py-1 text-right font-medium">Project</th>
              <th className="px-2 py-1 text-right font-medium">Retail</th>
              {showUnclassified ? (
                <th className="px-2 py-1 text-right font-medium">Unclass.</th>
              ) : null}
              <th className="px-2 py-1 text-right font-medium">On hand</th>
              <th className="px-2 py-1 text-right font-medium">Reserved</th>
              <th className="px-2 py-1 text-right font-medium">Free</th>
              <th className="px-2 py-1 text-right font-medium">SPO</th>
              <th className="px-2 py-1 text-right font-medium">Available</th>
              <th className="px-2 py-1 text-right font-medium">Suggested qty</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((m) => {
              const live = liveFor(m);
              return (
                <tr
                  key={m.id}
                  className="cursor-pointer border-t border-border/60 hover:bg-muted/60"
                  onClick={() => onOpenMember(m.rec)}
                >
                  <td className="max-w-28 truncate px-2 py-1" title={m.warehouse}>
                    {m.warehouse}
                  </td>
                  {/* Captain's own preferred fix (20 Aug, live diagnosis): "put the icon
                      at project and retail separately then we don't need the open SOs".
                      A single popover on the Project cell used to carry the WHOLE
                      location's demand - order and retail mixed - so a captain reading a
                      Retail-chipped SO under the Project number reasonably concluded
                      retail was being counted as project. Each cell now opens ONLY its
                      own channel, and the header inside says which one. */}
                  <td className="px-2 py-1 text-right tabular-nums">
                    <span className="inline-flex items-center justify-end gap-0.5">
                      {numCell(m.rec.project_committed)}
                      <StopClick>
                        <PlanDemandPopover
                          runId={runId}
                          recId={m.id}
                          channel="project"
                          label={`Project demand at ${m.warehouse}`}
                        />
                      </StopClick>
                    </span>
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    <span className="inline-flex items-center justify-end gap-0.5">
                      {numCell(m.rec.retail_committed)}
                      <StopClick>
                        <PlanDemandPopover
                          runId={runId}
                          recId={m.id}
                          channel="retail"
                          label={`Retail demand at ${m.warehouse}`}
                        />
                      </StopClick>
                    </span>
                  </td>
                  {showUnclassified ? (
                    <td className="px-2 py-1 text-right tabular-nums">
                      <span className="inline-flex items-center justify-end gap-0.5">
                        {numCell(m.rec.unclassified_committed)}
                        <StopClick>
                          <PlanDemandPopover
                            runId={runId}
                            recId={m.id}
                            channel="unclassified"
                            label={`Unclassified demand at ${m.warehouse}`}
                          />
                        </StopClick>
                      </span>
                    </td>
                  ) : null}
                  <td className="px-2 py-1 text-right">
                    {liveLoading ? liveCellSkeleton() : liveCell(live?.on_hand)}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {liveLoading ? liveCellSkeleton() : liveCell(live?.reserved)}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {liveLoading ? liveCellSkeleton() : liveCell(live?.free)}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {liveLoading ? liveCellSkeleton() : liveCell(live?.spo_qty)}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {liveLoading ? liveCellSkeleton() : liveCell(live?.available, true)}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmtInt(m.order_qty)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {liveStock?.as_of ? (
        <p className="mt-2 text-2xs text-muted-foreground">
          Live stock as of {formatDateTimeInMalaysia(liveStock.as_of)}
        </p>
      ) : null}
    </div>
  );
}

export function PlanLinesGrid({
  lines,
  decisions,
  onDecide,
  onClear,
  coverFor,
  priceFor,
  cheaperFor,
  levelFor,
  onAmendLevel,
  onAmendMoq,
  poFor,
  trendFor,
  channelTrendFor,
  trendSeriesMonths = 24,
  purchaseTrendFor,
  purchaseTrendWindowMonths = 3,
  onOpenPurchaseTrend,
  hasPhotoFor,
  photoStatus = 'idle',
  onOpenPhoto,
  economicsFor,
  healthThresholds = { margin_floor_pct: 15, dead_turnover_months: 6 },
  onDecideLifecycle,
  staleAfterDays = 180,
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
  onDecide: (line: PlanLine, next: PlanDecision) => Promise<void> | void;
  /** Return a line to undecided. Separate from `onDecide` because undecided is the absence
   *  of a decision, not a fourth kind of one. */
  onClear: (line: PlanLine) => Promise<void> | void;
  /** What the plan suggests for a line: buy, cover from elsewhere, or a split of the two. */
  coverFor?: (line: PlanLine) => CoverProposal;
  /** What we last paid this line's supplier, and how old that is. Undefined = no opinion. */
  priceFor?: (line: PlanLine) => PriceAdvice | undefined;
  /** S13e: a materially cheaper supplier on the line's own shortlist, when one exists. */
  cheaperFor?: (line: PlanLine) => CheaperAlternative | null;
  /** S13f: the AutoCount level this run suggests for the line's product+location. */
  levelFor?: (line: PlanLine) => LevelSuggestion | undefined;
  /** S14: record (or withdraw, with null) the buyer's own level figure. */
  onAmendLevel?: (s: LevelSuggestion, amended: number | null) => Promise<void> | void;
  /** 20 Aug live test: record (or withdraw, with null) the buyer's own MoQ for a line -
   *  master data drifts and they should not have to wait for a re-run to fix it. Absent =
   *  read-only (the MOQ cell then only ever shows the frozen master figure). */
  onAmendMoq?: (line: PlanLine, moq: number | null) => Promise<void> | void;
  /** S15: the open PO lines already carrying this product to this warehouse. */
  poFor?: (line: PlanLine) => PoReceipt[];
  /** Is this product's demand sustaining or dying off, on this line's side. */
  trendFor?: (line: PlanLine) => TrajectoryEntry | undefined;
  /** How far back that trend's series reaches, for the "no orders dated in the last N
   *  months" line. Off the payload, never a literal on the screen. */
  trendSeriesMonths?: number;
  /** 5.3 follow-up (19-20 Aug): the order trend for one PRODUCT'S channel - drives the
   *  trend subline under each dynamic channel column on the grouped grid. Undefined when
   *  the caller has no opinion (ungrouped grid never reads this). */
  channelTrendFor?: (productId: string | null, channel: PlanChannel) => ChannelTrendEntry | undefined;
  /** The mirror of `trendFor`, on the buy side: what we have actually purchased. */
  purchaseTrendFor?: (line: PlanLine) => ProductPurchaseTrend | undefined;
  /** The window the purchase-trend sentence compares (months). */
  purchaseTrendWindowMonths?: number;
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
  /** Record (or withdraw) the buyer's keep-or-discontinue answer. Absent = read-only. */
  onDecideLifecycle?: (productId: string, decision: 'keep' | 'discontinue' | null) => Promise<void> | void;
  /** The age past which the business stops trusting a price. Shown, not implied. */
  staleAfterDays?: number;
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
   * line, with Project/Retail/Unclassified as dynamic COLUMNS on it instead of a row each -
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
  const [searchQuery, setSearchQuery] = useState('');
  const statusFilter: string = statusFilterProp ?? 'all';
  const setStatusFilter = (next: string) =>
    onStatusFilterChange?.(next === 'all' ? null : (next as PlanLineStatus));
  // Undecided/decided is its own filter, controllable the same way statusFilter is: the
  // reorder page's decision-progress tile drives it from outside, and every other caller
  // (the SCM simulation tab) leaves it uncontrolled and gets its own local toggle.
  const [ownDecidedFilter, setOwnDecidedFilter] = useState<'all' | 'undecided' | 'decided'>('all');
  const decidedFilter = decidedFilterProp ?? ownDecidedFilter;
  const setDecidedFilter = (next: string) =>
    (onDecidedFilterChange ?? setOwnDecidedFilter)(next as 'all' | 'undecided' | 'decided');
  // S14: one filter per suggestion column, so the buyer can work one question at a time
  // ("show me every stale price", "every level change", "project side only").
  const [sideFilter, setSideFilter] = useState<string>('all');
  const [priceFilter, setPriceFilter] = useState<string>('all');
  const [actionFilter, setActionFilter] = useState<string>('all');
  const [levelFilter, setLevelFilter] = useState<string>('all');
  // Row click opens the full derivation, as it did before the grid was rebuilt. The pager
  // steps through the rows in the order they are currently sorted and filtered, so "next"
  // means the next line the buyer is actually looking at.
  const [detailRec, setDetailRec] = useState<ReorderRecommendation | null>(null);

  const filtered = useMemo(() => {
    const needle = searchQuery.trim().toLowerCase();
    return lines.filter((l) => {
      if (statusFilter !== 'all' && l.status !== statusFilter) return false;
      if (decidedFilter === 'undecided' && decisions[l.id]) return false;
      if (decidedFilter === 'decided' && !decisions[l.id]) return false;
      if (sideFilter !== 'all' && (l.rec.segment ?? 'project') !== sideFilter) return false;
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
      if (!needle) return true;
      return (
        l.sku.toLowerCase().includes(needle) ||
        l.product_name.toLowerCase().includes(needle) ||
        l.warehouse.toLowerCase().includes(needle) ||
        l.supplier.name.toLowerCase().includes(needle)
      );
    });
  }, [lines, searchQuery, statusFilter, decidedFilter, sideFilter, priceFilter,
      actionFilter, levelFilter, decisions, priceFor, coverFor, levelFor, poFor]);

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

  // The channel COLUMN set (5.3 follow-up, 19-20 Aug): dynamic, off the whole run's rows
  // (`lines`, unfiltered - a column must not appear/disappear as the buyer searches or
  // filters), never hardcoded to two. Empty on the ungrouped grid, which has no channel
  // columns at all.
  const dynamicChannels = useMemo<PlanChannel[]>(
    () => (groupByChannel ? presentChannels(lines) : []),
    [groupByChannel, lines],
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
   * The Suggested-qty popover's own open/close bug (user feedback, 2026-08-12: "after I
   * tick, it shouldn't close the popup").
   *
   * `columns` below is recreated on every `decisions` change - it has to be, every OTHER
   * column reads `decisions` too - which recreates every inline cell FUNCTION along with
   * it. React identifies a functional component's fiber by (function reference, tree
   * position); a fresh function reference is a different component type as far as
   * reconciliation is concerned, so React unmounts and remounts the whole cell subtree on
   * every toggle, discarding the ledger Popover's own open state with it. Not a Radix bug -
   * confirmed by reproduction: the Popover trigger's DOM node is a literally different
   * element after a decision commit.
   *
   * The fix is a STABLE cell renderer for this one column, built once via `useCallback`
   * with an empty dependency list, reading its live inputs off a ref instead of closing
   * over them - so `columnDef.cell` for 'suggested' never changes identity and the Popover
   * survives a decision toggle, regardless of how often `columns` itself is rebuilt.
   */
  const suggestedQtyCellInputsRef = useRef({
    decisions, coverFor, poFor, economicsFor, healthThresholds, trendFor, onDecide,
  });
  suggestedQtyCellInputsRef.current = {
    decisions, coverFor, poFor, economicsFor, healthThresholds, trendFor, onDecide,
  };
  const renderSuggestedQtyCell = useCallback((ctx: CellContext<PlanLine, unknown>) => {
    const original = ctx.row.original;
    if (!original.purchasable) {
      return <span className="text-muted-foreground">{EM_DASH}</span>;
    }
    const {
      decisions: liveDecisions, coverFor: liveCoverFor, poFor: livePoFor,
      economicsFor: liveEconomicsFor, healthThresholds: liveHealthThresholds,
      trendFor: liveTrendFor, onDecide: liveOnDecide,
    } = suggestedQtyCellInputsRef.current;
    return (
      <span className="inline-flex items-center gap-1">
        <span className="tabular-nums">{fmtInt(original.order_qty)}</span>
        <StopClick>
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                title="How we got this qty"
                aria-label={`Explain order qty for ${original.sku}`}
                className="rounded-sm text-muted-foreground/70 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Info className="size-3.5" aria-hidden />
              </button>
            </PopoverTrigger>
            <PopoverPortal>
              <PopoverContent align="end" collisionPadding={8} className="w-80 p-0 text-sm">
                <OrderQtyLedger
                  line={original}
                  decision={liveDecisions[original.id]}
                  cover={liveCoverFor?.(original) ?? NO_COVER}
                  poReceipts={livePoFor?.(original) ?? []}
                  economicsFor={liveEconomicsFor}
                  healthThresholds={liveHealthThresholds}
                  trend={liveTrendFor?.(original)}
                  onDecide={(next) => liveOnDecide(original, next)}
                />
              </PopoverContent>
            </PopoverPortal>
          </Popover>
        </StopClick>
      </span>
    );
  }, []);

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
        size: 64,
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
                {/* 5.3: the chevron is purely a state indicator - the whole row already
                    toggles the drill open (`onRowClick`), same as any other row opens the
                    explanation dialog. */}
                {group && (
                  row.getIsExpanded() ? (
                    <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  ) : (
                    <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  )
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
        size: 240,
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
          // The per-warehouse rows a grouped row summed (5.3/5.4) - a read and drill panel,
          // never a decision surface. `DataGridTable` renders this full-width below any row
          // whose `getIsExpanded()` is true, same mechanism as `POIntakeLinesGrid`'s note
          // panel; only a group row (below) ever turns that on.
          expandedContent: (line: PlanLine) =>
            isGroupedLine(line) ? (
              <GroupMembersPanel
                group={line.__group}
                runId={runId ?? null}
                onOpenMember={(rec) => setDetailRec(rec)}
              />
            ) : null,
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
        size: 130,
        enableSorting: true,
        meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-20" /> },
      } satisfies ColumnDef<PlanLine>] : []),
      // The Order-type chip and the SO/Project/Retail/Unclassified columns are an
      // UNGROUPED-only chapter (5.3 follow-up, 19-20 Aug): grouped mode replaces all five
      // with the dynamic channel columns below - "instead of 1 column SO, 1 column
      // project, 1 column retail, it should be 2 columns" - so a channel is never both a
      // chip AND a column at once.
      ...(!groupByChannel ? [{
        id: 'side',
        accessorFn: (row) => row.rec.segment ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Order type" visibility column={column} />,
        // Project vs Retail, off the warehouse's segment. Never merged into one figure
        // anywhere on this screen (S13b): project demand is erratic and retail stable, so a
        // number spanning both describes neither. "Retail" not "Dealer" - the user's word.
        cell: ({ row }) => {
          const seg = row.original.rec.segment;
          if (!seg) return <span className="text-muted-foreground">{EM_DASH}</span>;
          return (
            <Badge variant={seg === 'project' ? 'info' : 'success'} appearance="light" size="sm">
              {seg === 'project' ? 'Project' : 'Retail'}
            </Badge>
          );
        },
        size: 100,
        enableSorting: true,
        meta: { headerTitle: 'Order type', skeleton: <Skeleton className="h-5 w-14" /> },
      } satisfies ColumnDef<PlanLine>] : []),
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
        size: 130,
        enableSorting: true,
        meta: { headerTitle: 'SO (needed)', skeleton: <Skeleton className="h-4 w-10" /> },
      } satisfies ColumnDef<PlanLine>,
      // The SO column's channel split (AC-F05 / AC-F07). Three DEMAND columns; the
      // supply columns below stay single shared facts of this product-location and
      // are deliberately NOT repeated per channel. Unclassified is visible and is
      // excluded from the actionable need until somebody classifies it.
      {
        id: 'project_need',
        accessorFn: (row) => row.rec.project_need ?? -1,
        header: ({ column }) => (
          <DataGridColumnHeader title="Project" visibility column={column} />
        ),
        cell: ({ row }) => (
          <span className="inline-flex items-center gap-0.5">
            <ChannelNeed
              value={row.original.rec.project_need}
              title="Confirmed unplaced Project Buy. Firm: Retail netting never reduces it"
            />
            {/* Same drill the per-location group panel already has (21 Aug follow-up:
                "where is the tooltip for me to open at project and retail") - the row
                IS one location at this grain, so no `scope` widening is needed. */}
            <StopClick>
              <PlanDemandPopover runId={runId ?? null} recId={row.original.id} channel="project" />
            </StopClick>
          </span>
        ),
        size: 90,
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
          <span className="inline-flex items-center gap-0.5">
            <ChannelNeed
              value={row.original.rec.retail_need}
              title="Retail-class need, after the normal netting of free supply"
            />
            <StopClick>
              <PlanDemandPopover runId={runId ?? null} recId={row.original.id} channel="retail" />
            </StopClick>
          </span>
        ),
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'Retail need', skeleton: <Skeleton className="h-4 w-10" /> },
      } satisfies ColumnDef<PlanLine>,
      {
        id: 'unclassified_need',
        accessorFn: (row) => row.rec.unclassified_need ?? -1,
        header: ({ column }) => (
          <DataGridColumnHeader title="Unclass." visibility column={column} />
        ),
        cell: ({ row }) => (
          <span className="inline-flex items-center gap-0.5">
            <ChannelNeed
              value={row.original.rec.unclassified_need}
              title="Demand whose sales order carries no demand class. Not in the actionable need"
              tone="exception"
            />
            <StopClick>
              <PlanDemandPopover
                runId={runId ?? null}
                recId={row.original.id}
                channel="unclassified"
              />
            </StopClick>
          </span>
        ),
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'Unclassified need', skeleton: <Skeleton className="h-4 w-10" /> },
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
              // Any one member's recommendation id opens the drill - the backend
              // resolves the product+run off it and unions every sibling recommendation
              // itself (`scope="product"`), so which member is "first" here is not a
              // decision that changes what the drill shows.
              const anyMemberId = line.__group.members[0]?.id;
              return (
                <ChannelColumnCell
                  value={value}
                  confirmedNote={confirmed}
                  drill={
                    anyMemberId ? (
                      <StopClick>
                        <PlanDemandPopover
                          runId={runId ?? null}
                          recId={anyMemberId}
                          channel={channel}
                          scope="product"
                        />
                      </StopClick>
                    ) : undefined
                  }
                />
              );
            },
            size: 110,
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
        header: ({ column }) => <DataGridColumnHeader title="On hand" visibility column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{numCell(row.original.rec.on_hand)}</span>,
        size: 90,
        enableSorting: true,
        meta: { headerTitle: 'On hand', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'incoming_spo',
        accessorFn: (row) => row.rec.incoming_spo ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="SPO" visibility column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums" title="On the water - incoming SPO quantity">
            {numCell(row.original.rec.incoming_spo)}
          </span>
        ),
        size: 80,
        enableSorting: true,
        meta: { headerTitle: 'SPO (incoming)', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'outstanding_po',
        accessorFn: (row) => row.rec.outstanding_po ?? 0,
        header: ({ column }) => (
          <DataGridColumnHeader title="PO outstanding" visibility column={column} />
        ),
        // The mirror of the SO cell's order-trend popup: who we bought it from, when, and
        // at what cost - the same interaction, on the buy side.
        cell: ({ row }) => (
          <StopClick>
            <PlanPurchaseTrendPopover
              qty={row.original.rec.outstanding_po}
              trend={purchaseTrendFor?.(row.original)}
              windowMonths={purchaseTrendWindowMonths}
              price={priceFor?.(row.original)}
              onOpen={onOpenPurchaseTrend}
            />
          </StopClick>
        ),
        size: 80,
        enableSorting: true,
        meta: { headerTitle: 'PO outstanding (on order)', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'suggested',
        accessorFn: (row) => row.order_qty,
        header: ({ column }) => (
          <DataGridColumnHeader title="Suggested qty" visibility column={column} />
        ),
        // Stable renderer (see `renderSuggestedQtyCell` above) - keeps the ledger Popover
        // open across a decision toggle.
        cell: renderSuggestedQtyCell,
        size: 120,
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
        size: 110,
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
        size: 110,
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
          const qty = decidedQty(line, decisions[line.id]) || line.order_qty;
          const cost = decidedCost({ ...line }, { buy: qty });
          // A price we do not hold is never rendered as a number: it is the reason the line
          // cannot be weighed against a budget. A dash rather than the words, so the row does
          // not repeat "No price" twice; the title carries the detail.
          return cost === null ? (
            <span className="text-muted-foreground" title="No price on file, so this line cannot be costed">
              {EM_DASH}
            </span>
          ) : (
            <span className="tabular-nums">{fmtMoney(cost)}</span>
          );
        },
        size: 120,
        enableSorting: true,
        meta: { headerTitle: 'Total cost', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'price',
        // Sorted by how urgent the price question is, not alphabetically: a line costing at
        // zero has to be reachable in one click from the top of the column.
        accessorFn: (row) => {
          const p = priceFor?.(row);
          return p ? PRICE_ADVICE_SORT[p.advice] : 99;
        },
        header: ({ column }) => (
          <DataGridColumnHeader title="Suggested price" visibility column={column} />
        ),
        cell: ({ row }) => (
          <StopClick>
            <PlanPriceCell
              unitCost={row.original.unit_cost}
              currency={row.original.currency}
              price={priceFor?.(row.original)}
              cheaper={cheaperFor?.(row.original) ?? null}
              staleAfterDays={staleAfterDays}
              purchasable={row.original.purchasable}
            />
          </StopClick>
        ),
        size: 150,
        enableSorting: true,
        meta: { headerTitle: 'Suggested price', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'supplier',
        accessorFn: (row) => row.supplier?.name ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Suggested supplier" visibility column={column} />
        ),
        cell: ({ row }) =>
          isGroupedLine(row.original) &&
          row.original.supplier?.code === '' &&
          row.original.__group.conflicts.has('supplier') ? (
            // Supplier is a PRODUCT fact carried through when every location agrees
            // (captain's 20 Aug ruling) - this dash means the group's own locations
            // genuinely disagree on supplier, a real conflict rather than a suppressed fact.
            // When no member carries a supplier at all (not a conflict), fall through to
            // `PlanSupplierCell`, whose own fallback already reads "No supplier linked to
            // this product" - the same data-gap wording an ungrouped row gets.
            <span className="text-muted-foreground" title="Varies by location - expand to see each one">
              {EM_DASH}
            </span>
          ) : (
            <StopClick>
              <PlanSupplierCell
                supplier={row.original.supplier ?? null}
                alternatives={row.original.alternatives ?? []}
                price={priceFor?.(row.original)}
                cheaper={cheaperFor?.(row.original) ?? null}
                purchasable={row.original.purchasable}
              />
            </StopClick>
          ),
        size: 180,
        enableSorting: true,
        meta: { headerTitle: 'Suggested supplier', skeleton: <Skeleton className="h-4 w-24" /> },
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
        size: 110,
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
        size: 100,
        enableSorting: true,
        meta: { headerTitle: 'Reorder qty', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'level',
        // The changes float to the top: a column of "still fits" is a column nobody reads.
        accessorFn: (row) => {
          const s = levelFor?.(row);
          if (!s) return 2;
          return levelActionLabel(s).changed ? 0 : 1;
        },
        header: ({ column }) => (
          <DataGridColumnHeader title="AutoCount level + qty" visibility column={column} />
        ),
        cell: ({ row }) => (
          <StopClick>
            <PlanLevelCell suggestion={levelFor?.(row.original)} onAmend={onAmendLevel} />
          </StopClick>
        ),
        size: 200,
        enableSorting: true,
        meta: { headerTitle: 'AutoCount level + qty', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'health',
        // The rows the buyer should re-question float up: discontinue candidates first,
        // then the margin problems, then the healthy book.
        accessorFn: (row) => {
          const econ = economicsFor?.(row);
          if (!econ) return 9;
          const margin = marginOf(row.unit_cost_base, econ, healthThresholds.margin_floor_pct);
          const advice = discontinueAdvice(econ, margin, trendFor?.(row), healthThresholds);
          if (advice?.consider) return 0;
          return { negative: 1, thin: 2, unknown: 3, healthy: 4 }[margin.tone];
        },
        header: ({ column }) => (
          <DataGridColumnHeader title="Product health" visibility column={column} />
        ),
        cell: ({ row }) => {
          const econ = economicsFor?.(row.original);
          if (!econ) return <span className="text-muted-foreground">{EM_DASH}</span>;
          const margin = marginOf(
            row.original.unit_cost_base, econ, healthThresholds.margin_floor_pct);
          const advice = discontinueAdvice(
            econ, margin, trendFor?.(row.original), healthThresholds);
          return (
            <StopClick>
              <PlanHealthCell
                margin={margin}
                advice={advice}
                econ={econ}
                onDecideLifecycle={onDecideLifecycle}
              />
            </StopClick>
          );
        },
        size: 170,
        enableSorting: true,
        meta: { headerTitle: 'Product health', skeleton: <Skeleton className="h-5 w-20" /> },
      },
      {
        id: 'moq',
        accessorFn: (row) => row.order_qty_inputs?.moq ?? -1,
        header: ({ column }) => <DataGridColumnHeader title="MOQ" visibility column={column} />,
        // The supplier's minimum, and - when it forces more than the need - the pump-up
        // with its sell-through odds. The engine floors at the MOQ silently; this column
        // is where the silence ends.
        cell: ({ row }) => {
          const line = row.original;
          const moq = line.order_qty_inputs?.moq ?? null;
          const masterMoq = line.order_qty_inputs?.master_moq ?? null;
          const isOverride = line.order_qty_inputs?.moq_is_override ?? false;
          // Only a buy/covered row carries a real recommendation for the write to land on;
          // a grouped row edits every member at once, so every member has to qualify.
          const editable = isGroupedLine(line)
            ? line.__group.members.every((m) => m.rec.type === 'buy' || m.rec.type === 'covered')
            : line.rec.type === 'buy' || line.rec.type === 'covered';
          if (isGroupedLine(line) && moq === null && line.__group.conflicts.has('moq')) {
            // MOQ is a PRODUCT fact carried through when every location agrees (captain's
            // 20 Aug ruling) - this dash means the group's own locations genuinely disagree,
            // a real conflict rather than a suppressed fact. When no member carries an MOQ
            // at all (not a conflict), fall through to the shared "no MOQ on file" branch
            // below - the same data-gap wording an ungrouped row gets.
            return (
              <span className="text-muted-foreground" title="Varies by location - expand to see each one">
                {EM_DASH}
              </span>
            );
          }
          if (!line.purchasable) {
            return (
              <span className="text-muted-foreground" title="No MOQ on file for this supplier">
                {EM_DASH}
              </span>
            );
          }
          const gap = moq !== null
            ? moqGap(
                // The PRE-round need: what the engine computed before the MOQ floor.
                line.rec.recommended_qty ?? line.order_qty,
                moq,
                Math.ceil(line.order_qty),
                economicsFor?.(line),
                healthThresholds.dead_turnover_months,
              )
            : null;
          return (
            <StopClick>
              <PlanMoqCell
                moq={moq}
                masterMoq={masterMoq}
                isOverride={isOverride}
                disabled={!editable}
                onChange={onAmendMoq ? (value) => onAmendMoq(line, value) : undefined}
                note={gap ? { text: moqGapNote(gap, fmtInt), warn: gap.verdict !== 'clears', title: gap.sentence } : null}
              />
            </StopClick>
          );
        },
        size: 140,
        enableSorting: true,
        meta: { headerTitle: 'MOQ', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'decision',
        // The merged "Suggested action" + "Decision" column (user markup, 2026-08-12): one
        // place to see the suggestion and take it. Wider than either of the two columns it
        // replaces used to be alone, since it now carries what both of them said.
        header: ({ column }) => <DataGridColumnHeader title="Decision" visibility column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          // S16 (captain, 21 Aug, 3rd time requested): the row IS the decision surface, on
          // every grain - grouped included. The ONE thing that still locks it is a legacy
          // run (`decisionsReadOnly`, stamped by the caller off `isLegacyRun` - its
          // decisions are history and nothing here may rewrite them).
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
          // A grouped (product-grain) row fans the SAME decision out to every member behind
          // it (`usePlanLines.decide`, mirroring `updateMoq`'s own fan-out) - its cell shows
          // the unanimous result, or `mixed` when the members disagree (5.3).
          const { decision, mixed } = isGroupedLine(line)
            ? groupDecisionState(line.__group.members.map((m) => m.id), decisions)
            : { decision: decisions[line.id], mixed: false };
          return (
            <StopClick>
              <PlanLineDecisionCell
                line={line}
                decision={decision}
                mixed={mixed}
                cover={coverFor?.(line) ?? NO_COVER}
                poReceipts={poFor?.(line) ?? []}
                onDecide={(next) => onDecide(line, next)}
                onClear={() => onClear(line)}
              />
            </StopClick>
          );
        },
        size: 340,
        enableSorting: false,
        enableHiding: false,
        meta: { headerTitle: 'Decision', skeleton: <Skeleton className="h-8 w-40" /> },
      },
    ],
    [decisions, onDecide, onClear, runId, decisionsReadOnly, readOnlyReason,
     coverFor, priceFor, cheaperFor, trendFor, channelTrendFor, groupByChannel, dynamicChannels,
     levelFor, onAmendLevel, onAmendMoq, poFor, purchaseTrendFor, purchaseTrendWindowMonths,
     onOpenPurchaseTrend, hasPhotoFor, photoStatus, onOpenPhoto, economicsFor, healthThresholds,
     onDecideLifecycle, staleAfterDays, renderSuggestedQtyCell, channelTotals],
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
          'rank', 'sku', 'warehouse',
          'suggested', ...dynamicChannels.map((c) => `channel_${c}`),
          'on_hand', 'incoming_spo', 'outstanding_po',
          'decision',
          'price', 'supplier', 'moq', 'cost',
          'reorder_level', 'reorder_qty', 'level', 'health',
          'net', 'days_cover',
        ]
      : [
          'rank', 'side', 'sku', 'warehouse',
          'suggested', 'needed', 'project_need', 'retail_need', 'unclassified_need',
          'on_hand', 'incoming_spo', 'outstanding_po',
          'decision',
          'price', 'supplier', 'moq', 'cost',
          'reorder_level', 'reorder_qty', 'level', 'health',
          'net', 'days_cover',
        ],
  );
  // Computed steps, not decisions: off by default, one columns-menu click to bring back.
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({
    net: false,
    days_cover: false,
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

  // Never a group row's own synthetic `rec` (5.3: it exists to feed the grid's cells, not
  // to be explained on its own) - Next/Prev inside the detail dialog must only ever land
  // on a real per-warehouse recommendation.
  const pageRecs = useMemo<ReorderRecommendation[]>(
    () =>
      table
        .getRowModel()
        .rows.filter((r) => !isGroupedLine(r.original))
        .map((r) => r.original.rec),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [table, tableData, pagination, sorting, expanded],
  );

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
        searchSlot={
          <div className="relative">
            <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search product, location, or supplier"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full ps-9 sm:w-64 md:w-80"
            />
            {searchQuery.length > 0 && (
              <Button
                mode="icon"
                variant="dim"
                className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
              >
                <X />
              </Button>
            )}
          </div>
        }
        filters={{
          kind: 'custom',
          active: [statusFilter, decidedFilter, sideFilter, priceFilter, actionFilter,
                   levelFilter].some((f) => f !== 'all'),
          activeCount: [statusFilter, decidedFilter, sideFilter, priceFilter, actionFilter,
                        levelFilter].filter((f) => f !== 'all').length,
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
                value={sideFilter}
                onChange={setSideFilter}
                options={[
                  { value: 'all', label: 'Both order types' },
                  { value: 'project', label: 'Project' },
                  { value: 'dealer', label: 'Retail' },
                ]}
                placeholder="Order type"
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
      tableClassNames={{ edgeCell: 'px-5' }}
      onRowClick={(row) => {
        // A group row has no single recommendation to explain (5.3) - clicking it opens
        // its per-warehouse drill instead of the explanation dialog.
        if (isGroupedLine(row)) {
          setExpanded((prev) => {
            const current = typeof prev === 'boolean' ? {} : prev;
            return { ...current, [row.id]: !current[row.id] };
          });
          return;
        }
        setDetailRec(row.rec);
      }}
    >
      <Card>
        {toolbar}
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <ReorderExplanationDialog
        rec={detailRec}
        open={!!detailRec}
        onOpenChange={(o) => !o && setDetailRec(null)}
        recs={pageRecs}
        totalCount={filtered.length}
        pageItemOffset={pagination.pageIndex * pagination.pageSize}
        onNavigate={setDetailRec}
      />
    </DataGrid>
  );
}
