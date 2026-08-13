'use client';

import { useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { fmtInt } from '../../lib/format';
import type { PlanLine } from '../lib/planLine';
import type { PlanDecision } from '../lib/planDecisions';
import { describeCover, type CoverProposal } from '../lib/coverPlan';
import { describePoBook, poOffset, type PoReceipt } from '../lib/poCover';
import { trendAdvice, type TrajectoryEntry } from '../lib/trajectory';
import { marginOf, type ProductEconomics } from '../lib/productHealth';

/**
 * The decision AND the suggestion, in ONE place (user markup, 2026-08-12).
 *
 * > "I want the decision and suggestion to be made in 1 place instead of going to multiple
 * >  places. I want the decision to be emphasized: the user sees the table, they know exactly
 * >  which button/cell/icon to click to make the decision, and after they made it, they know
 * >  which one has been made, which one hasn't, so they can decide until all outstanding
 * >  decisions are cleared."
 *
 * This used to be two columns: a text-only "Suggested action" column explaining the mix, and a
 * separate "Decision" column with the Accept / Adjust / Skip controls next to it - the same
 * fact, described twice, in two places the eye had to travel between. They are now one cell.
 *
 * An UNDECIDED row leads with ONE loud button carrying the whole mix ("Buy 1,100" /
 * "Stock 15 (BRW-BB) + PO 120"), because that button IS the decision - clicking it takes the
 * suggestion exactly as offered. Adjust and Skip sit beside it, smaller, for the two other
 * things a buyer does with a suggestion. Whatever else there is to know about the suggestion
 * (stock crossing a segment boundary, CS being superseded, an SPO already counted, a trend
 * argument for more or fewer) sits underneath in quiet type - present, but never competing with
 * the button for attention.
 *
 * A DECIDED row goes quiet: a check (or an X for a skip) and the mix actually taken, in the
 * PAST tense ("Bought 1,100" - the tense itself is the "this one is done" signal, since the
 * numbers alone would read the same as the suggestion), with a small "Change" to reopen it.
 * Reading down the column now answers "which ones are left" without opening anything.
 *
 * The composition math (stock, then the PO book, then a buy for the remainder) is untouched -
 * only where its words are printed moved.
 */

export function PlanLineDecisionCell({
  line,
  decision,
  cover,
  poReceipts = [],
  trend,
  economics,
  healthThresholds = { margin_floor_pct: 15, dead_turnover_months: 6 },
  onDecide,
  onClear,
}: {
  line: PlanLine;
  decision: PlanDecision | undefined;
  /** What the plan suggests: buy it, cover it from elsewhere, or both. */
  cover: CoverProposal;
  /** S15: the open PO lines already carrying this product here. */
  poReceipts?: PoReceipt[];
  /** The order-trend verdict behind the "consider more/fewer" advisory. Undefined = no
   *  opinion, so the advisory line is simply absent. */
  trend?: TrajectoryEntry;
  /** What the product sells for and how fast it turns, so a "buy more" advisory can carry
   *  its thin-margin caveat in the same breath. Undefined = no opinion. */
  economics?: ProductEconomics;
  /** The policy's lines for "thin margin". */
  healthThresholds?: { margin_floor_pct: number; dead_turnover_months: number };
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

  // The SAME shape, suggestion or decision - only the buy verb changes tense. That tense is
  // the "made / not made" signal: a decided row must not read exactly like an undecided one.
  const summary = (d: PlanDecision, decided = false): string => {
    if (d.skip) return 'Skipped';
    const parts: string[] = [];
    if ((d.stock?.qty ?? 0) > 0) {
      parts.push(`Stock ${fmtInt(d.stock!.qty)} (${d.stock!.sources.map((s) => s.warehouse_code).join(', ')})`);
    }
    if ((d.po ?? 0) > 0) parts.push(`PO ${fmtInt(d.po!)}`);
    if ((d.buy ?? 0) > 0) parts.push(`${decided ? 'Bought' : 'Buy'} ${fmtInt(d.buy!)}`);
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
      <div className="flex min-w-0 flex-wrap items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5">
        {decision.skip ? (
          <X className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <Check className="size-3.5 shrink-0 text-scm-incoming" aria-hidden />
        )}
        <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground" title={summary(decision, true)}>
          {summary(decision, true)}
        </span>
        <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs" onClick={onClear}>
          Change
        </Button>
      </div>
    );
  }

  const canAccept = line.purchasable && (suggestedBuy > 0 || stockQty > 0 || suggestedPo > 0);

  // What used to be the separate "Suggested action" column: the notes a buyer needs beyond
  // the mix itself. Quiet, underneath the button, never a second place to look for them.
  const advice = trendAdvice(trend, suggestedBuy);
  const margin = economics ? marginOf(line.unit_cost_base, economics, healthThresholds.margin_floor_pct) : null;
  const thinMargin =
    advice?.direction === 'more' &&
    (margin?.tone === 'thin' || margin?.tone === 'negative') &&
    margin?.pct !== null;
  // A cover offer on a project line is purchasing superseding CS: the inquiry said buy it
  // all, and the engine found stock CS did not use. Said out loud, because a quiet
  // disagreement with CS reads as the engine miscounting.
  const crossing = cover.sources.some((s) => s.cross_segment);
  const supersede =
    line.rec.segment === 'project' && cover.coverQty > 0 ? `CS asked to buy ${fmtInt(needed)}` : null;

  return (
    <div className="min-w-0 space-y-1">
      <div className="flex flex-wrap items-center gap-1.5">
        {/* The loudest thing in the row: this button IS the decision. */}
        <Button
          size="sm"
          className="h-8 px-2"
          onClick={() => onDecide(suggested)}
          disabled={!canAccept}
          title={acceptTitle}
        >
          <Check className="size-3.5 shrink-0" />
          <span className="max-w-44 truncate">{summary(suggested)}</span>
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
      {line.purchasable ? (
        <div className="min-w-0 text-2xs text-muted-foreground">
          {/* S15: what is arriving is ALREADY inside the net, so it is a note, never a
              second offset - counting it again would cover the same demand twice. */}
          {(line.rec.incoming_spo ?? 0) > 0 ? (
            <span className="block truncate">
              {`${fmtInt(line.rec.incoming_spo ?? 0)} arriving (SPO) already counted`}
            </span>
          ) : null}
          {crossing ? <span className="block text-scm-overstock">crosses segment</span> : null}
          {supersede ? <span className="block truncate">{supersede}</span> : null}
          {/* The forecast advisory: the trend's own %-change applied to the buy, applied by a
              CLICK, never silently - committed demand stays the driver. */}
          {advice ? (
            <button
              type="button"
              className="block truncate text-scm-incoming underline decoration-dotted underline-offset-2 hover:text-primary"
              title={`Apply: adjust the buy to ${fmtInt(
                advice.direction === 'more' ? suggestedBuy + advice.delta : suggestedBuy - advice.delta,
              )}`}
              onClick={() =>
                onDecide({
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
                  buy: advice.direction === 'more' ? suggestedBuy + advice.delta : suggestedBuy - advice.delta,
                  reason: `Trend: orders ${advice.direction === 'more' ? 'rose' : 'fell'} ${advice.pct}%`,
                })
              }
            >
              {`Consider ${fmtInt(advice.delta)} ${advice.direction} - orders ${
                advice.direction === 'more' ? 'rose' : 'fell'
              } ${advice.pct}%${thinMargin ? `, but margin only ${margin!.pct}%` : ''}`}
            </button>
          ) : null}
        </div>
      ) : null}
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
