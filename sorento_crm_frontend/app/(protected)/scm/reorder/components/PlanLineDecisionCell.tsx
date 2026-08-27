'use client';

import { useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { fmtInt } from '../../lib/format';
import type { PlanLine } from '../lib/planLine';
import type { PlanDecision } from '../lib/planDecisions';
import { applySourceEdits, sourceEditsForTotal, type CoverProposal } from '../lib/coverPlan';
import { roundBuyQty } from '../lib/orderQtyLedger';
import { CoverBreakdownTable } from './CoverBreakdownTable';
import { describePoBook, poOffset, type PoReceipt } from '../lib/poCover';

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
 * (stock crossing a segment boundary, CS being superseded, an SPO already counted) sits
 * underneath in quiet type - present, but never competing with the button for attention.
 *
 * A DECIDED row goes quiet: a check (or an X for a skip) and the mix actually taken, in the
 * PAST tense ("Bought 1,100" - the tense itself is the "this one is done" signal, since the
 * numbers alone would read the same as the suggestion), with a small "Change" to reopen it.
 * Reading down the column now answers "which ones are left" without opening anything.
 *
 * The composition math (stock, then the PO book, then a buy for the remainder) is untouched -
 * only where its words are printed moved.
 *
 * S16 (captain, 21 Aug, 3rd time requested): "I want the decision made here" - the cell IS
 * the decision surface now, on every grain and every rec_type this can be decided over
 * (buy, covered, needs_level, disposition). `onDecide`/`onClear` write straight to the
 * backend (`POST`/`DELETE .../recommendations/{rec_id}/decision`); a rejected write is
 * caught here and toasted, the same pattern `PlanMoqCell` already uses for its own save.
 * On a GROUPED (product-grain) row the SAME decision is fanned out to every member behind
 * it (`usePlanLines.decide`, mirroring `updateMoq`'s fan-out) - `mixed` says the members
 * disagree, which reads differently from nobody having decided at all.
 */

export function PlanLineDecisionCell({
  line,
  decision,
  mixed = false,
  cover,
  poReceipts = [],
  onDecide,
  onClear,
}: {
  line: PlanLine;
  decision: PlanDecision | undefined;
  /** A GROUPED row's members disagree on the decision - some decided differently, or
   *  some decided and others have not. Distinct from `decision === undefined` alone,
   *  which is ALSO true of a group nobody has touched: that is undecided, not mixed. */
  mixed?: boolean;
  /** What the plan suggests: buy it, cover it from elsewhere, or both. */
  cover: CoverProposal;
  /** S15: the open PO lines already carrying this product here. */
  poReceipts?: PoReceipt[];
  onDecide: (next: PlanDecision) => Promise<void> | void;
  /** Put the line back to undecided. Its own callback rather than a decision field,
   *  because undecided is the ABSENCE of a decision and must not become one. */
  onClear: () => Promise<void> | void;
}) {
  // Both writes go through here so a rejection always toasts, whichever control fired it
  // (the Accept button, Adjust's own Record, or a grouped fan-out that partly failed).
  const decide = async (next: PlanDecision) => {
    try {
      await onDecide(next);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not record the decision.');
    }
  };
  const clear = async () => {
    try {
      await onClear();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not clear the decision.');
    }
  };
  // The engine's own composition. `order_qty` is frequently fractional on real data
  // (a demand rate times a horizon); rounded UP, never down - down is a deliberate
  // under-buy of a shortage we just calculated.
  const needed = Math.ceil(line.order_qty);
  const stockQty = cover.coverQty;
  const afterStock = stockQty > 0 ? cover.buyQty : needed;
  const poQty = poReceipts.reduce((t, r) => t + r.remaining, 0);
  const { usePo: suggestedPo, buy: rawBuy } = poOffset(afterStock, poQty);
  // MoQ and the order multiple are the supplier's rules, not the ledger's: a buy is rounded
  // wherever it is recorded, or the same row lands on 14 from this button and 20 from the
  // ledger. The LABEL reads the rounded figure too - a button that says 14 and records 20 is
  // the worse half of the bug.
  const suggestedBuy = roundBuyQty(rawBuy, line.order_qty_inputs);

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
  //
  // SHORT on purpose (captain, round 2): the source codes used to ride inside the label
  // ("Stock 15 (BRW-BB, PJ-SR) + Buy 182"), which grew with every location and truncated
  // before the buy figure - the one number the button is asking about. Where the stock came
  // from moved to the hover table, where it has room to be a list.
  const summary = (d: PlanDecision, decided = false): string => {
    if (d.skip) return 'Skipped';
    const parts: string[] = [];
    if ((d.stock?.qty ?? 0) > 0) parts.push(`Stock ${fmtInt(d.stock!.qty)}`);
    if ((d.po ?? 0) > 0) parts.push(`PO ${fmtInt(d.po!)}`);
    if ((d.buy ?? 0) > 0) parts.push(`${decided ? 'Bought' : 'Buy'} ${fmtInt(d.buy!)}`);
    return parts.length ? parts.join(' + ') : 'Nothing';
  };

  if (decision) {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5">
        {decision.skip ? (
          <X className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <Check className="size-3.5 shrink-0 text-scm-incoming" aria-hidden />
        )}
        {decision.skip ? (
          <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
            {summary(decision, true)}
          </span>
        ) : (
          <HoverCard openDelay={120}>
            {/* A button, not a span: a hover card is also a FOCUS card, and a decided row's
                breakdown has to be reachable without a mouse. The `title` stays because the
                text truncates - the tooltip is what a narrow column leaves the reader. */}
            <HoverCardTrigger asChild>
              <button
                type="button"
                className="min-w-0 flex-1 truncate text-start text-sm text-muted-foreground"
                title={summary(decision, true)}
              >
                {summary(decision, true)}
              </button>
            </HoverCardTrigger>
            <HoverCardContent className="w-56 p-3" align="start">
              <CoverBreakdownTable
                title={`${line.sku} - decided`}
                sources={decision.stock?.sources ?? []}
                poQty={decision.po ?? 0}
                buyQty={decision.buy ?? 0}
                buyLabel="Bought"
              />
            </HoverCardContent>
          </HoverCard>
        )}
        <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-xs" onClick={() => void clear()}>
          Change
        </Button>
      </div>
    );
  }

  const canAccept = line.purchasable && (suggestedBuy > 0 || stockQty > 0 || suggestedPo > 0);
  // S16: a grouped row whose members disagree - some decided differently, or some decided
  // and others have not. Read only when nobody has already been read as decided above, so
  // it never appears alongside the settled row it would otherwise contradict.
  const mixedNotice = mixed ? (
    <p className="text-2xs font-medium text-amber-600">
      Mixed across locations - deciding here sets every one of them the same way.
    </p>
  ) : null;

  // What used to be the separate "Suggested action" column: the notes a buyer needs beyond
  // the mix itself. Quiet, underneath the button, never a second place to look for them.
  //
  // P6 (captain, 25 Aug): the trend advisory ("Consider 490 more - orders rose 3233%") is NOT
  // one of them. A percentage off a tiny base shouts a number nobody would act on, next to the
  // button that IS the decision. The trend still has its say, in the trajectory popover on the
  // SO column, where the demand it judges lives and the whole series is there to read it with.
  //
  // A cover offer on a project line is purchasing superseding CS: the inquiry said buy it
  // all, and the engine found stock CS did not use. Said out loud, because a quiet
  // disagreement with CS reads as the engine miscounting.
  const crossing = cover.sources.some((s) => s.cross_segment);
  const supersede =
    line.rec.segment === 'project' && cover.coverQty > 0 ? `CS asked to buy ${fmtInt(needed)}` : null;

  return (
    <div className="min-w-0 space-y-1">
      {mixedNotice}
      <div className="flex flex-wrap items-center gap-1.5">
        {/* The loudest thing in the row: this button IS the decision. Its detail lives in
            the hover table beside it, never in a `title` sentence. */}
        <HoverCard openDelay={120}>
          <HoverCardTrigger asChild>
            <Button
              size="sm"
              className="h-8 px-2"
              onClick={() => void decide(suggested)}
              disabled={!canAccept}
              aria-label={`Accept for ${line.sku}: ${summary(suggested)}`}
            >
              <Check className="size-3.5 shrink-0" />
              <span className="max-w-44 truncate">{summary(suggested)}</span>
            </Button>
          </HoverCardTrigger>
          <HoverCardContent className="w-56 p-3" align="start">
            <CoverBreakdownTable
              title={`Accept for ${line.sku}`}
              sources={suggested.stock?.sources ?? []}
              poQty={suggestedPo}
              buyQty={suggestedBuy}
            />
            {suggestedPo > 0 ? (
              <p className="mt-2 text-2xs text-muted-foreground">
                {`Already ordered: ${describePoBook(poReceipts).join(' ')}`}
              </p>
            ) : null}
          </HoverCardContent>
        </HoverCard>
        {line.purchasable ? (
          <AdjustMixture
            line={line}
            suggested={suggested}
            stockMax={stockQty}
            poMax={poQty}
            cover={cover}
            onDecide={decide}
          />
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 px-2"
          onClick={() => void decide({ skip: true })}
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
  onDecide: (next: PlanDecision) => Promise<void> | void;
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
    const poQty = Math.min(num(po), poMax);
    // Typed by hand, rounded all the same: the supplier's MoQ and order multiple do not stop
    // applying because the buyer overrode the mixture (review finding 1, round 2).
    const buyQty = roundBuyQty(num(buy), line.order_qty_inputs);
    // Stock keeps its per-bin split, scaled down from the front when the buyer takes less
    // than offered: the nearest bins were ranked first, so they are kept first. The scaling
    // goes through the SAME helper the ledger's per-location inputs use, so a total typed
    // here and quantities typed there can never produce a different split.
    const edited = applySourceEdits(cover, sourceEditsForTotal(cover, Math.min(num(stock), stockMax)));
    const sources = edited.sources.map((s) => ({
      warehouse_id: s.warehouse_id,
      warehouse_code: s.warehouse_code,
      qty: s.qty,
    }));
    void onDecide({
      ...(buyQty > 0 ? { buy: buyQty } : {}),
      ...(edited.coverQty > 0 ? { stock: { qty: edited.coverQty, sources } } : {}),
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
          {/* Only where there IS a PO to use. A project row never has one (P8: its purchase
              order is consumed by the Order Inquiry's links, so offering it here would net
              the same quantity twice), and a retail row with an empty book has nothing to
              offer either - both used to render an input that could only ever read 0 and
              could not be typed into. */}
          {poMax > 0 ? (
            <label className="flex items-center justify-between gap-2">
              <span>From PO book (max {fmtInt(poMax)})</span>
              <Input
                type="number" min={0} max={poMax} inputMode="numeric"
                className="h-7 w-20 text-right tabular-nums"
                value={po} onChange={(e) => setPo(e.target.value)}
                aria-label="Units from the PO book"
              />
            </label>
          ) : null}
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
