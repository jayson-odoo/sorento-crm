'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  ExpandedState,
  Row,
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  Check,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Download,
  FileText,
  Info,
  LayoutGrid,
  LoaderCircle,
  Plus,
  RefreshCw,
  Table2,
  Trash2,
} from 'lucide-react';
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
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import {
  OnHandTable,
  PlanRowDialog,
  PoTakesPicker,
  SoCoveragePicker,
  SpoTabs,
  type PlanRowDialogKind,
} from '@/app/(protected)/scm/components/PlanRowDialog';
import { PlanNumberButton } from '@/app/(protected)/scm/components/PlanNumberButton';
import {
  useCreateSpo,
  useDeleteSpo,
  useDownloadSpoWorksheet,
  useSpoSuggestion,
} from '@/app/(protected)/scm/hooks/useFulfilment';
import type {
  SpoConfirmLine,
  SpoCoverageLine,
  SpoDemandLine,
  SpoLocationOption,
  SpoLocationSplit,
  SpoPoTake,
  SpoSuggestionLine,
} from '@/app/(protected)/scm/services/fulfilmentService';
import {
  cascadeTake,
  buildSpoScheduleMatrix,
  bucketKeyFor,
  type SpoMatrixBucket,
  type SpoMatrixEntry,
} from './spoScheduleMatrix';
import { SpoScheduleMatrixTable } from './SpoScheduleMatrixTable';

/**
 * The packing-list-to-SPO planner. One row per PACKED product, the loading-plan-style ranked
 * TABLE `ContainerRequestSection` renders for the container request, not a checkbox list. No
 * checkbox column, on purpose, mirroring `ContainerRequestSection.renderQtyCell`'s own rule:
 * the SPO-qty input IS the include/exclude decision, edited to 0 drops the line off the
 * confirm without hiding the row.
 *
 * DOCTRINE CORRECTION (captain, 21 Aug): "when there is PO, then we only can do SPO... it is
 * when we got PO, then we only can pull from the PO to form SPO." `suggested_qty` is now
 * `po_covered_qty` itself - what an open PO PULLS this SPO up to, never a deduction. A line
 * with nothing pullable (`cannot_convert`) is not selectable, same shape as the no-supplier
 * case; a partially-backed line stays selectable at `po_covered_qty`, with the uncovered
 * remainder (`no_po_qty`) named on `reason`. On hand / incoming SPO are CONTEXT columns only -
 * they never feed the qty. See `fulfilmentService.ts`'s own contract doc for the full story.
 *
 * Four asks from the same doctrine-correction message, all on this table:
 *   1. The PO-takes drill names the PO's own date and supplier, and opens as the shared
 *      lightbox (`PlanRowDialog kind="po_takes"`, R21).
 *   2. A "SO covered" drill answers "what SO am I covering", in the same lightbox.
 *   3. Table/Schedule toggle, two schedule views (PO coverage, SO coverage) - product rows x
 *      weekly buckets, the loading plan's own visual precedent.
 *   4. The location control is a per-line SPLIT editor (`LocationSplitPanel`) - a line's SPO
 *      can land at more than one warehouse, each split writing its own allocation. It lives in
 *      the row's EXPANDED area (R22, part 4): a list of editable rows does not fit a cell, and
 *      a popover put it behind a click, clipped at the viewport edge, away from its own row.
 */

const EM_DASH = '-';
const intFmt = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });
function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  return intFmt.format(value);
}
function fmtSigned(value: number): string {
  const s = intFmt.format(Math.abs(value));
  return value < 0 ? `-${s}` : s;
}

type SplitState = { warehouseId: string; qty: number };
type LineState = {
  qty: number;
  /** What the operator TYPED, held apart from what is currently sendable. Null until they
   *  type one, and the quantity is then a derived default that follows the ticked takes.
   *  Kept separate because the sendable figure is clamped to what is ticked, and writing
   *  that clamp back over the typed one is how unticking the only take stored 0 and the
   *  re-tick had nothing left to give back. */
  typedQty: number | null;
  splits: SplitState[];
  /** Which PO takes this line draws from. Every one, until somebody unticks one (AC-G1). */
  poTakeIds: string[];
  /** Which demand this SPO is pointed at - `SpoCoverageLine.key`s (Q4, AC-G3). */
  soKeys: string[];
};
type ScheduleView = 'po' | 'so';

/** A `po_takes` row occupied by ANOTHER SPO entirely (S5) - `qty: 0` is never this
 *  cascade's own take, so the row can never be ticked. */
function isTakenPo(t: SpoPoTake): boolean {
  return t.qty === 0 && t.taken_qty > 0;
}

/** Every `po_line_id` this line's take set could TICK - a taken row is never one of them
 *  (S5). The initial-tick default (every take, AC-G1) and a re-tick from the picker both
 *  read through this so neither can hand a taken row's id back into state. */
function tickablePoTakeIds(ln: SpoSuggestionLine): string[] {
  return ln.po_takes.filter((t) => !isTakenPo(t)).map((t) => t.po_line_id);
}

/** A `so_coverage` row occupied by ANOTHER SPO entirely (S5) - `qty: 0` is never tickable
 *  here either; `default_ticked` is already `false` for it server-side, so this only guards
 *  a re-tick handed back by the picker. */
function isTakenCoverage(c: SpoCoverageLine): boolean {
  return c.qty === 0 && c.taken_qty > 0;
}

/**
 * What the ticked takes cover - the ceiling on this line's SPO quantity (AC-G2).
 *
 * The cascade RE-RUN over the ticked lines, not the sum of the slices it took while every
 * line was ticked: with 100 packed against a 60-open PO and a 150-open one, the walk takes
 * 60 and 40, and unticking the first must ask the second for the whole 100 - it has it.
 * Summing the remaining slice answered 40 and quietly lost 60 pieces of cover that exist.
 * `open_qty` is what makes that computable here; the server does the same walk on Create.
 */
function poCoveredFor(ln: SpoSuggestionLine, takeIds: string[]): number {
  const available = ln.po_takes
    .filter((t) => takeIds.includes(t.po_line_id))
    .reduce((sum, t) => sum + (t.open_qty ?? t.qty), 0);
  return Math.min(available, ln.packed_qty);
}

/**
 * What the ticked demand actually GETS from this SPO - the one walk every figure on the
 * row is read off (browser pass 2, finding 3).
 *
 * There used to be two: the cell showed `min(sum of ticked need, qty)` and the banner
 * compared the raw `sum of ticked need` against the packed quantity. On a container packed
 * with 100 whose POs cover 19, the cell read 19 and the banner read "302 ticked against 100
 * packed" and disabled Create SPO - two answers to one question, and the wrong one was the
 * one holding the button.
 *
 * The walk: each ticked entry, in the server's own order, takes what it needs out of the
 * SPO quantity until there is none left. An entry that gets nothing is one this container
 * cannot serve at all, which is the only thing worth stopping the operator for.
 */
function coverageTakes(
  ln: SpoSuggestionLine,
  soKeys: string[],
  qty: number,
): { entry: SpoCoverageLine; take: number }[] {
  const out: { entry: SpoCoverageLine; take: number }[] = [];
  let left = Math.max(qty, 0);
  for (const entry of ln.so_coverage ?? []) {
    if (!soKeys.includes(entry.key)) continue;
    const take = Math.min(entry.qty, left);
    out.push({ entry, take: Math.max(take, 0) });
    left -= Math.max(take, 0);
  }
  return out;
}

/** What the ticks cover between them - what the SO-covered cell states. */
function tickedQty(ln: SpoSuggestionLine, soKeys: string[], qty: number): number {
  return coverageTakes(ln, soKeys, qty).reduce((sum, t) => sum + t.take, 0);
}

/**
 * The ticks the server proposed, narrowed to what this SPO can reach.
 *
 * The server walks its list against the PACKED quantity; the SPO is capped at what open
 * POs cover, which is often less. Ticking an order the container cannot serve on the very
 * first render is how the banner fired on a screen nobody had touched.
 */
function defaultSoKeys(ln: SpoSuggestionLine, qty: number): string[] {
  const proposed = (ln.so_coverage ?? []).filter((c) => c.default_ticked).map((c) => c.key);
  return coverageTakes(ln, proposed, qty)
    .filter((t) => t.take > 0)
    .map((t) => t.entry.key);
}

/**
 * Where the quantity lands, derived from the same walk (AC-G4).
 *
 * Each ticked piece of demand pulls what it needs, at ITS warehouse. What no tick claims is
 * free stock, and it goes to the suggested warehouse - labelled Unassigned on screen,
 * because nobody has said who it is for and pretending otherwise is how a container arrives
 * against the wrong order.
 */
function splitsFromTicks(
  ln: SpoSuggestionLine,
  soKeys: string[],
  qty: number,
): SplitState[] {
  if (ln.cannot_convert || qty <= 0) return [];
  const byWarehouse = new Map<string, number>();
  let claimed = 0;
  for (const { entry, take } of coverageTakes(ln, soKeys, qty)) {
    if (take <= 0) continue;
    const warehouse = entry.warehouse_id ?? ln.suggested_warehouse_id;
    if (!warehouse) continue;
    byWarehouse.set(warehouse, (byWarehouse.get(warehouse) ?? 0) + take);
    claimed += take;
  }
  const unassigned = qty - claimed;
  if (unassigned > 0 && ln.suggested_warehouse_id) {
    byWarehouse.set(
      ln.suggested_warehouse_id,
      (byWarehouse.get(ln.suggested_warehouse_id) ?? 0) + unassigned,
    );
  }
  return [...byWarehouse.entries()].map(([warehouseId, splitQty]) => ({
    warehouseId,
    qty: splitQty,
  }));
}

function splitsTotal(splits: SplitState[]): number {
  return splits.reduce((sum, s) => sum + (s.qty || 0), 0);
}

export function SpoPlannerTable({ shipmentId }: { shipmentId: string }) {
  const suggestion = useSpoSuggestion(shipmentId);
  const create = useCreateSpo(shipmentId);
  const deleteSpo = useDeleteSpo(shipmentId);
  const worksheet = useDownloadSpoWorksheet(shipmentId);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [view, setView] = useState<'table' | 'schedule'>('table');
  const [scheduleView, setScheduleView] = useState<ScheduleView>('po');

  const [state, setState] = useState<Record<string, LineState>>({});
  /** Which lines have their destinations open (R22). Closed to start with: the table is a
   *  ranked reading first, and every row open turns it into a form. */
  const [expanded, setExpanded] = useState<ExpandedState>({});
  /** The ONE lightbox this grid opens (R21): which figure was clicked, and on which line.
   *  Four dialogs mounted per row would be four Radix roots per row; the grid holds one and
   *  the cells only say what to put in it. */
  const [dialog, setDialog] = useState<
    { kind: PlanRowDialogKind; line: SpoSuggestionLine; bucket?: SpoMatrixBucket } | null
  >(null);

  useEffect(() => {
    // A fresh suggestion replaces whatever she had edited - "refresh" looks again, it does
    // not keep edits made against a now-stale suggestion (same rule ContainerRequestSection
    // applies to its own qty overrides).
    const next: Record<string, LineState> = {};
    for (const ln of suggestion.data?.lines ?? []) {
      // Every take ticked and the server's own demand walk pre-ticked: the default IS the
      // answer for most containers, and the ticks exist for the ones where it is not - a
      // TAKEN row (S5) is never one of them, no matter how it landed on `po_takes`.
      const poTakeIds = tickablePoTakeIds(ln);
      const soKeys = defaultSoKeys(ln, ln.suggested_qty);
      next[ln.shipment_line_id] = {
        qty: ln.suggested_qty,
        typedQty: null,
        poTakeIds,
        soKeys,
        splits: splitsFromTicks(ln, soKeys, ln.suggested_qty),
      };
    }
    setState(next);
  }, [suggestion.data]);

  const lines = useMemo(() => suggestion.data?.lines ?? [], [suggestion.data]);
  const alreadyConverted = suggestion.data?.already_converted ?? false;

  const stateFor = (ln: SpoSuggestionLine): LineState => {
    const held = state[ln.shipment_line_id];
    if (held) return held;
    const soKeys = defaultSoKeys(ln, ln.suggested_qty);
    return {
      qty: ln.suggested_qty,
      typedQty: null,
      poTakeIds: tickablePoTakeIds(ln),
      soKeys,
      splits: splitsFromTicks(ln, soKeys, ln.suggested_qty),
    };
  };
  const qtyFor = (ln: SpoSuggestionLine) => stateFor(ln).qty;
  const splitsFor = (ln: SpoSuggestionLine) => stateFor(ln).splits;
  const takeIdsFor = (ln: SpoSuggestionLine) => stateFor(ln).poTakeIds;
  const soKeysFor = (ln: SpoSuggestionLine) => stateFor(ln).soKeys;

  const patch = (ln: SpoSuggestionLine, next: Partial<LineState>) =>
    setState((prev) => ({
      ...prev,
      [ln.shipment_line_id]: { ...stateFor(ln), ...next },
    }));

  const setQty = (ln: SpoSuggestionLine, qty: number) => {
    const current = stateFor(ln);
    // The split follows the quantity, because it is derived from the ticks against it -
    // leaving a stale split behind is how Create SPO refuses with "the split has to add up"
    // on a screen where nothing looks wrong.
    patch(ln, {
      qty,
      typedQty: qty,
      splits: splitsFromTicks(ln, current.soKeys, qty),
    });
  };

  const setSplits = (ln: SpoSuggestionLine, splits: SplitState[]) => patch(ln, { splits });

  /**
   * Untick a take and the SPO falls to what the rest of them cover; tick it back and it
   * returns (AC-G2).
   *
   * ONE recompute for both directions. It used to take `min(current qty, covered)`, which
   * cannot go back up: unticking lowered the quantity, and re-ticking then held it at the
   * lowered figure while the PO-covers cell alone recovered - so the SPO qty, the SO
   * covered, the split and the Create gate all sat at the unticked values until a reload.
   *
   * A quantity the operator TYPED is theirs and survives, clamped to what is ticked. One
   * they never touched is a derived default and follows the takes.
   */
  const setTakeIds = (ln: SpoSuggestionLine, poTakeIds: string[]) => {
    // A taken row's checkbox is disabled in the picker, but its id is never trusted from the
    // caller either way (S5) - the same defensiveness `_keep` uses server-side.
    const tickable = new Set(tickablePoTakeIds(ln));
    const nextIds = poTakeIds.filter((id) => tickable.has(id));
    const current = stateFor(ln);
    const covered = poCoveredFor(ln, nextIds);
    // Derived from the TYPED figure, never from the clamped one on screen: clamping is a
    // view of what can be sent right now, and storing it destroyed the decision behind it.
    const qty = current.typedQty === null ? covered : Math.min(current.typedQty, covered);
    patch(ln, {
      poTakeIds: nextIds,
      qty,
      soKeys: current.soKeys,
      splits: splitsFromTicks(ln, current.soKeys, qty),
    });
  };

  /** Tick the demand this SPO is for; the split follows (AC-G3, AC-G4). */
  const setSoKeys = (ln: SpoSuggestionLine, soKeys: string[]) => {
    // Same defensiveness as `setTakeIds` (S5): a taken row's key is never trusted, however
    // it arrived.
    const takenKeys = new Set(
      (ln.so_coverage ?? []).filter(isTakenCoverage).map((c) => c.key),
    );
    const nextKeys = soKeys.filter((key) => !takenKeys.has(key));
    const current = stateFor(ln);
    patch(ln, { soKeys: nextKeys, splits: splitsFromTicks(ln, nextKeys, current.qty) });
  };

  const confirmLines: SpoConfirmLine[] = useMemo(
    () =>
      lines.map((ln) => {
        const qty = Math.max(qtyFor(ln), 0);
        const include = !ln.cannot_convert && qty > 0;
        const splits = include ? splitsFor(ln).filter((s) => s.warehouseId && s.qty > 0) : [];
        const location_splits: SpoLocationSplit[] = splits.map((s) => ({
          warehouse_id: s.warehouseId,
          qty: s.qty,
        }));
        return {
          shipment_line_id: ln.shipment_line_id,
          qty: include ? qty : 0,
          include,
          location_splits,
          po_take_ids: takeIdsFor(ln),
          so_line_ids: soKeysFor(ln),
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lines, state],
  );
  const includedCount = confirmLines.filter((l) => l.include).length;

  // A split must sum to exactly the line's SPO qty (the backend's own hard rule, mirroring
  // `allocation_suggestion_service.approve`) - checked here too so Create SPO is disabled
  // before the round-trip rather than after a 422.
  const splitMismatch = useMemo(() => {
    const bad = new Set<string>();
    for (const ln of lines) {
      const item = confirmLines.find((c) => c.shipment_line_id === ln.shipment_line_id);
      if (!item?.include) continue;
      const splits = item.location_splits ?? [];
      if (splits.length === 0) continue; // no location chosen - allowed, just no allocation
      const total = splits.reduce((sum, s) => sum + s.qty, 0);
      if (Math.abs(total - item.qty) > 1e-6) bad.add(ln.shipment_line_id);
    }
    return bad;
  }, [lines, confirmLines]);

  /**
   * Lines where the ticked demand asks for more than the container holds (AC-G5).
   *
   * The figures are shown rather than the ticks being silently clamped: the operator ticked
   * four orders for a container that can serve three, and which of them to drop is their
   * decision, not an arithmetic one.
   */
  const overTicked = useMemo(() => {
    const bad = new Map<string, string[]>();
    for (const ln of lines) {
      if (ln.cannot_convert) continue;
      // An order this SPO cannot serve AT ALL - the operator ticked past what the
      // container holds. Which one to drop is their decision, so it is named rather than
      // silently untitcked, and Create waits until they have made it (AC-G5).
      const starved = coverageTakes(ln, soKeysFor(ln), qtyFor(ln))
        .filter((t) => t.take <= 0)
        .map((t) => t.entry.document ?? t.entry.key);
      if (starved.length) bad.set(ln.shipment_line_id, starved);
    }
    return bad;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, state]);

  const renderQtyCell = (ln: SpoSuggestionLine) => (
    <Input
      type="number"
      min={0}
      max={poCoveredFor(ln, takeIdsFor(ln)) || undefined}
      step={1}
      className="h-8 w-24 tabular-nums"
      value={qtyFor(ln)}
      disabled={ln.cannot_convert}
      title="What the TICKED POs pull this SPO up to - cannot exceed it"
      onChange={(e) => {
        const raw = Math.max(0, Number(e.target.value) || 0);
        const next = Math.min(raw, poCoveredFor(ln, takeIdsFor(ln)));
        setQty(ln, next);
      }}
    />
  );

  /**
   * How much of this line's quantity no tick claims (AC-G4, Q4).
   *
   * It rides at the suggested warehouse, which is often the SAME warehouse a ticked order
   * needs - so the split reads "BRW 70" whether 40 of it is spoken for or none of it is,
   * and unticking an order moved no number on the screen at all. The figure has to be
   * stated, because it is the difference between goods promised to an order and free stock.
   */
  const unassignedFor = (ln: SpoSuggestionLine) =>
    Math.max(qtyFor(ln) - tickedQty(ln, soKeysFor(ln), qtyFor(ln)), 0);

  /**
   * What goes INSIDE the one lightbox, by which figure was clicked (R21).
   *
   * The two pickers are controlled and fetch-free: this table already holds `po_takes` and
   * `so_coverage`, and owns the walk that re-reads them when a tick changes, so the dialog
   * cannot hold a second opinion about the same rows. On hand and Incoming SPO are the
   * SHARED reorder / loading-plan bodies, which fetch their own rows on open.
   */
  const dialogBody = (kind: PlanRowDialogKind, ln: SpoSuggestionLine, bucket?: SpoMatrixBucket) => {
    switch (kind) {
      case 'po_takes': {
        // S4, AC-D3: opened from a schedule cell, the rows whose OWN date fell in that
        // clicked week are marked - the same week function the matrix bucketed them into,
        // so the picker cannot disagree with the cell that opened it.
        const bucketHits = bucket
          ? new Set(
              ln.po_takes
                .filter((t) => bucketKeyFor(t.expected_date) === bucket.key)
                .map((t) => t.po_line_id),
            )
          : undefined;
        return (
          <PoTakesPicker
            takes={ln.po_takes}
            tickedIds={takeIdsFor(ln)}
            onChange={(ids) => setTakeIds(ln, ids)}
            coveredQty={poCoveredFor(ln, takeIdsFor(ln))}
            packedQty={ln.packed_qty}
            bucketHits={bucketHits}
          />
        );
      }
      case 'so_coverage': {
        const bucketHits = bucket
          ? new Set(
              (ln.so_coverage ?? [])
                .filter((c) => bucketKeyFor(c.required_date) === bucket.key)
                .map((c) => c.key),
            )
          : undefined;
        return (
          <SoCoveragePicker
            coverage={ln.so_coverage ?? []}
            tickedKeys={soKeysFor(ln)}
            onChange={(keys) => setSoKeys(ln, keys)}
            unassigned={unassignedFor(ln)}
            // Take per row off the SAME walk the cell, the split and the banner read, so
            // the dialog cannot say one thing while the row says another.
            takes={Object.fromEntries(
              coverageTakes(ln, soKeysFor(ln), qtyFor(ln)).map((t) => [t.entry.key, t.take]),
            )}
            bucketHits={bucketHits}
          />
        );
      }
      case 'on_hand':
        return <OnHandTable productId={ln.product_id} />;
      case 'spo':
        return <SpoTabs supplierId={ln.supplier_id ?? ''} productId={ln.product_id} />;
      default:
        return null;
    }
  };

  /** A line nothing can be sent for has nowhere to send it, so it does not open (R22). */
  const cannotSplit = (ln: SpoSuggestionLine) =>
    ln.cannot_convert || qtyFor(ln) <= 0 || ln.location_options.length === 0;

  /**
   * The Location cell is now a chevron, not an editor (R22, AC-G4).
   *
   * The destinations are an editable LIST of rows, and a DataGrid cell has no room for one -
   * it lived in a popover, which put an editing surface behind a click, clipped it at the
   * viewport edge and could not be read beside the row it belongs to. The row expands
   * instead: same rows, full width, and the cell keeps the reading it always had (where it
   * lands, and how much of it nobody has claimed).
   */
  const renderLocationCell = (ln: SpoSuggestionLine, row: Row<SpoSuggestionLine>) => {
    const splits = splitsFor(ln);
    const unassigned = unassignedFor(ln);
    const disabled = cannotSplit(ln);
    const label =
      splits.length === 0
        ? 'No location'
        : splits.length === 1
          ? ln.location_options.find((o) => o.warehouse_id === splits[0].warehouseId)?.warehouse_code ??
            'Choose'
          : `${splits.length} locations`;
    const mismatch = splitMismatch.has(ln.shipment_line_id);
    const expanded = row.getIsExpanded();
    return (
      <div className="flex min-w-0 flex-col gap-0.5">
        {disabled ? (
          <span className="truncate text-muted-foreground">{label}</span>
        ) : (
          <button
            type="button"
            aria-expanded={expanded}
            title="Where this SPO lands"
            onClick={() => row.toggleExpanded()}
            className={
              mismatch
                ? 'inline-flex min-w-0 items-center gap-1 rounded-sm font-medium text-destructive underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40'
                : 'inline-flex min-w-0 items-center gap-1 rounded-sm underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40'
            }
          >
            {expanded ? (
              <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            ) : (
              <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            )}
            <span className="truncate">{label}</span>
          </button>
        )}
        {unassigned > 0 && !ln.cannot_convert ? (
          <span className="text-2xs text-muted-foreground">
            {fmtInt(unassigned)} unassigned
          </span>
        ) : null}
      </div>
    );
  };

  const columns = useMemo<ColumnDef<SpoSuggestionLine>[]>(
    () => [
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const ln = row.original;
          return (
            <div className={ln.cannot_convert ? 'flex min-w-0 items-center gap-1 opacity-60' : 'flex min-w-0 items-center gap-1'}>
              <span className="truncate font-medium" title={ln.item_code ?? ''}>
                {ln.item_code ?? EM_DASH}
              </span>
              {ln.reason ? (
                <span className="shrink-0" title={ln.reason} aria-label={ln.reason}>
                  <Info className="size-3.5 text-muted-foreground" aria-hidden />
                </span>
              ) : null}
            </div>
          );
        },
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'packed_qty',
        header: ({ column }) => <DataGridColumnHeader title="Packed" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.packed_qty)}</span>,
        size: 85,
        enableSorting: false,
        meta: { headerTitle: 'Packed' },
      },
      {
        id: 'po_covered',
        header: ({ column }) => <DataGridColumnHeader title="PO covers" column={column} />,
        cell: ({ row }) => {
          const ln = row.original;
          if (!ln.po_takes.length) {
            return <span className="tabular-nums text-muted-foreground">{fmtInt(0)}</span>;
          }
          const ticked = takeIdsFor(ln);
          return (
            <PlanNumberButton
              value={fmtInt(poCoveredFor(ln, ticked))}
              label="Which PO covers this, oldest purchase order first"
              onClick={() => setDialog({ kind: 'po_takes', line: ln })}
            />
          );
        },
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'PO covers' },
      },
      {
        id: 'on_hand',
        header: ({ column }) => <DataGridColumnHeader title="On hand" column={column} />,
        cell: ({ row }) => {
          const ln = row.original;
          return (
            <PlanNumberButton
              value={fmtInt(ln.on_hand)}
              label="Where this product is on hand right now"
              onClick={() => setDialog({ kind: 'on_hand', line: ln })}
              disabled={!ln.product_id}
            />
          );
        },
        size: 85,
        enableSorting: false,
        meta: { headerTitle: 'On hand (context)' },
      },
      {
        id: 'incoming_spo',
        header: ({ column }) => <DataGridColumnHeader title="Incoming SPO" column={column} />,
        cell: ({ row }) => {
          const ln = row.original;
          return (
            <PlanNumberButton
              value={fmtInt(ln.incoming_spo)}
              label="What is already on the water for the site pools"
              onClick={() => setDialog({ kind: 'spo', line: ln })}
              // The drill reads by supplier AND product; without both there is nothing to
              // ask for, so the figure stays plain text rather than opening an empty table.
              disabled={!ln.product_id || !ln.supplier_id}
            />
          );
        },
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Incoming SPO (context)' },
      },
      {
        id: 'suggested_qty',
        header: ({ column }) => <DataGridColumnHeader title="SPO qty" column={column} />,
        cell: ({ row }) => renderQtyCell(row.original),
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'SPO qty' },
      },
      {
        id: 'so_covered',
        header: ({ column }) => <DataGridColumnHeader title="SO covered" column={column} />,
        cell: ({ row }) => {
          const ln = row.original;
          if (ln.cannot_convert || !(ln.so_coverage ?? []).length) {
            return <span className="tabular-nums text-muted-foreground">{EM_DASH}</span>;
          }
          const keys = soKeysFor(ln);
          return (
            <PlanNumberButton
              value={fmtInt(tickedQty(ln, keys, qtyFor(ln)))}
              label="Which demand this SPO is for - project by need-by date, then retail"
              onClick={() => setDialog({ kind: 'so_coverage', line: ln })}
            />
          );
        },
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'SO covered' },
      },
      {
        id: 'location',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => renderLocationCell(row.original, row),
        size: 220,
        enableSorting: false,
        meta: {
          headerTitle: 'Location',
          // `DataGridTable` renders this full width under any row whose `getIsExpanded()`
          // is true, the same mechanism `PlanLinesGrid` uses for its per-warehouse panel.
          // Only ONE column may carry it (the table takes the first it finds), and this is
          // the one the chevron sits in.
          expandedContent: (ln: SpoSuggestionLine) => (
            <LocationSplitPanel
              line={ln}
              splits={splitsFor(ln)}
              qty={qtyFor(ln)}
              disabled={cannotSplit(ln)}
              mismatch={splitMismatch.has(ln.shipment_line_id)}
              onChange={(next) => setSplits(ln, next)}
            />
          ),
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.shipment_line_id,
    state: { expanded },
    onExpandedChange: setExpanded,
    getRowCanExpand: (row) => !cannotSplit(row.original),
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // Every line covered, or nothing packed for one: the chevrons are all disabled, so the
  // two toolbar buttons have nothing to open. A control that does nothing when pressed
  // reads as a broken screen, so it says why instead (R22, AC-G5).
  const nothingToExpand = table.getRowModel().rows.every((r) => !r.getCanExpand());

  const poMatrix = useMemo(() => {
    const entries: SpoMatrixEntry<SpoPoTake & { item_code: string | null }>[] = [];
    for (const ln of lines) {
      const rowKey = ln.item_code ? `item:${ln.item_code}` : `line:${ln.shipment_line_id}`;
      const rowLabel = ln.item_code ?? ln.product_name ?? 'Unresolved';
      const takes = cascadeTake(ln.po_takes, qtyFor(ln));
      for (const t of takes) {
        entries.push({
          row_key: rowKey,
          row_label: rowLabel,
          row_description: null,
          shipment_line_id: ln.shipment_line_id,
          date: t.expected_date,
          qty: t.takenQty,
          taken_qty: 0,
          detail: { ...t, item_code: ln.item_code },
        });
      }
      // S5 (AC-E8): every candidate line ANOTHER SPO already pulled from, on its own entry
      // (`qty: 0`) - whether or not THIS cascade also took from the same line, so a mixed
      // cell (both figures) and a taken-only cell (grey) both fall out of the same sum.
      for (const t of ln.po_takes) {
        if (!(t.taken_qty > 0)) continue;
        entries.push({
          row_key: rowKey,
          row_label: rowLabel,
          row_description: null,
          shipment_line_id: ln.shipment_line_id,
          date: t.expected_date,
          qty: 0,
          taken_qty: t.taken_qty,
          taken_by: t.taken_by,
          detail: { ...t, item_code: ln.item_code },
        });
      }
    }
    return buildSpoScheduleMatrix(entries);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, state]);

  // Bucketed by the TICKS, not by a cascade over the chosen locations (AC-G8): the ticks
  // are what the operator actually decided this SPO is for, and a schedule computed from
  // anything else would show a different answer to the one the drill above states.
  const soMatrix = useMemo(() => {
    const entries: SpoMatrixEntry<SpoDemandLine & { item_code: string | null }>[] = [];
    for (const ln of lines) {
      if (ln.cannot_convert) continue;
      const rowKey = ln.item_code ? `item:${ln.item_code}` : `line:${ln.shipment_line_id}`;
      const rowLabel = ln.item_code ?? ln.product_name ?? 'Unresolved';
      const keys = soKeysFor(ln);
      let left = qtyFor(ln);
      for (const entry of ln.so_coverage ?? []) {
        if (left <= 0) break;
        if (!keys.includes(entry.key)) continue;
        const take = Math.min(entry.qty, left);
        if (take <= 0) continue;
        left -= take;
        entries.push({
          row_key: rowKey,
          row_label: rowLabel,
          row_description: null,
          shipment_line_id: ln.shipment_line_id,
          date: entry.required_date,
          qty: take,
          taken_qty: 0,
          detail: {
            so_number: entry.document,
            customer_name: entry.customer_name,
            agent_name: null,
            required_date: entry.required_date,
            order_date: null,
            qty: take,
            item_code: ln.item_code,
          },
        });
      }
      // S5 (AC-E8): every piece of demand ANOTHER SPO already covers, on its own entry
      // (`qty: 0`) - see the PO loop above for why this is separate from the take loop.
      for (const entry of ln.so_coverage ?? []) {
        if (!(entry.taken_qty > 0)) continue;
        entries.push({
          row_key: rowKey,
          row_label: rowLabel,
          row_description: null,
          shipment_line_id: ln.shipment_line_id,
          date: entry.required_date,
          qty: 0,
          taken_qty: entry.taken_qty,
          taken_by: entry.taken_by,
          detail: {
            so_number: entry.document,
            customer_name: entry.customer_name,
            agent_name: null,
            required_date: entry.required_date,
            order_date: null,
            qty: 0,
            item_code: ln.item_code,
          },
        });
      }
    }
    return buildSpoScheduleMatrix(entries);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, state]);

  if (suggestion.isLoading) {
    return (
      <Card className="p-4">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="mt-3 h-40 w-full rounded-lg" />
      </Card>
    );
  }

  if (suggestion.isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-8 text-center">
        <p className="text-sm font-medium text-destructive">
          {suggestion.error instanceof Error
            ? suggestion.error.message
            : 'Failed to load the SPO planner.'}
        </p>
        <Button variant="outline" size="sm" onClick={() => suggestion.refetch()}>
          <RefreshCw className="size-4" />
          Try again
        </Button>
      </Card>
    );
  }

  if (alreadyConverted) {
    const existingSpos = suggestion.data?.existing_spos ?? [];
    const spoNumbers = existingSpos.map((s) => s.po_number ?? EM_DASH).join(', ');
    return (
      <Card className="p-4">
        {suggestion.data?.self_heal_note ? (
          <Alert variant="warning" size="sm" className="mb-3">
            <AlertDescription>{suggestion.data.self_heal_note}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold">SPO already created</h3>
            <p className="text-2xs text-muted-foreground">
              This packing list has already gone through Create SPO.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => worksheet.mutate(suggestion.data?.shipment_number ?? 'container')}
              disabled={worksheet.isPending}
            >
              {worksheet.isPending ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
              ) : (
                <Download className="size-4" aria-hidden />
              )}
              Download worksheet
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-destructive hover:text-destructive"
              onClick={() => setDeleteOpen(true)}
              disabled={!existingSpos.length}
            >
              <Trash2 className="size-4" aria-hidden />
              Delete SPO
            </Button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          {existingSpos.map((spo) => (
            <Badge key={spo.purchase_order_id} variant="secondary" size="sm">
              {spo.po_number ?? EM_DASH}
              {spo.supplier_name ? ` · ${spo.supplier_name}` : ''}
            </Badge>
          ))}
        </div>

        <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Confirm delete</AlertDialogTitle>
              <AlertDialogDescription>
                {existingSpos.length === 1
                  ? `This deletes ${spoNumbers}. `
                  : `This deletes ${existingSpos.length} SPOs: ${spoNumbers}. `}
                The planner can create them again, but the numbers are minted fresh - the ones
                deleted here are gone. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deleteSpo.isPending}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => deleteSpo.mutate(undefined, { onSuccess: () => setDeleteOpen(false) })}
                disabled={deleteSpo.isPending}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleteSpo.isPending ? 'Deleting...' : 'Delete'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </Card>
    );
  }

  if (!lines.length) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm font-medium">This container has no line we hold a product for.</p>
      </Card>
    );
  }

  return (
    <Card>
      {suggestion.data?.self_heal_note ? (
        <Alert variant="warning" size="sm" className="m-3 mb-0">
          <AlertDescription>{suggestion.data.self_heal_note}</AlertDescription>
        </Alert>
      ) : null}
      <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">SPO planner</h3>
        </div>
        <Button
          size="sm"
          onClick={() => create.mutate(confirmLines)}
          disabled={
            !includedCount || splitMismatch.size > 0 || overTicked.size > 0 || create.isPending
          }
        >
          {create.isPending ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
          ) : (
            <Check className="size-4" aria-hidden />
          )}
          Create SPO
        </Button>
      </CardHeader>

      <div className="flex flex-col gap-3 border-t border-border px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-md border border-input" role="group" aria-label="Planner view">
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
          {view === 'table' ? (
            <div className="flex items-center gap-1">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={nothingToExpand}
                title={nothingToExpand ? 'No line can be split yet' : undefined}
                // Only the lines that CAN be split. `toggleAllRowsExpanded(true)` ignores
                // `getRowCanExpand`, so it opened a split panel under every covered line too -
                // a panel with a disabled editor and nothing to do in it.
                onClick={() =>
                  table.setExpanded(
                    Object.fromEntries(
                      table
                        .getRowModel()
                        .rows.filter((r) => r.getCanExpand())
                        .map((r) => [r.id, true]),
                    ),
                  )
                }
              >
                <ChevronsUpDown className="size-4" aria-hidden />
                Expand all
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={nothingToExpand}
                title={nothingToExpand ? 'No line can be split yet' : undefined}
                onClick={() => table.setExpanded({})}
              >
                <ChevronsDownUp className="size-4" aria-hidden />
                Collapse all
              </Button>
            </div>
          ) : null}
        </div>
        <div className="flex min-w-0 items-center justify-end gap-2 sm:ms-auto">
          {/* S3 (review): these gate Create SPO in EITHER view, so they render in both - a
              disabled Create SPO with no reason on screen reads as broken. They sit before
              the schedule View select so the reason is read first. */}
          {splitMismatch.size > 0 ? (
            <span className="text-2xs text-end font-medium text-destructive">
              {splitMismatch.size} line{splitMismatch.size === 1 ? '' : 's'} - location split does not add up
              to the SPO qty
            </span>
          ) : null}
          {overTicked.size > 0 ? (
            <span className="text-2xs text-end font-medium text-destructive">
              {[...overTicked.values()].flat().join(', ')} - this container has nothing left
              for it. Untick it, or send more.
            </span>
          ) : null}
          {view === 'schedule' ? (
            <div className="flex items-center gap-2">
              <Label htmlFor="spo-schedule-mode" className="text-xs text-muted-foreground">
                View
              </Label>
              <div className="w-44">
                <SearchableSelect
                  id="spo-schedule-mode"
                  value={scheduleView}
                  onChange={(v) => setScheduleView(v as ScheduleView)}
                  options={[
                    { value: 'po', label: 'Purchase order' },
                    { value: 'so', label: 'Sales order' },
                  ]}
                />
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {view === 'table' ? (
        <DataGrid
          table={table}
          recordCount={lines.length}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
          emptyMessage="This container has no line we hold a product for."
        >
          <CardTable>
            <DataGridTable />
          </CardTable>
        </DataGrid>
      ) : scheduleView === 'po' ? (
        poMatrix.rows.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm font-medium">Nothing is pulled from an open PO yet.</p>
          </div>
        ) : (
          <div className="p-4">
            <SpoScheduleMatrixTable
              rowHeader="Product"
              rows={poMatrix.rows}
              buckets={poMatrix.buckets}
              cells={poMatrix.cells}
              onCellClick={(cell, bucket) => {
                // The clicked CELL's own first entry, not the row's: a row groups by item
                // code and can hold more than one shipment line, and the row's own
                // `shipment_line_id` names whichever line first CREATED the row - not
                // necessarily the one behind THIS cell (S4, AC-D2).
                const ln = lines.find((l) => l.shipment_line_id === cell.entries[0]?.shipment_line_id);
                if (ln) setDialog({ kind: 'po_takes', line: ln, bucket });
              }}
            />
          </div>
        )
      ) : soMatrix.rows.length === 0 ? (
        <div className="p-6 text-center">
          <p className="text-sm font-medium">No location has been chosen for any line yet.</p>
        </div>
      ) : (
        <div className="p-4">
          <SpoScheduleMatrixTable
            rowHeader="Product"
            rows={soMatrix.rows}
            buckets={soMatrix.buckets}
            cells={soMatrix.cells}
            onCellClick={(cell, bucket) => {
              const ln = lines.find((l) => l.shipment_line_id === cell.entries[0]?.shipment_line_id);
              if (ln) setDialog({ kind: 'so_coverage', line: ln, bucket });
            }}
          />
        </div>
      )}
      <CardFooter className="justify-end text-2xs text-muted-foreground">
        {includedCount} of {lines.length} line{lines.length === 1 ? '' : 's'} will create an SPO
      </CardFooter>

      {dialog ? (
        <PlanRowDialog
          kind={dialog.kind}
          productCode={dialog.line.item_code ?? dialog.line.product_name ?? EM_DASH}
          productName={dialog.line.product_name}
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
        >
          {dialogBody(dialog.kind, dialog.line, dialog.bucket)}
        </PlanRowDialog>
      ) : null}
    </Card>
  );
}

/**
 * Where a line's SPO lands (fourth doctrine-correction ask, "I can create SPO to multiple
 * locations"): zero, one or several destination rows, each an independent warehouse + qty,
 * validated to sum to the line's SPO qty.
 *
 * In the EXPANDED ROW, full width, not a popover (R22, AC-G4). An editable list of rows in a
 * popover is an editing surface behind a click: it clips at the viewport edge, it cannot be
 * read beside the row it belongs to, and it hid the one figure that decides whether Create
 * SPO is allowed. The row itself has the width for it.
 *
 * What it does NOT carry is the coverage list. Which orders this SPO is for is a decision of
 * its own and belongs in the SO covered lightbox (captain, 27 Aug); repeating it here made
 * two places to read the same walk, and they disagreed the moment one of them was stale.
 */
function LocationSplitPanel({
  line,
  splits,
  qty,
  disabled,
  mismatch,
  onChange,
}: {
  line: SpoSuggestionLine;
  splits: SplitState[];
  qty: number;
  disabled: boolean;
  mismatch: boolean;
  onChange: (splits: SplitState[]) => void;
}) {
  const options = line.location_options.map((o: SpoLocationOption) => ({
    value: o.warehouse_id,
    label: o.warehouse_code ?? o.warehouse_id,
  }));
  const total = splitsTotal(splits);
  /** The remainder, which is what the SPO has not been given a destination for. Negative
   *  means the rows ask for more than the SPO holds - the one state that has to shout. */
  const unassigned = qty - total;

  const updateRow = (index: number, patch: Partial<SplitState>) =>
    onChange(splits.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  const removeRow = (index: number) => onChange(splits.filter((_, i) => i !== index));
  const addRow = () => {
    const remaining = Math.max(qty - total, 0);
    const used = new Set(splits.map((s) => s.warehouseId));
    const next = line.location_options.find((o) => !used.has(o.warehouse_id));
    onChange([...splits, { warehouseId: next?.warehouse_id ?? '', qty: remaining || 0 }]);
  };

  if (disabled) {
    return (
      <div className="px-4 py-3 text-2xs text-muted-foreground">
        No destination can be chosen for this line.
      </div>
    );
  }

  return (
    <div className="bg-muted/30 px-4 py-3">
      {/* Its own scroll container, so the select + qty + remove row stays usable at 375px
          without widening the grid it sits inside. */}
      <ScrollArea>
        <div className="min-w-[30rem] space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium">
              {line.item_code ?? line.product_name ?? 'This product'} - destinations
            </p>
            <span
              className={
                mismatch ? 'text-2xs font-medium text-destructive' : 'text-2xs text-muted-foreground'
              }
            >
              {fmtInt(total)} / {fmtInt(qty)} split
            </span>
          </div>

          <div className="space-y-2">
            {splits.map((split, i) => {
              const location = line.location_options.find((o) => o.warehouse_id === split.warehouseId);
              return (
                <div key={i} className="space-y-1 rounded-md border bg-background p-2">
                  <div className="flex items-center gap-1.5">
                    <div className="min-w-0 flex-1">
                      <SearchableSelect
                        size="sm"
                        value={split.warehouseId}
                        options={options}
                        onChange={(v) => updateRow(i, { warehouseId: v || '' })}
                        placeholder="Choose location"
                        clearable
                      />
                    </div>
                    <Input
                      type="number"
                      min={0}
                      step={1}
                      className="h-8 w-20 tabular-nums"
                      aria-label={`Quantity for destination ${i + 1}`}
                      value={split.qty}
                      onChange={(e) => updateRow(i, { qty: Math.max(0, Number(e.target.value) || 0) })}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 shrink-0 text-muted-foreground hover:text-destructive"
                      aria-label="Remove destination"
                      onClick={() => removeRow(i)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                  {location ? (
                    <div className="grid grid-cols-4 gap-1 text-2xs text-muted-foreground">
                      <span>SO {fmtInt(location.outstanding_so)}</span>
                      <span>On hand {fmtInt(location.on_hand)}</span>
                      <span>SPO {fmtInt(location.incoming_spo)}</span>
                      <span title="available after this SPO">
                        After {fmtSigned(location.available + (split.qty || 0))}
                      </span>
                    </div>
                  ) : null}
                </div>
              );
            })}

            <div
              className={
                unassigned < 0
                  ? 'flex items-center justify-between gap-2 rounded-md border border-destructive px-2 py-1.5 text-xs font-medium text-destructive'
                  : 'flex items-center justify-between gap-2 rounded-md border border-dashed px-2 py-1.5 text-xs text-muted-foreground'
              }
            >
              <span>Unassigned</span>
              <span className="tabular-nums">{fmtInt(unassigned)}</span>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full"
            onClick={addRow}
            disabled={splits.length >= line.location_options.length}
          >
            <Plus className="size-4" aria-hidden />
            Add location
          </Button>
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
}

export default SpoPlannerTable;
