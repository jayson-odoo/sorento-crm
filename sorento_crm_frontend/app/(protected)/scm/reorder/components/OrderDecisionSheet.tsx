'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Check, PackageOpen } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt, fmtPct } from '../../lib/format';
import { dayLabel } from '../lib/coverageTimeline';
import {
  fmtCbm,
  fmtCost,
  fmtMonths,
  fmtVariance,
  orderQuantityImpact,
  type ImpactFigure,
} from '../lib/orderImpact';
import { useOrderSummarySuppliers } from '../hooks/useSummaryOrder';
import type { OrderSummaryRow, SupplierCandidate } from '../types/summaryOrder.types';

/**
 * The order-quantity decision (UAC Group C2), as a right slide-over off the
 * Summary Order Report row.
 *
 * Two things this screen refuses to do, both deliberate:
 *
 *  1. **It does not warn when the chosen quantity exceeds the shortfall**
 *     (AC-C2.7). Ordering spare is routine and frequently correct - a container
 *     is cheaper filled, and a line that has waited 214 days is not restocked by
 *     buying exactly what is missing. So the panel STATES the consequence
 *     (shortfall covered, spare created and where it lands, resulting months of
 *     cover, cash committed, container volume added) in a neutral tone, and the
 *     engine's own figure stays visible beside it (AC-C2.8). It does not correct
 *     the decider.
 *  2. **It does not print 0 for a figure it cannot compute.** Months of cover
 *     needs a demand statistic and container volume needs recorded dimensions,
 *     and most products have neither. A volume of 0 reads as "no space needed"
 *     and a cover of 0 as "already out of stock", so each figure names the input
 *     that is missing instead, which also puts the gap in front of whoever can
 *     go and record it.
 *
 * Supplier is a choice, not a fixed value (AC-C2.5). Each candidate carries last
 * PO cost and DATE, last incoming cost, the variance between them, on-time rate
 * and lead time - cost alone cannot answer whether to change supplier (AC-C3.5).
 * A candidate that has never delivered this item says so, or the lowest cost on
 * the list makes an untested supplier look like the obvious pick. A stale last
 * PO date is flagged (AC-C2.6): it is what separates a fast mover from a dead
 * line. Both costs are labelled ex-works in the supplier's currency and neither
 * is a landed cost (AC-C3.4).
 */

/** One figure in the consequence panel: the number, or the input that is missing. */
function ConsequenceFigure({
  label,
  figure,
  format,
  testId,
}: {
  label: string;
  figure: ImpactFigure;
  format: (value: number) => string;
  testId: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border px-3 py-2" data-testid={testId}>
      <div className="truncate text-2xs uppercase tracking-wide text-muted-foreground" title={label}>
        {label}
      </div>
      {figure.value === null ? (
        <div className="text-sm font-medium text-muted-foreground" title={figure.missing ?? ''}>
          {figure.missing}
        </div>
      ) : (
        <div className="truncate text-lg font-semibold tabular-nums leading-tight">
          {format(figure.value)}
        </div>
      )}
    </div>
  );
}

/** One number in the position strip. */
function Position({ label, value, tone }: { label: string; value: number; tone?: 'short' }) {
  return (
    <div className="min-w-0 rounded-lg border border-border px-2.5 py-1.5">
      <div className="truncate text-2xs uppercase tracking-wide text-muted-foreground" title={label}>
        {label}
      </div>
      <div
        className={cn(
          'truncate text-sm font-semibold tabular-nums',
          tone === 'short' && value > 0 && 'text-scm-stockout',
        )}
      >
        {fmtInt(value)}
      </div>
    </div>
  );
}

function SupplierRow({
  candidate,
  staleAfterDays,
  selected,
  onSelect,
}: {
  candidate: SupplierCandidate;
  staleAfterDays: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const c = candidate;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      data-testid={`supplier-${c.supplier_code}`}
      className={cn(
        'w-full border-b px-3 py-2.5 text-start last:border-b-0 transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
        selected && 'bg-muted/60',
      )}
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-center gap-1.5 break-words">
          {selected ? <Check className="size-3.5 shrink-0 text-primary" aria-hidden /> : null}
          <span className="font-medium" title={c.supplier_name}>
            {c.supplier_name}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {c.delivered_line_count === 0 ? (
            <Badge variant="warning" appearance="light" size="xs">
              never delivered this item
            </Badge>
          ) : null}
          {c.is_stale ? (
            <Badge
              variant="destructive"
              appearance="light"
              size="xs"
              title={`Last bought more than ${fmtInt(staleAfterDays)} days ago`}
            >
              stale
            </Badge>
          ) : null}
        </div>
      </div>

      <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 text-2xs sm:grid-cols-3">
        <div className="min-w-0">
          <dt className="text-muted-foreground">Last PO cost (ex-works)</dt>
          <dd className="truncate tabular-nums">
            {c.last_po_cost === null ? EM_DASH : fmtCost(c.last_po_cost, c.currency)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Last PO date</dt>
          <dd className="truncate tabular-nums" data-testid={`last-po-date-${c.supplier_code}`}>
            {c.last_po_date ? dayLabel(c.last_po_date) : 'never bought'}
            {c.stale_days !== null ? (
              <span className={cn('ms-1', c.is_stale && 'text-scm-stockout')}>
                ({fmtInt(c.stale_days)} days ago)
              </span>
            ) : null}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Incoming cost (ex-works)</dt>
          <dd className="truncate tabular-nums">
            {c.last_incoming_cost === null
              ? 'never received'
              : fmtCost(c.last_incoming_cost, c.currency)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Ordered to incoming</dt>
          <dd
            className={cn(
              'truncate tabular-nums',
              c.cost_variance !== null && c.cost_variance > 0 && 'text-scm-stockout',
            )}
          >
            {c.cost_variance === null ? EM_DASH : fmtVariance(c.cost_variance, c.currency)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">On time</dt>
          <dd className="truncate tabular-nums">
            {c.on_time_rate === null ? EM_DASH : fmtPct(c.on_time_rate)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Lead time</dt>
          <dd className="truncate tabular-nums">
            {c.lead_time_days === null ? EM_DASH : `${fmtInt(c.lead_time_days)} days`}
          </dd>
        </div>
      </dl>
    </button>
  );
}

export interface OrderDecisionSheetProps {
  row: OrderSummaryRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (input: { chosen_qty: number; supplier_code: string }) => void;
  isSaving: boolean;
}

export function OrderDecisionSheet({
  row,
  open,
  onOpenChange,
  onSave,
  isSaving,
}: OrderDecisionSheetProps) {
  const [qtyText, setQtyText] = useState('');
  const [supplierCode, setSupplierCode] = useState<string | null>(null);

  const suppliers = useOrderSummarySuppliers(row?.product_code ?? null, open);

  // Reopening on another row starts from that row's own decision, or the
  // engine's suggestion when it has none.
  useEffect(() => {
    if (!open || !row) return;
    setQtyText(String(row.chosen_qty ?? row.suggested_qty ?? 0));
    setSupplierCode(row.chosen_supplier_code);
  }, [open, row]);

  const candidates = useMemo(() => suppliers.data?.candidates ?? [], [suppliers.data]);
  const selected = useMemo(
    () => candidates.find((c) => c.supplier_code === supplierCode) ?? null,
    [candidates, supplierCode],
  );

  const chosenQty = Number.parseInt(qtyText, 10);
  const qty = Number.isFinite(chosenQty) ? chosenQty : 0;
  const impact = row ? orderQuantityImpact(row, qty, selected) : null;

  if (!row) return null;

  const canSave = qty > 0 && !!supplierCode && !isSaving;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full gap-0 overflow-y-auto p-0 sm:max-w-xl"
        aria-describedby={undefined}
      >
        <SheetHeader className="border-b p-4 pe-12 sm:p-6 sm:pe-12">
          <SheetTitle className="min-w-0 break-words">
            {row.product_code}
            {row.product_name ? ` · ${row.product_name}` : ''}
          </SheetTitle>
          <SheetDescription className="min-w-0 break-words">
            Order quantity and supplier
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="space-y-5 p-4 sm:p-6">
          {/* Position - what the row already said, so the decision is taken in context. */}
          <section aria-label="Position">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Position label="On hand" value={row.on_hand} />
              <Position label="Project demand" value={row.project_demand} />
              <Position label="Dealer outstanding" value={row.dealer_outstanding} />
              <Position label="On order" value={row.qty_on_order} />
              <Position label="In transit" value={row.qty_in_transit} />
              <Position label="Shortfall" value={row.shortfall} tone="short" />
            </div>
          </section>

          {/* Quantity - the single decision, with the engine's figure beside it. */}
          <section aria-label="Quantity" className="space-y-2">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0 flex-1">
                <Label htmlFor="chosen-qty" className="mb-1 block">
                  Order quantity{row.uom ? ` (${row.uom})` : ''}
                </Label>
                <Input
                  id="chosen-qty"
                  inputMode="numeric"
                  value={qtyText}
                  onChange={(e) => setQtyText(e.target.value.replace(/[^0-9]/g, ''))}
                  className="tabular-nums"
                />
              </div>
              <div className="shrink-0 rounded-lg border border-border px-3 py-2" data-testid="suggested-qty">
                <div className="text-2xs uppercase tracking-wide text-muted-foreground">
                  Engine suggests
                </div>
                <div className="text-lg font-semibold tabular-nums leading-tight">
                  {fmtInt(row.suggested_qty)}
                </div>
              </div>
              <Button
                variant="outline"
                className="shrink-0"
                onClick={() => setQtyText(String(row.suggested_qty))}
              >
                Use suggestion
              </Button>
            </div>
            {row.decided_by ? (
              <p className="text-2xs text-muted-foreground">
                Last set to {fmtInt(row.chosen_qty)} by {row.decided_by}
                {row.decided_at ? ` on ${dayLabel(row.decided_at.slice(0, 10))}` : ''}
              </p>
            ) : null}
          </section>

          {/* Consequence - stated, never warned about (AC-C2.7). */}
          {impact ? (
            <section aria-label="What this order does" className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                What this order does
              </div>
              <div
                className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm"
                data-testid="impact-headline"
              >
                Covers {fmtInt(impact.shortfall_covered)} of the {fmtInt(impact.shortfall)} short
                {impact.shortfall_remaining > 0
                  ? `, leaving ${fmtInt(impact.shortfall_remaining)} still short`
                  : ''}
                {impact.spare_qty > 0
                  ? `, and creates ${fmtInt(impact.spare_qty)} spare in ${
                      impact.spare_lands_at ?? 'the pool'
                    }`
                  : ''}
                .
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <ConsequenceFigure
                  label="Months of cover"
                  figure={impact.months_of_cover}
                  format={(v) => fmtMonths(v)}
                  testId="impact-cover"
                />
                <ConsequenceFigure
                  label={`Cash committed${impact.currency ? ` (${impact.currency}, ex-works)` : ''}`}
                  figure={impact.cash_committed}
                  format={(v) => fmtCost(v, impact.currency)}
                  testId="impact-cash"
                />
                <ConsequenceFigure
                  label="Container volume added"
                  figure={impact.volume_cbm}
                  format={(v) => fmtCbm(v)}
                  testId="impact-volume"
                />
              </div>
            </section>
          ) : null}

          {/* Supplier - a choice, with what it costs to make it (AC-C2.5). */}
          <section aria-label="Supplier" className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Supplier
            </div>
            {suppliers.isLoading ? (
              <div className="space-y-2" aria-label="Loading supplier candidates" aria-busy="true">
                {Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 w-full rounded-lg" />
                ))}
              </div>
            ) : suppliers.isError || !suppliers.data ? (
              <div className="flex flex-col items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-center">
                <AlertCircle className="size-5 text-destructive" aria-hidden />
                <p className="max-w-sm text-sm text-muted-foreground">
                  {suppliers.error instanceof Error
                    ? suppliers.error.message
                    : 'Failed to load the supplier candidates.'}
                </p>
                <Button variant="outline" size="sm" onClick={() => void suppliers.refetch()}>
                  Try again
                </Button>
              </div>
            ) : candidates.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border p-4 text-center">
                <PackageOpen className="mx-auto size-5 text-muted-foreground" aria-hidden />
                <p className="mt-1 text-sm font-medium">No supplier linked to this item</p>
                <p className="mt-0.5 text-2xs text-muted-foreground">
                  Link one in Master Data before it can be ordered.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                {candidates.map((c) => (
                  <SupplierRow
                    key={c.supplier_code}
                    candidate={c}
                    staleAfterDays={suppliers.data.stale_after_days}
                    selected={c.supplier_code === supplierCode}
                    onSelect={() => setSupplierCode(c.supplier_code)}
                  />
                ))}
              </div>
            )}
          </section>
        </SheetBody>

        <SheetFooter className="gap-2 border-t p-4 sm:p-6">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button
            disabled={!canSave}
            onClick={() => {
              if (!supplierCode) return;
              onSave({ chosen_qty: qty, supplier_code: supplierCode });
            }}
          >
            Record decision
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

export default OrderDecisionSheet;
