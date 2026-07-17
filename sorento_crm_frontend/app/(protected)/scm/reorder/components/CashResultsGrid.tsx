'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  GripVertical,
  Info,
  ShoppingCart,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtDecimal, fmtInt, fmtMoney, fmtSigned } from '../../lib/format';
import { m8CashImpact, type M8PlanRow } from '../lib/planRow';
import { useExplainDemand, useExplainNet } from '../hooks/useDrills';

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
const COLS =
  'minmax(0,32px) minmax(0,52px) minmax(180px,1.5fr) minmax(0,76px) minmax(0,150px) minmax(0,120px) minmax(0,88px) minmax(0,120px) minmax(110px,1fr) minmax(160px,1.4fr) minmax(230px,1.4fr)';
const MIN_TABLE_WIDTH = 1330;

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
        <PopoverContent align="end" collisionPadding={8} className="w-80 p-0 text-sm">
          {children}
        </PopoverContent>
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
  // live `explain/demand` recompute — that runs a different window (and returns 0 for a
  // network SKU here) which would print "net / 0 = N". The live drill is evidence-only:
  // the DO list + coefficient of variation.
  const frozenRate = row.forecast_daily_demand;
  // No finite cover to show when there's a deficit OR no measurable frozen demand to
  // divide by — either way we must NOT divide by zero.
  const undefinedCover = row.days_cover === null || frozenRate == null || frozenRate <= 0;
  const isDeficit = row.net != null && row.net < 0;
  return (
    <div>
      <DrillHeader
        title={
          undefinedCover
            ? 'Days cover = undefined (deficit / no measurable demand)'
            : `Days cover = ${fmtInt(row.days_cover)}`
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
function OrderQtyDrill({ row }: { row: M8PlanRow }) {
  const q = row.order_qty_inputs;
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
      <div className="space-y-1 px-3 py-2">
        {line('Safety stock', q.safety_stock)}
        {line('Reorder point', q.reorder_point)}
        {line('Order-up-to level', q.order_up_to)}
        {line('MoQ', q.moq)}
        {line('Order multiple', q.order_multiple)}
        <div className="mt-1 flex justify-between border-t pt-1 text-xs font-medium">
          <span>Rounded order qty</span>
          <span className="tabular-nums">{fmtInt(q.rounded_qty)}</span>
        </div>
      </div>
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
            {q.safety_stock === null ? EM_DASH : fmtInt(q.safety_stock)} +{' '}
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
  row,
  section,
  decision,
  edited,
  po,
  rankLabel,
  handlers,
  onOpenDetail,
}: {
  row: M8PlanRow;
  section: 'within' | 'over';
  decision: M8RowDecision;
  edited: boolean;
  /** The draft PO this line was confirmed into, if any (M8-F8/M8-F9). */
  po?: RowPoLink;
  /** Sequential 1..N priority within the costed plan (M8-F) — defaults to the global rank. */
  rankLabel?: number;
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
      {/* drag handle */}
      <div className="flex h-full items-center justify-center py-2 text-muted-foreground/40">
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
          <PopoverContent align="end" collisionPadding={8} className="w-80 p-0 text-sm">
            <OrderQtyDrill row={row} />
          </PopoverContent>
        </Popover>
      </div>

      {/* cash impact - hover shows qty x unit cost */}
      <div
        className="px-1 py-2 text-right tabular-nums"
        title={cash === null ? 'No supplier cost on record' : `${fmtInt(row.order_qty)} x ${fmtMoney(row.unit_cost)}`}
      >
        {cash === null ? <span className="text-muted-foreground">{EM_DASH}</span> : fmtMoney(cash)}
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
          title="Explain days cover"
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
                {row.unit_cost === null ? 'no cost' : fmtMoney(row.unit_cost)} ·{' '}
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
          // Fund) — the only way to fund one is to DRAG it up into Within budget.
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
                (The old "Fund" restore button is removed — sections move by drag only.) */}
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
}: {
  within: M8PlanRow[];
  over: M8PlanRow[];
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
}) {
  // Each section collapses independently so the user can fold the table away and
  // scroll to the run-history list below (M8-D10).
  const [withinCollapsed, setWithinCollapsed] = useState(false);
  const [overCollapsed, setOverCollapsed] = useState(false);

  return (
    <div className="overflow-x-auto rounded-xl border">
      <div style={{ minWidth: MIN_TABLE_WIDTH }}>
        {/* header row */}
        <div
          className="grid items-center border-b bg-muted/40 px-0 text-2xs font-medium uppercase tracking-wide text-muted-foreground"
          style={{ gridTemplateColumns: COLS }}
        >
          <div className="py-2" />
          <div className="px-1 py-2">Rank</div>
          <div className="px-1 py-2">SKU</div>
          <div className="px-1 py-2">Type</div>
          <div className="px-1 py-2 text-right">Order qty</div>
          <div className="px-1 py-2 text-right">Cash impact</div>
          <div className="px-1 py-2 text-right">Net</div>
          <div className="px-1 py-2 text-right">Days cover</div>
          <div className="px-1 py-2">Warehouse</div>
          <div className="px-1 py-2">Supplier</div>
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
              {fmtInt(within.length)}
            </Badge>
          </div>
          {budgetHeader}
        </div>

        {!withinCollapsed ? (
          <DroppableSection id="within">
            {within.length ? (
              within.map((row) => (
                <PlanRow
                  key={row.id}
                  row={row}
                  section="within"
                  decision={decisions[row.id] ?? null}
                  edited={editedIds.has(row.id)}
                  po={poByRow?.[row.id]}
                  rankLabel={displayRank?.[row.id]}
                  handlers={handlers}
                  onOpenDetail={onOpenDetail}
                />
              ))
            ) : (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                Nothing funded at this budget. Raise it or drag a row up to fund it.
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
            {fmtInt(over.length)}
          </Badge>
          <span className="text-2xs text-muted-foreground">
            drag a row up to fund it (pins), or raise the budget
          </span>
        </div>

        {!overCollapsed ? (
          <DroppableSection id="over">
            {over.length ? (
              over.map((row) => (
                <PlanRow
                  key={row.id}
                  row={row}
                  section="over"
                  decision={decisions[row.id] ?? null}
                  edited={editedIds.has(row.id)}
                  po={poByRow?.[row.id]}
                  rankLabel={displayRank?.[row.id]}
                  handlers={handlers}
                  onOpenDetail={onOpenDetail}
                />
              ))
            ) : (
              <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                Nothing deferred - the budget funds every costed buy.
              </div>
            )}
          </DroppableSection>
        ) : null}
      </div>
    </div>
  );
}
