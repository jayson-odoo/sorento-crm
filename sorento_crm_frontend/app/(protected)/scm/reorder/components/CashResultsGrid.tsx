'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Clock,
  GripVertical,
  HelpCircle,
  Info,
  Search,
  ShoppingCart,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtDecimal, fmtInt, fmtMoney, fmtSigned, fmtSupplierCost } from '../../lib/format';
import { m8CashImpact, type M8PlanRow } from '../lib/planRow';
import { useExplainDemand, useExplainNet } from '../hooks/useDrills';
import { BuyOffsetsPanel } from './BuyOffsetsPanel';
import { PlanChecklistPopover } from './PlanChecklistPopover';
import { PlanDemandPopover } from './PlanDemandPopover';

/**
 * SCM M8 (slice C) - ONE table, two draggable sections (Within budget / Over
 * budget), inline per-line decisions, click-to-explain drills, and a row-anchored
 * inline edit popover. Prototype: driven entirely by mock rows + client state,
 * no backend. Rendered as a div-based grid (not DataGrid) so drag between the two
 * sections, per-cell popovers, and the section divider row can all co-exist -
 * that shape is outside what the react-table DataGrid wrapper hosts cleanly.
 */

/** Column template shared by header, data rows, and the section divider so every
 *  cell lines up. Order matches the alignment doc. The flexible columns (SKU,
 *  Warehouse, Supplier, Decision) carry `fr` weights so the grid spans the FULL
 *  container width instead of capping at a fixed total and leaving dead space on
 *  the right (M8-F11). The Decision column has a generous min so a confirmed line's
 *  full draft-PO number ("PO-DRAFT-0008") + the "PO created" badge never truncate.
 *  The budget control lives in the Within-budget section header (a separate flex
 *  row) and does NOT feed this grid template, so its placement no longer constrains
 *  the columns. */
// Two extra columns after Order qty: the reorder level and reorder quantity held on the
// PRODUCT record. The buyer reads the plan against what master data says, and where the two
// disagree is where the master record needs updating - so both are on the row rather than
// behind a drill.
const COLS =
  'minmax(0,32px) minmax(0,52px) minmax(180px,1.5fr) minmax(0,76px) minmax(0,150px) minmax(0,96px) minmax(0,96px) minmax(0,120px) minmax(0,88px) minmax(0,120px) minmax(110px,1fr) minmax(160px,1.4fr) minmax(230px,1.4fr)';
const MIN_TABLE_WIDTH = 1520;

/** Client-side sort/search over the visible rows (additive to the drag experience).
 *  'rank' asc IS the engine's default order - in that state (and only that state,
 *  with an empty search) the rows stay drag-orderable; any other sort or an active
 *  search disables drag so the two orderings never fight (see `dragDisabled`). */
type SortCol = 'rank' | 'order_qty' | 'cash' | 'days_cover' | 'warehouse' | 'supplier';
type SortDir = 'asc' | 'desc';

function compareRows(col: SortCol, a: M8PlanRow, b: M8PlanRow): number {
  switch (col) {
    case 'order_qty':
      return a.order_qty - b.order_qty;
    case 'cash':
      // Uncosted rows (null cash) sort to the low end regardless of direction basis.
      return (m8CashImpact(a) ?? -Infinity) - (m8CashImpact(b) ?? -Infinity);
    case 'days_cover':
      return (a.days_cover ?? -Infinity) - (b.days_cover ?? -Infinity);
    case 'warehouse':
      return a.warehouse.localeCompare(b.warehouse);
    case 'supplier':
      return a.supplier.name.localeCompare(b.supplier.name);
    case 'rank':
    default:
      return a.rank - b.rank;
  }
}

/** Sort a section's rows. Rank-ascending returns the array untouched so the default
 *  (engine) order - and the drag identity that rides on it - is preserved exactly. */
function sortSection(rows: M8PlanRow[], col: SortCol, dir: SortDir): M8PlanRow[] {
  if (col === 'rank' && dir === 'asc') return rows;
  const factor = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => factor * compareRows(col, a, b));
}

/** Case-insensitive substring match over SKU code + product name + supplier name. */
function matchesSearch(row: M8PlanRow, needle: string): boolean {
  if (!needle) return true;
  return (
    row.sku.toLowerCase().includes(needle) ||
    row.product_name.toLowerCase().includes(needle) ||
    row.supplier.name.toLowerCase().includes(needle)
  );
}

/** A clickable column header that toggles the client-side sort and shows the active
 *  ▲/▼ indicator. `align` mirrors the numeric right-aligned columns. */
function SortHeader({
  label,
  col,
  activeCol,
  dir,
  onSort,
  align = 'start',
}: {
  label: string;
  col: SortCol;
  activeCol: SortCol;
  dir: SortDir;
  onSort: (col: SortCol) => void;
  align?: 'start' | 'end';
}) {
  const isActive = activeCol === col;
  return (
    <button
      type="button"
      onClick={() => onSort(col)}
      title={`Sort by ${label}`}
      aria-label={`Sort by ${label}`}
      className={cn(
        'inline-flex items-center gap-1 rounded-sm uppercase tracking-wide hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        align === 'end' && 'justify-end',
        isActive && 'text-foreground',
      )}
    >
      <span>{label}</span>
      {isActive ? (
        dir === 'asc' ? (
          <ChevronUp className="size-3" aria-hidden />
        ) : (
          <ChevronDown className="size-3" aria-hidden />
        )
      ) : null}
    </button>
  );
}

export type M8RowDecision = 'accepted' | 'rejected' | null;

interface RowHandlers {
  /** Accept a within-budget row (pins it) / Fund an over-budget row (pins it). */
  onFund: (row: M8PlanRow) => void;
  /** Reject a row with a required reason (excludes it from the plan). */
  onReject: (row: M8PlanRow, reason: string) => void;
  /** Save an inline qty/supplier edit with a required reason. */
  onEdit: (row: M8PlanRow, patch: { order_qty: number; supplier_code: string }, reason: string) => void;
}

/** A right-aligned number with a click-to-explain info icon beside it. */
function ExplainNumber({
  value,
  children,
  title,
}: {
  value: string;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <span className="inline-flex items-center justify-end gap-1 tabular-nums">
      <span>{value}</span>
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            title={title}
            aria-label={title}
            className="text-muted-foreground/70 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
          >
            <Info className="size-3.5" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent align="end" collisionPadding={8} className="w-80 p-0 text-sm">
            {children}
          </PopoverContent>
        </PopoverPortal>
      </Popover>
    </span>
  );
}

function DrillHeader({ title }: { title: string }) {
  return <div className="border-b px-3 py-2 text-xs font-semibold">{title}</div>;
}

/** A short two-line skeleton for a drill that's still loading its working. */
function DrillLoading() {
  return (
    <div className="space-y-1.5 px-3 py-3" aria-label="Loading breakdown">
      <Skeleton className="h-3.5 w-full" />
      <Skeleton className="h-3.5 w-4/5" />
      <Skeleton className="h-3.5 w-3/5" />
    </div>
  );
}

/** Net drill - components + the open SOs behind committed (M8-A1). Fetched lazily
 *  from `explain-net` when the popover opens. */
/**
 * Why this row has no cash figure. Two different problems, fixed on two different screens:
 * nobody has ever priced the item, or it is priced in money we hold no rate for. One
 * label would send half of them to the wrong place.
 */
function costUnavailableReason(row: M8PlanRow): string {
  if (row.unit_cost === null) return 'No supplier cost on record';
  const code = (row.currency || '').trim().toUpperCase();
  return code
    ? `No exchange rate on file for ${code}, so this cost cannot be compared or funded`
    : 'No supplier cost on record';
}

/** The same fact as `costUnavailableReason`, short enough to sit in the cash cell. The
 *  full sentence stays on the cell's title. A bare dash here would read as zero cash. */
function costUnavailableLabel(row: M8PlanRow): string {
  if (row.unit_cost === null) return 'No cost';
  const code = (row.currency || '').trim().toUpperCase();
  return code ? `No ${code} rate` : 'No cost';
}

function NetDrill({ row }: { row: M8PlanRow }) {
  const { data: nb, isLoading, isError } = useExplainNet(row.id, true);
  if (isLoading) {
    return (
      <div>
        <DrillHeader title="Net breakdown" />
        <DrillLoading />
      </div>
    );
  }
  if (isError || !nb) {
    return (
      <div>
        <DrillHeader title={`Net = ${fmtSigned(row.net)}`} />
        <p className="px-3 py-2 text-xs text-muted-foreground">Couldn&apos;t load the net breakdown.</p>
      </div>
    );
  }
  return (
    <div>
      <DrillHeader title={`Net = ${fmtSigned(nb.net)}`} />
      <div className="space-y-1 px-3 py-2">
        <div className="flex justify-between">
          <span className="text-muted-foreground">on hand</span>
          <span className="tabular-nums">{fmtInt(nb.on_hand)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">+ on order</span>
          <span className="tabular-nums">{fmtInt(nb.on_order)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">- committed</span>
          <span className="tabular-nums">{fmtInt(nb.committed)}</span>
        </div>
      </div>
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Open sales orders
        </div>
        {nb.committed_sos.length ? (
          <div className="space-y-1">
            {nb.committed_sos.map((so) => (
              <div key={so.so_number} className="flex items-center justify-between gap-2 text-xs">
                <span className="font-medium">{so.so_number}</span>
                <span
                  className="min-w-0 flex-1 truncate text-muted-foreground"
                  title={so.customer_name ?? undefined}
                >
                  {so.customer_name ?? EM_DASH}
                </span>
                <span className="tabular-nums">{fmtInt(so.qty)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">No open sales orders committed.</div>
        )}
      </div>
    </div>
  );
}

/** Days cover drill - net + demand DOs + CV + the arithmetic (M8-A2/A3). Demand
 *  working is fetched lazily from `explain/demand` when the popover opens. */
function DaysCoverDrill({ row }: { row: M8PlanRow }) {
  const { data: demand, isLoading, isError } = useExplainDemand(
    row.product_id,
    row.warehouse_id,
    true,
  );
  // Headline avg/day + the "net / rate = days" arithmetic MUST use the SAME rate the
  // engine froze into `days_cover` (`net / forecast_daily_demand = days_cover`), not the
  // live `explain/demand` recompute - that runs a different window (and returns 0 for a
  // network SKU here) which would print "net / 0 = N". The live drill is evidence-only:
  // the DO list + coefficient of variation.
  const frozenRate = row.forecast_daily_demand;
  // No finite cover to show when there's a deficit OR no measurable frozen demand to
  // divide by - either way we must NOT divide by zero.
  const undefinedCover = row.days_cover === null || frozenRate == null || frozenRate <= 0;
  const isDeficit = row.net != null && row.net < 0;
  return (
    <div>
      <DrillHeader
        title={
          undefinedCover
            ? 'Runway = undefined (deficit / no measurable demand)'
            : `Runway = ${fmtInt(row.days_cover)} days`
        }
      />
      {undefinedCover ? (
        <p className="px-3 pt-2 text-xs text-muted-foreground">
          {isDeficit
            ? `Net is a deficit (${fmtSigned(row.net)}), so there is no positive cover to divide by demand - the buy exists to clear the shortfall.`
            : 'No measurable daily demand to divide the net by, so forward cover is undefined.'}
        </p>
      ) : null}
      <div className="space-y-1 px-3 py-2">
        <div className="text-2xs font-medium uppercase tracking-wide text-muted-foreground">Net</div>
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">on hand + on order - committed</span>
          <span className="tabular-nums">{fmtSigned(row.net)}</span>
        </div>
      </div>
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Demand (delivery orders that drove outflow)
        </div>
        {isLoading ? (
          <DrillLoading />
        ) : isError ? (
          <div className="mb-1.5 text-xs text-muted-foreground">Couldn&apos;t load the demand working.</div>
        ) : demand && demand.demand_dos.length ? (
          <div className="mb-1.5 space-y-1">
            {demand.demand_dos.slice(0, 6).map((doItem) => (
              <Link
                key={doItem.order_id}
                href={`/order-management/orders/${doItem.order_id}`}
                className="flex items-center justify-between gap-2 rounded-sm text-xs hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                title={`Open ${doItem.do_number}`}
              >
                <span className="font-medium hover:underline">{doItem.do_number}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {doItem.order_date ?? EM_DASH}
                </span>
                <span className="tabular-nums text-muted-foreground">{fmtInt(doItem.qty_out)} out</span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="mb-1.5 text-xs text-muted-foreground">No delivery orders in the window.</div>
        )}
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">avg / day (90-day window)</span>
          <span className="tabular-nums">{frozenRate != null ? fmtDecimal(frozenRate) : EM_DASH}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">Coefficient of variation</span>
          <span className="tabular-nums">
            {demand?.demand_cv != null ? fmtDecimal(demand.demand_cv, 2) : EM_DASH}
          </span>
        </div>
        <p className="mt-0.5 text-2xs text-muted-foreground">
          How spread out the weekly demand is - higher means less predictable.
        </p>
      </div>
      {!undefinedCover ? (
        <div className="border-t px-3 py-2 text-xs">
          <span className="tabular-nums">
            {fmtSigned(row.net)} / {fmtDecimal(frozenRate as number)} ={' '}
            <span className="font-semibold">{fmtInt(row.days_cover)} days</span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

/** Order qty drill - SS / ROP / order-up-to / rounded inputs (M8-A4), plus the
 *  reorder-point formula with its actual inputs (M8-F5). */
function OrderQtyDrill({
  row,
  onApplyOffsets,
}: {
  row: M8PlanRow;
  /** Stage an adjustment when the buyer declines one of the netted offsets. */
  onApplyOffsets: (qty: number, reason: string) => void;
}) {
  const q = row.order_qty_inputs;
  // A pooled buy is sized once for every location that shares stock, then split. Saying so
  // is the difference between "why 55" answering itself and the reader doing arithmetic
  // that cannot work.
  const alloc = row.rec.allocation ?? [];
  const pooled = alloc.length > 1;
  const demandRate = row.forecast_daily_demand;
  const leadDays = row.supplier.lead_time_days;
  const line = (label: string, value: number | null) => (
    <div className="flex justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value === null ? EM_DASH : fmtInt(value)}</span>
    </div>
  );
  return (
    <div>
      <DrillHeader title={`Order qty = ${fmtInt(q.rounded_qty)}`} />

      {/* What we need and what we PROPOSE to cover it with, before the policy arithmetic.
          This sits first because it is the part the buyer can disagree with: everything
          below it explains the target, this decides what is actually bought. */}
      <BuyOffsetsPanel row={row} onApply={onApplyOffsets} />

      <div className="space-y-1 px-3 py-2">
        {line('Safety stock', q.safety_stock)}
        {line('Reorder point', q.reorder_point)}
        {/* On a pooled row the order-up-to belongs to the POOL, not to this bin, so it is
            labelled as such. Otherwise the reader tries order-up-to minus this location's
            net and gets a number that is nowhere on the row. */}
        {line(pooled ? 'Order-up-to level (whole pool)' : 'Order-up-to level', q.order_up_to)}
        {line('MoQ', q.moq)}
        {line('Order multiple', q.order_multiple)}
        <div className="mt-1 flex justify-between border-t pt-1 text-xs font-medium">
          <span>{pooled ? 'This location\u2019s share' : 'Rounded order qty'}</span>
          <span className="tabular-nums">{fmtInt(q.rounded_qty)}</span>
        </div>
      </div>

      {pooled ? (
        <div className="border-t px-3 py-2">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
            Bought for the whole pool
          </div>
          <p className="text-2xs text-muted-foreground">
            One purchase covers {alloc.length} locations that share stock. It is sized once
            against the pool, then placed where the shortage is.
          </p>
          <div className="mt-1 space-y-0.5">
            {alloc.map((a) => (
              <div key={a.warehouse_code ?? String(a.qty)} className="flex justify-between text-2xs">
                <span
                  className={
                    a.warehouse_code === row.rec.warehouse_code
                      ? 'font-medium'
                      : 'text-muted-foreground'
                  }
                >
                  {a.warehouse_code ?? EM_DASH}
                </span>
                <span className="tabular-nums">{fmtInt(a.qty)}</span>
              </div>
            ))}
            <div className="mt-1 flex justify-between border-t pt-1 text-2xs font-medium">
              <span>Pool total</span>
              <span className="tabular-nums">
                {fmtInt(alloc.reduce((t, a) => t + (a.qty ?? 0), 0))}
              </span>
            </div>
          </div>
        </div>
      ) : null}
      {/* Where the daily rate comes from, and how many days of it are being bought. Both
          were invisible: the row showed "1.0/day" with no way to see the deliveries behind
          it, and an order-up-to with no way to see it was 51 days of cover. */}
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Order-up-to level
        </div>
        <p className="text-2xs text-muted-foreground">
          S = reorder point + demand rate x review period
        </p>
        <div className="mt-1 flex items-baseline justify-between gap-2 text-xs">
          <span className="tabular-nums text-muted-foreground">
            {q.reorder_point === null ? EM_DASH : fmtInt(q.reorder_point)} +{' '}
            {demandRate == null ? EM_DASH : fmtDecimal(demandRate)}/day x{' '}
            {fmtInt(row.rec.review_days ?? null)}d review
          </span>
          <span className="tabular-nums font-semibold">
            {q.order_up_to === null ? EM_DASH : fmtInt(q.order_up_to)}
          </span>
        </div>
        {row.rec.safety_days != null && row.rec.review_days != null ? (
          <p className="mt-1 text-2xs text-muted-foreground">
            {fmtInt(
              (row.rec.safety_days ?? 0) + (leadDays ?? 0) + (row.rec.review_days ?? 0),
            )}{' '}
            days of cover ({fmtInt(row.rec.safety_days)} safety + {fmtInt(leadDays)} lead +{' '}
            {fmtInt(row.rec.review_days)} review)
          </p>
        ) : null}
      </div>

      {demandRate != null && row.rec.demand_window_days ? (
        <div className="border-t px-3 py-2">
          <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
            Where the rate comes from
          </div>
          <p className="text-2xs text-muted-foreground">
            {fmtInt(demandRate * row.rec.demand_window_days)} units left this location over
            the last {fmtInt(row.rec.demand_window_days)} days, which averages{' '}
            {fmtDecimal(demandRate)} a day. Past deliveries, not the open orders.
          </p>
        </div>
      ) : null}

      {/* Reorder-point explain (M8-F5): the formula + the frozen inputs behind it. */}
      <div className="border-t px-3 py-2">
        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
          Reorder point
        </div>
        <p className="text-2xs text-muted-foreground">
          ROP = safety stock + demand rate x lead time
        </p>
        <div className="mt-1 flex items-baseline justify-between gap-2 text-xs">
          <span className="tabular-nums text-muted-foreground">
            {/* One decimal, so the sum shown equals the answer shown. Rounding safety stock
                to a whole number printed "7 + 1.0/day x 14d = 22", which is off by one and
                reads as a broken calculation. */}
            {q.safety_stock === null ? EM_DASH : fmtDecimal(q.safety_stock)} +{' '}
            {demandRate == null ? EM_DASH : fmtDecimal(demandRate)}/day x{' '}
            {fmtInt(leadDays)}d lead
          </span>
          <span className="tabular-nums font-semibold">
            {q.reorder_point === null ? EM_DASH : fmtInt(q.reorder_point)}
          </span>
        </div>
      </div>
    </div>
  );
}

/** Row-anchored inline edit popover (M8-C5): qty + supplier + live cash preview
 *  + REQUIRED reason. Save disabled until the reason is non-empty. */
function InlineEditPopover({
  row,
  anchor,
  onSave,
}: {
  row: M8PlanRow;
  anchor: React.ReactNode;
  onSave: (patch: { order_qty: number; supplier_code: string }, reason: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [qty, setQty] = useState(String(row.order_qty));
  const [supplierCode, setSupplierCode] = useState(row.supplier.code);
  const [reason, setReason] = useState('');

  const reset = () => {
    setQty(String(row.order_qty));
    setSupplierCode(row.supplier.code);
    setReason('');
  };

  // Supplier swap options come from this rec's ranked alternatives (M8-C5); the
  // chosen supplier is always included so it stays selectable.
  const supplierOptions = row.alternatives;
  const supplierOpt = supplierOptions.find((o) => o.value === supplierCode);
  const unitCost = supplierOpt?.unit_cost ?? row.unit_cost ?? 0;
  const newQty = Number(qty) || 0;
  const newCash = newQty * unitCost;
  const originalCash = m8CashImpact(row) ?? 0;
  const delta = newCash - originalCash;
  const canSave = reason.trim().length > 0 && newQty > 0;

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) reset();
      }}
    >
      <PopoverTrigger asChild>{anchor}</PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="start" collisionPadding={8} className="w-80 space-y-3 p-3">
          <div className="text-xs font-semibold">Adjust {row.sku}</div>
          <div className="space-y-1">
            <Label htmlFor={`qty-${row.id}`} className="text-xs">
              Order qty
            </Label>
            <Input
              id={`qty-${row.id}`}
              type="number"
              inputMode="numeric"
              min={1}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="tabular-nums"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Supplier</Label>
            <SearchableSelect
              value={supplierCode}
              onChange={setSupplierCode}
              options={supplierOptions}
              placeholder="Select supplier"
              emptyMessage="No alternative suppliers on file."
            />
          </div>
          <div className="flex items-center justify-between rounded-md bg-muted/50 px-2.5 py-1.5 text-xs">
            <span className="text-muted-foreground">Cash impact</span>
            <span className="font-semibold tabular-nums">
              {fmtMoney(newCash)}{' '}
              <span className={cn(delta === 0 ? 'text-muted-foreground' : delta > 0 ? 'text-scm-stockout' : 'text-scm-incoming')}>
                ({delta >= 0 ? '+' : '-'}
                {fmtMoney(Math.abs(delta)).replace('RM ', '')})
              </span>
            </span>
          </div>
          <div className="space-y-1">
            <Label htmlFor={`reason-${row.id}`} className="text-xs">
              Reason <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id={`reason-${row.id}`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. seasonal uplift"
              rows={2}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!canSave}
              onClick={() => {
                onSave({ order_qty: newQty, supplier_code: supplierCode }, reason.trim());
                setOpen(false);
              }}
            >
              Save
            </Button>
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/** Reject reason popover (M8-C6 + M8-X3): a required reason IS the confirmation. */
function RejectPopover({ row, onReject }: { row: M8PlanRow; onReject: (reason: string) => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) setReason('');
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs">
          Reject
        </Button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="end" collisionPadding={8} className="w-72 space-y-2 p-3">
          <div className="text-xs font-semibold">Reject {row.sku}</div>
          <p className="text-2xs text-muted-foreground">
            The line stays on the plan marked &ldquo;Rejected&rdquo; and is left out of the buy. You can
            restore it with Accept.
          </p>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason for rejecting"
            rows={2}
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={!reason.trim()}
              onClick={() => {
                onReject(reason.trim());
                setOpen(false);
              }}
            >
              Reject
            </Button>
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/** The draft PO a confirmed line materialised into (M8-F8/M8-F9). */
export interface RowPoLink {
  po_number: string;
  po_id: string | null;
}

/** One data row - draggable between sections; renders inline cells + decisions. */
function PlanRow({
  runId,
  row,
  section,
  decision,
  edited,
  po,
  rankLabel,
  dragDisabled,
  handlers,
  onOpenDetail,
}: {
  /** The run the row belongs to, so the demand drill can fetch its order lines. */
  runId?: string | null;
  row: M8PlanRow;
  section: 'within' | 'over' | 'needs_cost';
  decision: M8RowDecision;
  edited: boolean;
  /** The draft PO this line was confirmed into, if any (M8-F8/M8-F9). */
  po?: RowPoLink;
  /** Sequential 1..N priority within the costed plan (M8-F) - defaults to the global rank. */
  rankLabel?: number;
  /** When a sort/search is active the row order no longer maps to drag order, so the
   *  drag handle is rendered inert to stop the two orderings fighting. */
  dragDisabled?: boolean;
  handlers: RowHandlers;
  /** Open the recommendation detail view (M8-C10). Fires only on a bare-row click -
   *  clicks on the inline controls (buttons / links / inputs) are excluded. */
  onOpenDetail?: (row: M8PlanRow) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: row.id,
    data: { section },
  });
  const cash = m8CashImpact(row);
  const isRejected = decision === 'rejected';
  const isPinned = decision === 'accepted';
  // A line that has been confirmed into a draft PO is locked (M8-F9): it no longer
  // offers Accept/Reject, it shows a link to the PO it landed in.
  const isConfirmed = !!po;

  return (
    <div
      ref={setNodeRef}
      onClick={
        onOpenDetail
          ? (e) => {
              // Inline controls (drag handle, qty/supplier edit, explain icons,
              // decision buttons, DO links) keep their own targets - only a click
              // on the bare row opens the detail view (M8-C10).
              if ((e.target as HTMLElement).closest('button, a, input, textarea, [role="dialog"]')) {
                return;
              }
              onOpenDetail(row);
            }
          : undefined
      }
      title={onOpenDetail ? `View ${row.sku} recommendation detail` : undefined}
      className={cn(
        'grid items-center border-b text-sm last:border-b-0',
        onOpenDetail && 'cursor-pointer hover:bg-muted/30',
        section === 'over' && 'opacity-80',
        isDragging && 'opacity-40',
        isRejected && 'opacity-50',
      )}
      style={{ gridTemplateColumns: COLS }}
    >
      {/* drag handle - hidden while a sort/search is active (drag order is meaningless then) */}
      <div className="flex h-full items-center justify-center py-2 text-muted-foreground/40">
        {dragDisabled ? null : (
          <button
            type="button"
            className="cursor-grab touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm active:cursor-grabbing"
            title="Drag between sections"
            aria-label={`Drag ${row.sku} between sections`}
            {...attributes}
            {...listeners}
          >
            <GripVertical className="size-4" aria-hidden />
          </button>
        )}
      </div>

      {/* rank */}
      <div className="px-1 py-2 tabular-nums" title={`Rank ${rankLabel ?? row.rank} by cash priority`}>
        {rankLabel ?? row.rank}
      </div>

      {/* SKU */}
      <div className="min-w-0 px-1 py-2">
        <div className="flex items-center gap-1.5">
          <span className="truncate font-medium" title={row.sku}>
            {row.sku}
          </span>
          {/* Which orders this quantity is actually for. Answers "why is it bought into
              BRW when I ordered for BRW-IB, and why so many" from the row itself. */}
          <PlanDemandPopover runId={runId ?? null} recId={row.id} />
          {/* On hand, incoming, outstanding PO, outstanding sales, the level and the last
              price - the lookups the buyer used to do by hand before deciding. */}
          <PlanChecklistPopover rec={row.rec} />
          {isPinned ? (
            <Badge variant="primary" appearance="light" size="xs">
              pinned
            </Badge>
          ) : null}
        </div>
        <span className="block truncate text-2xs text-muted-foreground" title={row.product_name}>
          {row.product_name}
        </span>
      </div>

      {/* type */}
      <div className="px-1 py-2">
        <Badge variant="info" appearance="light" size="sm">
          <ShoppingCart className="size-3" />
          Buy
        </Badge>
      </div>

      {/* order qty - click to edit + explain drill */}
      <div className="flex items-center justify-end gap-1 px-1 py-2 text-right">
        <InlineEditPopover
          row={row}
          onSave={(patch, reason) => handlers.onEdit(row, patch, reason)}
          anchor={
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-sm tabular-nums hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title="Click to adjust qty / supplier"
            >
              {edited ? (
                <span className="inline-flex items-center gap-1">
                  <span className="text-2xs text-muted-foreground line-through">
                    {fmtInt(row.original_order_qty)}
                  </span>
                  <span className="font-medium text-scm-overstock">{fmtInt(row.order_qty)}</span>
                </span>
              ) : (
                fmtInt(row.order_qty)
              )}
            </button>
          }
        />
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              title="How we got this qty"
              aria-label="Explain order qty"
              className="text-muted-foreground/70 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
            >
              <Info className="size-3.5" aria-hidden />
            </button>
          </PopoverTrigger>
          <PopoverPortal>
            <PopoverContent align="end" collisionPadding={8} className="w-80 p-0 text-sm">
              <OrderQtyDrill
                row={row}
                onApplyOffsets={(qty, reason) =>
                  handlers.onEdit(row, { order_qty: qty, supplier_code: row.supplier.code }, reason)
                }
              />
            </PopoverContent>
          </PopoverPortal>
        </Popover>
      </div>

      {/* master-data reorder settings - what the product record says, beside what the plan
          computed. A dash is "not set on the product", not zero. */}
      <div className="px-1 py-2 text-right tabular-nums text-muted-foreground">
        {row.rec.master_reorder_level == null ? EM_DASH : fmtInt(row.rec.master_reorder_level)}
      </div>
      <div className="px-1 py-2 text-right tabular-nums text-muted-foreground">
        {row.rec.master_reorder_quantity == null
          ? EM_DASH
          : fmtInt(row.rec.master_reorder_quantity)}
      </div>

      {/* cash impact - hover shows qty x unit cost */}
      <div
        className="px-1 py-2 text-right tabular-nums"
        title={
          cash === null
            ? costUnavailableReason(row)
            : `${fmtInt(row.order_qty)} x ${fmtSupplierCost(row.unit_cost, row.currency)}`
        }
      >
        {cash === null ? (
          <span className="text-2xs text-muted-foreground">{costUnavailableLabel(row)}</span>
        ) : (
          fmtMoney(cash)
        )}
      </div>

      {/* net - explain drill */}
      <div className="px-1 py-2 text-right">
        <ExplainNumber value={fmtSigned(row.net)} title="Explain net">
          <NetDrill row={row} />
        </ExplainNumber>
      </div>

      {/* days cover - explain drill */}
      <div className="px-1 py-2 text-right">
        <ExplainNumber
          value={row.days_cover === null ? EM_DASH : fmtInt(row.days_cover)}
          title="Explain runway"
        >
          <DaysCoverDrill row={row} />
        </ExplainNumber>
      </div>

      {/* warehouse (per-rec; network run reads "Network") */}
      <div className="min-w-0 px-1 py-2">
        <span className="block truncate text-xs" title={row.warehouse}>
          {row.warehouse}
        </span>
      </div>

      {/* supplier - click to edit */}
      <div className="min-w-0 overflow-hidden px-1 py-2">
        <InlineEditPopover
          row={row}
          onSave={(patch, reason) => handlers.onEdit(row, patch, reason)}
          anchor={
            <button
              type="button"
              className="block w-full min-w-0 rounded-sm text-left hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              title="Click to change supplier"
            >
              <span className="block truncate text-xs font-medium" title={row.supplier.name}>
                {row.supplier.name}
              </span>
              <span className="block truncate text-2xs text-muted-foreground">
                {row.unit_cost === null ? 'no cost' : fmtSupplierCost(row.unit_cost, row.currency)} ·{' '}
                {fmtInt(row.supplier.lead_time_days)}d lead
              </span>
            </button>
          }
        />
      </div>

      {/* decision */}
      <div className="flex items-center gap-1 px-1 py-2">
        {isConfirmed ? (
          // Confirmed line (M8-F9): locked, links to the draft PO it created (M8-F8).
          <>
            <Badge variant="success" appearance="light" size="sm">
              PO created
            </Badge>
            {po.po_id ? (
              <Link
                href={`/scm/purchase-orders/${po.po_id}`}
                className="whitespace-nowrap text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                title={`View ${po.po_number}`}
              >
                {po.po_number}
              </Link>
            ) : (
              <span className="whitespace-nowrap text-xs font-medium tabular-nums" title={po.po_number}>
                {po.po_number}
              </span>
            )}
          </>
        ) : section === 'over' ? (
          // M8-F13: over-budget rows have NO call-to-action (no Accept / Reject /
          // Fund) - the only way to fund one is to DRAG it up into Within budget.
          // A rejected line dragged down keeps its "Rejected" chip but no buttons.
          isRejected ? (
            <Badge variant="secondary" appearance="light" size="sm">
              Rejected
            </Badge>
          ) : (
            <span className="text-2xs text-muted-foreground">Drag up to fund</span>
          )
        ) : isRejected ? (
          <>
            <Badge variant="secondary" appearance="light" size="sm">
              Rejected
            </Badge>
            {/* Reversible (M8-F1): Accept overrides the reject and restores the buy.
                (The old "Fund" restore button is removed - sections move by drag only.) */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => handlers.onFund(row)}
            >
              Accept
            </Button>
          </>
        ) : isPinned ? (
          <>
            <Badge variant="success" appearance="light" size="sm">
              Accepted
            </Badge>
            <RejectPopover row={row} onReject={(reason) => handlers.onReject(row, reason)} />
          </>
        ) : (
          <>
            {/* Accept / Reject live only on Within-budget rows (M8-F13). */}
            <Button
              variant="primary"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => handlers.onFund(row)}
            >
              Accept
            </Button>
            <RejectPopover row={row} onReject={(reason) => handlers.onReject(row, reason)} />
          </>
        )}
      </div>
    </div>
  );
}

/** A droppable section wrapper - dropping a row here funds (within) or defers (over). */
function DroppableSection({
  id,
  children,
}: {
  id: 'within' | 'over';
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id, data: { section: id } });
  return (
    <div ref={setNodeRef} className={cn(isOver && 'bg-primary/5')}>
      {children}
    </div>
  );
}

/** Chevron collapse toggle for a section header (M8-D10). */
function CollapseToggle({
  collapsed,
  onToggle,
  label,
}: {
  collapsed: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={!collapsed}
      aria-label={collapsed ? `Expand ${label}` : `Collapse ${label}`}
      title={collapsed ? `Expand ${label}` : `Collapse ${label}`}
      className="flex size-6 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {collapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}
    </button>
  );
}

export function CashResultsGrid({
  within,
  over,
  decisions,
  editedIds,
  poByRow,
  displayRank,
  budgetHeader,
  handlers,
  onOpenDetail,
  runId,
  needsCost,
  reviewCostHref,
}: {
  within: M8PlanRow[];
  over: M8PlanRow[];
  /** Buys the plan produced but could not price - no supplier cost, or no exchange rate
   *  for the currency the cost is in. They are real shortages that still have to be
   *  fulfilled, so they get their own section and can be ordered; they are only kept out
   *  of the budget arithmetic, which needs a number nobody has. */
  needsCost?: M8PlanRow[];
  /** Where "Add a cost" sends the buyer (the products list, pre-filtered when one SKU). */
  reviewCostHref?: string;
  decisions: Record<string, M8RowDecision>;
  editedIds: ReadonlySet<string>;
  /** Draft PO per confirmed line, keyed by row id (M8-F8/M8-F9). */
  poByRow?: Record<string, RowPoLink>;
  /** Sequential 1..N priority label per row id over the costed plan (M8-F). */
  displayRank?: Record<string, number>;
  /** The budget control + committed/free readout, rendered in the funded header. */
  budgetHeader: React.ReactNode;
  handlers: RowHandlers;
  /** Open the recommendation detail view for a row (M8-C10). */
  onOpenDetail?: (row: M8PlanRow) => void;
  /** The run on screen, threaded to each row's demand drill. */
  runId?: string | null;
}) {
  // Each section collapses independently so the user can fold the table away and
  // scroll to the run-history list below (M8-D10).
  const [withinCollapsed, setWithinCollapsed] = useState(false);
  const [overCollapsed, setOverCollapsed] = useState(false);
  // The unpriced section can run to hundreds of rows on a book with thin supplier costs,
  // which would bury the two sections the buyer came for. Start it folded once it is
  // large; the header still states the count, so nothing is hidden, only deferred.
  const [needsCostCollapsed, setNeedsCostCollapsed] = useState(
    () => (needsCost?.length ?? 0) > 25,
  );

  // Client-side product search + column sort over the visible rows (additive).
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState<SortCol>('rank');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const needle = search.trim().toLowerCase();
  // Drag only makes sense in the untouched engine order (rank asc, no search); any
  // other sort/search freezes the order so drag can't fight it (see PlanRow).
  const dragDisabled = !(sortCol === 'rank' && sortDir === 'asc' && needle === '');

  // asc → desc → back to the default rank order.
  const onSort = (col: SortCol) => {
    if (sortCol !== col) {
      setSortCol(col);
      setSortDir('asc');
    } else if (sortDir === 'asc') {
      setSortDir('desc');
    } else {
      setSortCol('rank');
      setSortDir('asc');
    }
  };

  const visibleWithin = useMemo(
    () => sortSection(within.filter((r) => matchesSearch(r, needle)), sortCol, sortDir),
    [within, needle, sortCol, sortDir],
  );
  const visibleOver = useMemo(
    () => sortSection(over.filter((r) => matchesSearch(r, needle)), sortCol, sortDir),
    [over, needle, sortCol, sortDir],
  );
  const withinBadge = needle
    ? `${fmtInt(visibleWithin.length)} of ${fmtInt(within.length)}`
    : fmtInt(within.length);
  const overBadge = needle
    ? `${fmtInt(visibleOver.length)} of ${fmtInt(over.length)}`
    : fmtInt(over.length);

  const unpriced = needsCost ?? [];
  const visibleUnpriced = useMemo(
    () => sortSection(unpriced.filter((r) => matchesSearch(r, needle)), sortCol, sortDir),
    [unpriced, needle, sortCol, sortDir],
  );
  const unpricedBadge = needle
    ? `${fmtInt(visibleUnpriced.length)} of ${fmtInt(unpriced.length)}`
    : fmtInt(unpriced.length);

  return (
    <div className="space-y-3">
      {/* Product search - filters both sections by SKU / product / supplier. */}
      <div className="relative w-full sm:max-w-xs">
        <Search
          className="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search SKU, product, or supplier..."
          aria-label="Search buy recommendations"
          className="h-9 ps-8 pe-8"
        />
        {search ? (
          <button
            type="button"
            onClick={() => setSearch('')}
            aria-label="Clear search"
            title="Clear search"
            className="absolute end-2 top-1/2 -translate-y-1/2 rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="size-4" aria-hidden />
          </button>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-xl border">
        <div style={{ minWidth: MIN_TABLE_WIDTH }}>
        {/* header row */}
        <div
          className="grid items-center border-b bg-muted/40 px-0 text-2xs font-medium uppercase tracking-wide text-muted-foreground"
          style={{ gridTemplateColumns: COLS }}
        >
          <div className="py-2" />
          <div className="px-1 py-2">
            <SortHeader label="Rank" col="rank" activeCol={sortCol} dir={sortDir} onSort={onSort} />
          </div>
          <div className="px-1 py-2">SKU</div>
          <div className="px-1 py-2">Type</div>
          <div className="px-1 py-2 text-right">
            <SortHeader label="Order qty" col="order_qty" activeCol={sortCol} dir={sortDir} onSort={onSort} align="end" />
          </div>
          <div className="px-1 py-2 text-right" title="Reorder level on the product record">
            Reorder level
          </div>
          <div className="px-1 py-2 text-right" title="Reorder quantity on the product record">
            Reorder qty
          </div>
          <div className="px-1 py-2 text-right">
            <SortHeader label="Cash impact" col="cash" activeCol={sortCol} dir={sortDir} onSort={onSort} align="end" />
          </div>
          <div className="px-1 py-2 text-right">Net</div>
          <div className="px-1 py-2 text-right">
            <SortHeader label="Runway" col="days_cover" activeCol={sortCol} dir={sortDir} onSort={onSort} align="end" />
          </div>
          <div className="px-1 py-2">
            <SortHeader label="Warehouse" col="warehouse" activeCol={sortCol} dir={sortDir} onSort={onSort} />
          </div>
          <div className="px-1 py-2">
            <SortHeader label="Supplier" col="supplier" activeCol={sortCol} dir={sortDir} onSort={onSort} />
          </div>
          <div className="px-1 py-2">Decision</div>
        </div>

        {/* Within budget section header (holds the budget control) */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-scm-incoming-soft/40 px-3 py-3">
          <div className="flex items-center gap-2">
            <CollapseToggle
              collapsed={withinCollapsed}
              onToggle={() => setWithinCollapsed((v) => !v)}
              label="within budget"
            />
            <CheckCircle2 className="size-4 text-scm-incoming" aria-hidden />
            <span className="text-sm font-semibold">Within budget</span>
            <Badge variant="secondary" appearance="light" size="sm">
              {withinBadge}
            </Badge>
          </div>
          {budgetHeader}
        </div>

        {!withinCollapsed ? (
          <DroppableSection id="within">
            {visibleWithin.length ? (
              visibleWithin.map((row) => (
                <PlanRow
            runId={runId}
                  key={row.id}
                  row={row}
                  section="within"
                  decision={decisions[row.id] ?? null}
                  edited={editedIds.has(row.id)}
                  po={poByRow?.[row.id]}
                  rankLabel={displayRank?.[row.id]}
                  dragDisabled={dragDisabled}
                  handlers={handlers}
                  onOpenDetail={onOpenDetail}
                />
              ))
            ) : (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                {needle && within.length > 0
                  ? 'No buys in this section match your search.'
                  : 'Nothing funded at this budget. Raise it or drag a row up to fund it.'}
              </div>
            )}
          </DroppableSection>
        ) : null}

        {/* Over budget divider */}
        <div className="flex items-center gap-2 border-y bg-muted/60 px-3 py-2 text-sm">
          <CollapseToggle
            collapsed={overCollapsed}
            onToggle={() => setOverCollapsed((v) => !v)}
            label="over budget"
          />
          <Clock className="size-4 text-scm-overstock" aria-hidden />
          <span className="font-semibold">Over budget</span>
          <Badge variant="secondary" appearance="light" size="sm">
            {overBadge}
          </Badge>
          <span className="text-2xs text-muted-foreground">
            drag a row up to fund it (pins), or raise the budget
          </span>
        </div>

        {!overCollapsed ? (
          <DroppableSection id="over">
            {visibleOver.length ? (
              visibleOver.map((row) => (
                <PlanRow
            runId={runId}
                  key={row.id}
                  row={row}
                  section="over"
                  decision={decisions[row.id] ?? null}
                  edited={editedIds.has(row.id)}
                  po={poByRow?.[row.id]}
                  rankLabel={displayRank?.[row.id]}
                  dragDisabled={dragDisabled}
                  handlers={handlers}
                  onOpenDetail={onOpenDetail}
                />
              ))
            ) : (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                {needle && over.length > 0
                  ? 'No buys in this section match your search.'
                  : 'Nothing deferred - the budget funds every costed buy.'}
              </div>
            )}
          </DroppableSection>
        ) : null}

        {/* No price section. Rendered always, per the standard that a section states its
            own emptiness rather than disappearing - "every buy has a price" is worth
            reading. These rows are NOT droppable: a drop would pin a line into a budget
            it cannot be measured against. */}
        <div className="flex flex-wrap items-center gap-2 border-y bg-muted/60 px-3 py-2 text-sm">
          <CollapseToggle
            collapsed={needsCostCollapsed}
            onToggle={() => setNeedsCostCollapsed((v) => !v)}
            label="no price yet"
          />
          <HelpCircle className="size-4 text-muted-foreground" aria-hidden />
          <span className="font-semibold">No price yet</span>
          <Badge variant="secondary" appearance="light" size="sm">
            {unpricedBadge}
          </Badge>
          <span className="text-2xs text-muted-foreground">
            still short, still orderable, but no cash figure - so outside the budget above
          </span>
          {unpriced.length > 0 && reviewCostHref ? (
            <Link
              href={reviewCostHref}
              className="ms-auto rounded-sm text-2xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Add a cost
            </Link>
          ) : null}
        </div>

        {!needsCostCollapsed ? (
          visibleUnpriced.length ? (
            visibleUnpriced.map((row) => (
              <PlanRow
                runId={runId}
                key={row.id}
                row={row}
                section="needs_cost"
                decision={decisions[row.id] ?? null}
                edited={editedIds.has(row.id)}
                po={poByRow?.[row.id]}
                rankLabel={displayRank?.[row.id]}
                dragDisabled
                handlers={handlers}
                onOpenDetail={onOpenDetail}
              />
            ))
          ) : (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              {needle && unpriced.length > 0
                ? 'No buys in this section match your search.'
                : 'Every buy in this plan has a price.'}
            </div>
          )
        ) : null}
        </div>
      </div>
    </div>
  );
}
