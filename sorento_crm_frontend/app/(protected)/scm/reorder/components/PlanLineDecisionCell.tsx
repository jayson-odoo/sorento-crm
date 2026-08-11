'use client';

import { useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { fmtInt } from '../../lib/format';
import type { PlanLine } from '../lib/planLine';
import type { PlanDecision } from '../lib/planDecisions';
import { describeCover, type CoverProposal } from '../lib/coverPlan';
import { describePoBook, poOffset, type PoReceipt } from '../lib/poCover';

/**
 * One decision per row, and the decision is a MIXTURE (S16).
 *
 * > "imo it should be buy / use stock / use PO / use SPO etc, but we should allow mixture
 * >  of actions"
 *
 * The engine proposes a composition - stock from named bins, then the PO book, then a buy
 * for the remainder - and Accept records exactly that in one click. Adjust opens the same
 * three numbers for editing, each bounded by what actually exists. Incoming SPO is already
 * inside the net position, so it appears on the suggestion as a note, never as a fourth
 * number that would cover the same demand twice.
 *
 * Nothing here mentions a budget: what this costs is a question for after the decisions.
 * An undecided cell shows the actions and no state, because "I have not decided" has to
 * look different from every decision, including from skipping.
 */

export function PlanLineDecisionCell({
  line,
  decision,
  cover,
  poReceipts = [],
  onDecide,
  onClear,
}: {
  line: PlanLine;
  decision: PlanDecision | undefined;
  /** What the plan suggests: buy it, cover it from elsewhere, or both. */
  cover: CoverProposal;
  /** S15: the open PO lines already carrying this product here. */
  poReceipts?: PoReceipt[];
  onDecide: (next: PlanDecision) => void;
  /** Put the line back to undecided. Its own callback rather than a decision field,
   *  because undecided is the ABSENCE of a decision and must not become one. */
  onClear: () => void;
}) {
  // The engine's own composition. `order_qty` is frequently fractional on real data
  // (a demand rate times a horizon); rounded UP, never down - down is a deliberate
  // under-buy of a shortage we just calculated.
  const needed = Math.ceil(line.order_qty);
  const stockQty = cover.coverQty;
  const afterStock = stockQty > 0 ? cover.buyQty : needed;
  const poQty = poReceipts.reduce((t, r) => t + r.remaining, 0);
  const { usePo: suggestedPo, buy: suggestedBuy } = poOffset(afterStock, poQty);

  const suggested: PlanDecision = {
    ...(suggestedBuy > 0 ? { buy: suggestedBuy } : {}),
    ...(stockQty > 0
      ? {
          stock: {
            qty: stockQty,
            sources: cover.sources.map((s) => ({
              warehouse_id: s.warehouse_id,
              warehouse_code: s.warehouse_code,
              qty: s.qty,
            })),
          },
        }
      : {}),
    ...(suggestedPo > 0 ? { po: suggestedPo } : {}),
  };

  const summary = (d: PlanDecision): string => {
    if (d.skip) return 'Skipped';
    const parts: string[] = [];
    if ((d.stock?.qty ?? 0) > 0) {
      parts.push(`Stock ${fmtInt(d.stock!.qty)} (${d.stock!.sources.map((s) => s.warehouse_code).join(', ')})`);
    }
    if ((d.po ?? 0) > 0) parts.push(`PO ${fmtInt(d.po!)}`);
    if ((d.buy ?? 0) > 0) parts.push(`Buy ${fmtInt(d.buy!)}`);
    return parts.length ? parts.join(' + ') : 'Nothing';
  };

  const acceptTitle = [
    `Accept for ${line.sku}: ${summary(suggested)}.`,
    stockQty > 0 ? describeCover(cover, (n) => fmtInt(n)) : null,
    suggestedPo > 0 ? `Already ordered: ${describePoBook(poReceipts).join(' ')}` : null,
  ]
    .filter(Boolean)
    .join(' ');

  if (decision) {
    return (
      <div className="flex min-w-0 items-center gap-2">
        <Badge
          variant={decision.skip ? 'secondary' : 'primary'}
          appearance="light"
          size="sm"
          className="min-w-0"
        >
          <span className="truncate" title={summary(decision)}>
            {summary(decision)}
          </span>
        </Badge>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onClear}>
          Change
        </Button>
      </div>
    );
  }

  const canAccept = line.purchasable && (suggestedBuy > 0 || stockQty > 0 || suggestedPo > 0);

  return (
    <div className="flex items-center gap-1.5">
      <Button
        size="sm"
        className="h-8 px-2"
        onClick={() => onDecide(suggested)}
        disabled={!canAccept}
        title={acceptTitle}
      >
        <Check className="size-3.5" />
        <span className="max-w-40 truncate">{summary(suggested)}</span>
      </Button>
      {line.purchasable ? (
        <AdjustMixture
          line={line}
          suggested={suggested}
          stockMax={stockQty}
          poMax={poQty}
          cover={cover}
          onDecide={onDecide}
        />
      ) : null}
      <Button
        variant="ghost"
        size="sm"
        className="h-8 px-2"
        onClick={() => onDecide({ skip: true })}
        title={`Skip ${line.sku} this round`}
      >
        <X className="size-3.5" />
      </Button>
    </div>
  );
}

/**
 * The same three numbers, editable, each bounded by what actually exists: stock cannot
 * exceed what sits free, PO cannot exceed what is still to come. Buy is unbounded - the
 * buyer may deliberately order past the shortage.
 */
function AdjustMixture({
  line,
  suggested,
  stockMax,
  poMax,
  cover,
  onDecide,
}: {
  line: PlanLine;
  suggested: PlanDecision;
  stockMax: number;
  poMax: number;
  cover: CoverProposal;
  onDecide: (next: PlanDecision) => void;
}) {
  const [open, setOpen] = useState(false);
  const [buy, setBuy] = useState(String(suggested.buy ?? 0));
  const [stock, setStock] = useState(String(suggested.stock?.qty ?? 0));
  const [po, setPo] = useState(String(suggested.po ?? 0));

  const num = (v: string) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  };

  const commit = () => {
    const stockQty = Math.min(num(stock), stockMax);
    const poQty = Math.min(num(po), poMax);
    const buyQty = num(buy);
    // Stock keeps its per-bin split, scaled down from the front when the buyer takes less
    // than offered: the nearest bins were ranked first, so they are kept first.
    let remaining = stockQty;
    const sources = cover.sources
      .map((s) => {
        const take = Math.min(s.qty, remaining);
        remaining -= take;
        return { warehouse_id: s.warehouse_id, warehouse_code: s.warehouse_code, qty: take };
      })
      .filter((s) => s.qty > 0);
    onDecide({
      ...(buyQty > 0 ? { buy: buyQty } : {}),
      ...(stockQty > 0 ? { stock: { qty: stockQty, sources } } : {}),
      ...(poQty > 0 ? { po: poQty } : {}),
    });
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 px-2" title={`Adjust the mix for ${line.sku}`}>
          <Pencil className="size-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-64 space-y-2 text-xs" align="end">
          <p className="font-medium">Cover {fmtInt(Math.ceil(line.order_qty))} of {line.sku}</p>
          <label className="flex items-center justify-between gap-2">
            <span>From stock (max {fmtInt(stockMax)})</span>
            <Input
              type="number" min={0} max={stockMax} inputMode="numeric"
              className="h-7 w-20 text-right tabular-nums"
              value={stock} onChange={(e) => setStock(e.target.value)}
              disabled={stockMax <= 0}
              aria-label="Units from stock"
            />
          </label>
          <label className="flex items-center justify-between gap-2">
            <span>From PO book (max {fmtInt(poMax)})</span>
            <Input
              type="number" min={0} max={poMax} inputMode="numeric"
              className="h-7 w-20 text-right tabular-nums"
              value={po} onChange={(e) => setPo(e.target.value)}
              disabled={poMax <= 0}
              aria-label="Units from the PO book"
            />
          </label>
          <label className="flex items-center justify-between gap-2">
            <span>Buy</span>
            <Input
              type="number" min={0} inputMode="numeric"
              className="h-7 w-20 text-right tabular-nums"
              value={buy} onChange={(e) => setBuy(e.target.value)}
              aria-label="Units to buy"
            />
          </label>
          <div className="flex justify-end pt-1">
            <Button size="sm" className="h-7 px-3" onClick={commit}>
              Record
            </Button>
          </div>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
