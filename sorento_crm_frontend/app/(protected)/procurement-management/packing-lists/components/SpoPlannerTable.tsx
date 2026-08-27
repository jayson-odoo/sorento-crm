'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  Check,
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
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
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
import { cascadeTake, buildSpoScheduleMatrix, type SpoMatrixEntry } from './spoScheduleMatrix';
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
 *   1. The PO-takes drill now also names the PO's own date and supplier (`PoTakesDrillPopover`).
 *   2. A new "SO covered" drill answers "what SO am I covering" at the chosen location(s).
 *   3. Table/Schedule toggle, two schedule views (PO coverage, SO coverage) - product rows x
 *      weekly buckets, the loading plan's own visual precedent.
 *   4. The location control is a per-line SPLIT editor (`LocationSplitPopover`) - a line's SPO
 *      can land at more than one warehouse, each split writing its own allocation.
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

  useEffect(() => {
    // A fresh suggestion replaces whatever she had edited - "refresh" looks again, it does
    // not keep edits made against a now-stale suggestion (same rule ContainerRequestSection
    // applies to its own qty overrides).
    const next: Record<string, LineState> = {};
    for (const ln of suggestion.data?.lines ?? []) {
      // Every take ticked and the server's own demand walk pre-ticked: the default IS the
      // answer for most containers, and the ticks exist for the ones where it is not.
      const poTakeIds = ln.po_takes.map((t) => t.po_line_id);
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
      poTakeIds: ln.po_takes.map((t) => t.po_line_id),
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
  const toggleTake = (ln: SpoSuggestionLine, poLineId: string, on: boolean) => {
    const current = stateFor(ln);
    const poTakeIds = on
      ? [...current.poTakeIds, poLineId]
      : current.poTakeIds.filter((id) => id !== poLineId);
    const covered = poCoveredFor(ln, poTakeIds);
    // Derived from the TYPED figure, never from the clamped one on screen: clamping is a
    // view of what can be sent right now, and storing it destroyed the decision behind it.
    const qty = current.typedQty === null ? covered : Math.min(current.typedQty, covered);
    patch(ln, {
      poTakeIds,
      qty,
      soKeys: current.soKeys,
      splits: splitsFromTicks(ln, current.soKeys, qty),
    });
  };

  /** Tick the demand this SPO is for; the split follows (AC-G3, AC-G4). */
  const toggleCoverage = (ln: SpoSuggestionLine, key: string, on: boolean) => {
    const current = stateFor(ln);
    const soKeys = on
      ? [...current.soKeys, key]
      : current.soKeys.filter((k) => k !== key);
    patch(ln, { soKeys, splits: splitsFromTicks(ln, soKeys, current.qty) });
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

  /**
   * Ticked demand this SPO can only PART-cover - stated, never blocking (AC-G5's figures).
   *
   * The default walk does this on its last entry every time a container is smaller than the
   * demand behind it, which is most of them, so disabling Create for it would disable Create
   * for the normal case. What it is not allowed to do is stay quiet: the order is going to
   * be short, and the person sending it should read that here rather than discover it when
   * the container lands.
   */
  const partlyCovered = useMemo(() => {
    const out = new Map<string, { asked: number; covered: number; short: string[] }>();
    for (const ln of lines) {
      if (ln.cannot_convert) continue;
      const takes = coverageTakes(ln, soKeysFor(ln), qtyFor(ln));
      const short = takes
        .filter((t) => t.take > 0 && t.take < t.entry.qty)
        .map((t) => t.entry.document ?? t.entry.key);
      if (!short.length) continue;
      out.set(ln.shipment_line_id, {
        asked: takes.reduce((sum, t) => sum + t.entry.qty, 0),
        covered: takes.reduce((sum, t) => sum + t.take, 0),
        short,
      });
    }
    return out;
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

  /** Per warehouse, what the ticked demand accounts for - the same walk the cell reads. */
  const claimedFor = (ln: SpoSuggestionLine) => {
    const out = new Map<string, number>();
    for (const { entry, take } of coverageTakes(ln, soKeysFor(ln), qtyFor(ln))) {
      if (take <= 0) continue;
      const warehouse = entry.warehouse_id ?? ln.suggested_warehouse_id;
      if (!warehouse) continue;
      out.set(warehouse, (out.get(warehouse) ?? 0) + take);
    }
    return out;
  };

  const renderLocationCell = (ln: SpoSuggestionLine) => {
    const splits = splitsFor(ln);
    const qty = qtyFor(ln);
    const unassigned = unassignedFor(ln);
    const disabled = ln.cannot_convert || qty <= 0 || ln.location_options.length === 0;
    const label =
      splits.length === 0
        ? 'No location'
        : splits.length === 1
          ? ln.location_options.find((o) => o.warehouse_id === splits[0].warehouseId)?.warehouse_code ??
            'Choose'
          : `${splits.length} locations`;
    const mismatch = splitMismatch.has(ln.shipment_line_id);
    return (
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="flex items-center gap-1">
          <LocationSplitPopover
            line={ln}
            splits={splits}
            qty={qty}
            claimed={claimedFor(ln)}
            disabled={disabled}
            triggerLabel={label}
            mismatch={mismatch}
            onChange={(next) => setSplits(ln, next)}
          />
          {ln.location_options.length > 0 && !ln.cannot_convert ? (
            <SoCoveredDrillPopover line={ln} splits={splits} />
          ) : null}
        </div>
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
            <div className={ln.cannot_convert ? 'flex min-w-0 flex-col opacity-60' : 'flex min-w-0 flex-col'}>
              <span className="flex items-center gap-1 font-medium">
                <span className="truncate" title={ln.item_code ?? ''}>
                  {ln.item_code ?? EM_DASH}
                </span>
                {ln.reason ? (
                  <span className="shrink-0" title={ln.reason} aria-label={ln.reason}>
                    <Info className="size-3.5 text-muted-foreground" aria-hidden />
                  </span>
                ) : null}
              </span>
              <span className="truncate text-2xs text-muted-foreground" title={ln.product_name ?? ''}>
                {ln.product_name ?? EM_DASH}
                {ln.supplier_name ? ` · ${ln.supplier_name}` : ''}
              </span>
            </div>
          );
        },
        size: 230,
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
            <PoTakesDrillPopover
              title={ln.item_code ?? ln.product_name ?? 'This product'}
              takes={ln.po_takes}
              total={poCoveredFor(ln, ticked)}
              tickedIds={ticked}
              onToggle={(poLineId, on) => toggleTake(ln, poLineId, on)}
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
        cell: ({ row }) => <span className="tabular-nums text-muted-foreground">{fmtInt(row.original.on_hand)}</span>,
        size: 85,
        enableSorting: false,
        meta: { headerTitle: 'On hand (context)' },
      },
      {
        id: 'incoming_spo',
        header: ({ column }) => <DataGridColumnHeader title="Incoming SPO" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums text-muted-foreground">{fmtInt(row.original.incoming_spo)}</span>
        ),
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
            <SoCoverageDrillPopover
              title={ln.item_code ?? ln.product_name ?? 'This product'}
              coverage={ln.so_coverage}
              tickedKeys={keys}
              total={tickedQty(ln, keys, qtyFor(ln))}
              unassigned={Math.max(qtyFor(ln) - tickedQty(ln, keys, qtyFor(ln)), 0)}
              onToggle={(key, on) => toggleCoverage(ln, key, on)}
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
        cell: ({ row }) => renderLocationCell(row.original),
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Location' },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.shipment_line_id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const poMatrix = useMemo(() => {
    const entries: SpoMatrixEntry<SpoPoTake & { item_code: string | null }>[] = [];
    for (const ln of lines) {
      const takes = cascadeTake(ln.po_takes, qtyFor(ln));
      for (const t of takes) {
        entries.push({
          row_key: ln.item_code ? `item:${ln.item_code}` : `line:${ln.shipment_line_id}`,
          row_label: ln.item_code ?? ln.product_name ?? 'Unresolved',
          row_description: ln.product_name,
          date: t.expected_date,
          qty: t.takenQty,
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
      const keys = soKeysFor(ln);
      let left = qtyFor(ln);
      for (const entry of ln.so_coverage ?? []) {
        if (left <= 0) break;
        if (!keys.includes(entry.key)) continue;
        const take = Math.min(entry.qty, left);
        if (take <= 0) continue;
        left -= take;
        entries.push({
          row_key: ln.item_code ? `item:${ln.item_code}` : `line:${ln.shipment_line_id}`,
          row_label: ln.item_code ?? ln.product_name ?? 'Unresolved',
          row_description: ln.product_name,
          date: entry.required_date,
          qty: take,
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
          <p className="text-2xs text-muted-foreground">
            {suggestion.data?.shipment_status === 'draft'
              ? "Draft shipment - based on this draft's own packed quantities, not a real packing list yet."
              : 'What an open PO pulls this SPO up to, and where it should land.'}
          </p>
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
        {view === 'schedule' ? (
          <div className="flex items-center gap-2">
            <Label htmlFor="spo-schedule-mode" className="text-xs text-muted-foreground">
              Bucketed by
            </Label>
            <div className="w-52">
              <SearchableSelect
                id="spo-schedule-mode"
                value={scheduleView}
                onChange={(v) => setScheduleView(v as ScheduleView)}
                options={[
                  { value: 'po', label: "PO coverage (PO's expected date)" },
                  { value: 'so', label: "SO coverage (SO's needed date)" },
                ]}
              />
            </div>
          </div>
        ) : null}
        {splitMismatch.size > 0 ? (
          <span className="text-2xs font-medium text-destructive">
            {splitMismatch.size} line{splitMismatch.size === 1 ? '' : 's'} - location split does not add up
            to the SPO qty
          </span>
        ) : null}
        {overTicked.size > 0 ? (
          <span className="text-2xs font-medium text-destructive">
            {[...overTicked.values()].flat().join(', ')} - this container has nothing left
            for it. Untick it, or send more.
          </span>
        ) : null}
        {overTicked.size === 0 && partlyCovered.size > 0 ? (
          <span className="text-2xs text-muted-foreground">
            {[...partlyCovered.values()]
              .map(
                (p) =>
                  `${fmtInt(p.asked)} ticked, ${fmtInt(p.covered)} on this container - ${p.short.join(', ')} partly covered`,
              )
              .join('; ')}
          </span>
        ) : null}
      </div>

      {view === 'table' ? (
        <DataGrid
          table={table}
          recordCount={lines.length}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
          emptyMessage="This container has no line we hold a product for."
        >
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
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
              renderDrill={(cell, label) => (
                <>
                  <p className="text-xs font-medium">{label}</p>
                  <div className="space-y-1">
                    {cell.entries.map((e) => (
                      <div key={e.detail.po_line_id} className="flex items-center justify-between text-xs">
                        <span className="truncate" title={`${e.detail.po_number} - ${e.detail.supplier_name ?? EM_DASH}`}>
                          {e.detail.po_number}
                        </span>
                        <span className="tabular-nums">{fmtInt(e.qty)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
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
            renderDrill={(cell, label) => (
              <>
                <p className="text-xs font-medium">{label}</p>
                <div className="space-y-1">
                  {cell.entries.map((e, i) => (
                    <div key={`${e.detail.so_number}-${i}`} className="flex items-center justify-between text-xs">
                      <span className="truncate" title={e.detail.customer_name ?? ''}>
                        {e.detail.so_number ?? EM_DASH}
                      </span>
                      <span className="tabular-nums">{fmtInt(e.qty)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          />
        </div>
      )}
      <CardFooter className="justify-end text-2xs text-muted-foreground">
        {includedCount} of {lines.length} line{lines.length === 1 ? '' : 's'} will create an SPO
      </CardFooter>
    </Card>
  );
}

/** Earliest-first: which of this line's demand (at its CURRENT split locations) the SPO qty
 *  actually serves - the "what SO am I covering" ask, cascaded client-side against the live,
 *  edited qty (never a server round-trip per keystroke). */
function soTakesForLine(ln: SpoSuggestionLine, splits: SplitState[]) {
  const out: (SpoDemandLine & { takenQty: number; warehouse_code: string | null })[] = [];
  for (const split of splits) {
    if (!split.warehouseId || split.qty <= 0) continue;
    const location = ln.location_options.find((o) => o.warehouse_id === split.warehouseId);
    if (!location) continue;
    for (const t of cascadeTake(location.demand_lines, split.qty)) {
      out.push({ ...t, warehouse_code: location.warehouse_code });
    }
  }
  return out;
}

/**
 * Which POs this SPO draws from, oldest DOCUMENT first (Q8), each one tickable (AC-G1).
 *
 * The cell shows what the ticked ones cover and how many of them are on - untick the one
 * that is not really covering this container and the SPO falls to what the rest of them do.
 */
function PoTakesDrillPopover({
  title,
  takes,
  total,
  tickedIds,
  onToggle,
}: {
  title: string;
  takes: SpoPoTake[];
  total: number;
  tickedIds: string[];
  onToggle: (poLineId: string, on: boolean) => void;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-sm tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          title="Which PO covers this, oldest purchase order first"
        >
          {fmtInt(total)}
          <span className="text-2xs text-muted-foreground">
            {tickedIds.length} of {takes.length} POs
          </span>
          <Info className="size-3.5 text-muted-foreground" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-80 space-y-2 p-3">
          <p className="text-xs font-medium">{title} - covered by PO</p>
          <div className="space-y-1.5">
            {takes.map((t) => (
              <label
                key={t.po_line_id}
                className="flex items-center justify-between gap-2 text-xs"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <Checkbox
                    checked={tickedIds.includes(t.po_line_id)}
                    onCheckedChange={(checked) => onToggle(t.po_line_id, !!checked)}
                    aria-label={`Draw from ${t.po_number}`}
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-medium" title={t.po_number}>
                      {t.po_number}
                    </span>
                    <span className="block truncate text-2xs text-muted-foreground">
                      {t.supplier_name ?? EM_DASH}
                      {t.po_date ? ` · doc ${t.po_date}` : ''}
                      {t.expected_date ? ` · due ${t.expected_date}` : ''}
                    </span>
                  </span>
                </span>
                <span className="shrink-0 tabular-nums">{fmtInt(t.qty)}</span>
              </label>
            ))}
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/**
 * Which demand this SPO is being pointed at, tickable (Q4, AC-G3).
 *
 * Project rows first, then retail, in the order the server walked them - and the ticks it
 * pre-set are the answer for most containers. What no tick claims is stated as Unassigned
 * rather than quietly attached to the first order in the list.
 */
function SoCoverageDrillPopover({
  title,
  coverage,
  tickedKeys,
  total,
  unassigned,
  onToggle,
}: {
  title: string;
  coverage: SpoCoverageLine[];
  tickedKeys: string[];
  total: number;
  unassigned: number;
  onToggle: (key: string, on: boolean) => void;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-sm tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          title="Which demand this SPO is for - project by need-by date, then retail"
        >
          {fmtInt(total)}
          <Info className="size-3.5 text-muted-foreground" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-96 space-y-2 p-3">
          <p className="text-xs font-medium">{title} - what is this SPO for</p>
          <div className="space-y-1.5">
            {coverage.map((c) => (
              <label key={c.key} className="flex items-center justify-between gap-2 text-xs">
                <span className="flex min-w-0 items-center gap-2">
                  <Checkbox
                    checked={tickedKeys.includes(c.key)}
                    onCheckedChange={(checked) => onToggle(c.key, !!checked)}
                    aria-label={`Cover ${c.document ?? c.key}`}
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {c.document ?? EM_DASH}
                      <span className="ms-1 font-normal text-muted-foreground">
                        {c.kind === 'project' ? 'Project' : 'Retail'}
                      </span>
                    </span>
                    <span className="block truncate text-2xs text-muted-foreground">
                      {c.customer_name ?? EM_DASH}
                      {c.warehouse_code ? ` · ${c.warehouse_code}` : ''}
                      {c.required_date ? ` · needed ${c.required_date}` : ''}
                    </span>
                  </span>
                </span>
                <span className="shrink-0 tabular-nums">{fmtInt(c.qty)}</span>
              </label>
            ))}
          </div>
          {unassigned > 0 ? (
            <p className="border-t pt-2 text-2xs text-muted-foreground">
              {fmtInt(unassigned)} unassigned - free stock at the suggested warehouse.
            </p>
          ) : null}
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

function SoCoveredDrillTrigger({
  title,
  takes,
  total,
}: {
  title: string;
  takes: (SpoDemandLine & { takenQty: number; warehouse_code: string | null })[];
  total: number;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-sm tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          title="Which open SO demand this SPO will serve, earliest first"
        >
          {fmtInt(total)}
          <Info className="size-3.5 text-muted-foreground" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-96 space-y-2 p-3">
          <p className="text-xs font-medium">{title} - what SO am I covering</p>
          <div className="space-y-1.5">
            {takes.map((t, i) => (
              <div key={`${t.so_number}-${i}`} className="flex items-center justify-between gap-2 text-xs">
                <div className="min-w-0">
                  <div className="truncate font-medium" title={t.customer_name ?? ''}>
                    {t.so_number ?? EM_DASH}
                    {t.warehouse_code ? ` · ${t.warehouse_code}` : ''}
                  </div>
                  <div className="truncate text-2xs text-muted-foreground">
                    {t.customer_name ?? EM_DASH}
                    {t.agent_name ? ` · ${t.agent_name}` : ''}
                    {t.required_date ? ` · needed ${t.required_date}` : ''}
                  </div>
                </div>
                <span className="shrink-0 tabular-nums">{fmtInt(t.takenQty)}</span>
              </div>
            ))}
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/** Small icon-only trigger for the location cell (beside the split editor) - the same drill
 *  content as `SoCoveredDrillTrigger`, sized for a narrow row rather than a whole column. */
function SoCoveredDrillPopover({ line, splits }: { line: SpoSuggestionLine; splits: SplitState[] }) {
  const takes = soTakesForLine(line, splits);
  if (!takes.length) return null;
  const total = takes.reduce((sum, t) => sum + t.takenQty, 0);
  return (
    <SoCoveredDrillTrigger title={line.item_code ?? line.product_name ?? 'This product'} takes={takes} total={total} />
  );
}

/**
 * The location control (fourth doctrine-correction ask, "I can create SPO to multiple
 * locations"): zero, one or several destination rows, each an independent warehouse + qty,
 * validated to sum to the line's SPO qty. A popover rather than inline cells - a DataGrid row
 * has no room for an editable list of rows, and this mirrors the drill popovers already on
 * this table rather than inventing a new interaction.
 */
function LocationSplitPopover({
  line,
  splits,
  qty,
  claimed,
  disabled,
  triggerLabel,
  mismatch,
  onChange,
}: {
  line: SpoSuggestionLine;
  splits: SplitState[];
  qty: number;
  /** What the ticked demand accounts for, per warehouse - the rest of the split is free
   *  stock. Both parts land in the SAME warehouse whenever the unassigned share rides at a
   *  warehouse an order also needs, and then no quantity on this popover can tell them
   *  apart. */
  claimed: Map<string, number>;
  disabled: boolean;
  triggerLabel: string;
  mismatch: boolean;
  onChange: (splits: SplitState[]) => void;
}) {
  const options = line.location_options.map((o: SpoLocationOption) => ({
    value: o.warehouse_id,
    label: o.warehouse_code ?? o.warehouse_id,
  }));
  const total = splitsTotal(splits);

  const updateRow = (index: number, patch: Partial<SplitState>) => {
    const next = splits.map((s, i) => (i === index ? { ...s, ...patch } : s));
    onChange(next);
  };
  const removeRow = (index: number) => onChange(splits.filter((_, i) => i !== index));
  const addRow = () => {
    const remaining = Math.max(qty - total, 0);
    const used = new Set(splits.map((s) => s.warehouseId));
    const next = line.location_options.find((o) => !used.has(o.warehouse_id));
    onChange([...splits, { warehouseId: next?.warehouse_id ?? '', qty: remaining || 0 }]);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          className={mismatch ? 'h-8 w-full justify-start border-destructive text-destructive' : 'h-8 w-full justify-start'}
        >
          <span className="truncate">{triggerLabel}</span>
        </Button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" className="w-96 space-y-3 p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium">
              {line.item_code ?? line.product_name ?? 'This product'} - destinations
            </p>
            <span className={mismatch ? 'text-2xs font-medium text-destructive' : 'text-2xs text-muted-foreground'}>
              {fmtInt(total)} / {fmtInt(qty)} split
            </span>
          </div>

          {(() => {
            const unassigned = Math.max(
              qty - [...claimed.values()].reduce((sum, n) => sum + n, 0),
              0,
            );
            if (unassigned <= 0 && claimed.size === 0) return null;
            return (
              <div className="space-y-1 rounded-md bg-muted/50 p-2 text-2xs">
                <p className="font-medium">What this covers</p>
                {[...claimed.entries()].map(([warehouseId, claimedQty]) => {
                  const location = line.location_options.find(
                    (o) => o.warehouse_id === warehouseId,
                  );
                  return (
                    <p key={warehouseId} className="flex justify-between gap-2">
                      <span>{location?.warehouse_code ?? 'Chosen location'}</span>
                      <span className="tabular-nums">{fmtInt(claimedQty)}</span>
                    </p>
                  );
                })}
                {unassigned > 0 ? (
                  <p className="flex justify-between gap-2 text-muted-foreground">
                    <span>Unassigned</span>
                    <span className="tabular-nums">{fmtInt(unassigned)}</span>
                  </p>
                ) : null}
              </div>
            );
          })()}

          <div className="space-y-2">
            {splits.map((split, i) => {
              const location = line.location_options.find((o) => o.warehouse_id === split.warehouseId);
              return (
                <div key={i} className="space-y-1 rounded-md border p-2">
                  <div className="flex items-center gap-1.5">
                    <div className="min-w-0 flex-1">
                      <SearchableSelect
                        size="sm"
                        value={split.warehouseId}
                        options={options}
                        onChange={(v) => updateRow(i, { warehouseId: v || '' })}
                        placeholder="Choose location"
                      />
                    </div>
                    <Input
                      type="number"
                      min={0}
                      step={1}
                      className="h-8 w-20 tabular-nums"
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
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

export default SpoPlannerTable;
