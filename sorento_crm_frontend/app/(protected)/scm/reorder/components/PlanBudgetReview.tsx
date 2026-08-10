'use client';

import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Scissors } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { fmtInt, fmtMoney } from '../../lib/format';
import type { PlanLine } from '../lib/planLine';
import { budgetVerdict, proposeCuts, type PlanDecisionMap, type PlanTotals } from '../lib/planDecisions';

/**
 * The money question, asked AFTER the decisions.
 *
 * > "during planning, I don't even need to specify the budget, I should check my budget at the
 * >  end of decisions made for all products, then I check whether it is within my budget, if
 * >  not, what can be done"
 *
 * So the budget lives here and nowhere else. Until a figure is typed there is no verdict, and
 * the panel says what has been decided rather than implying the plan fits inside nothing.
 *
 * Two counts are load-bearing and both are stated before any total:
 *
 * * **undecided** - work not yet done. Without it a half-read plan totals up like a finished
 *   one and the buyer signs off on a number that is missing most of the list.
 * * **no price** - decided buys we cannot cost. They are real orders that simply cannot be
 *   weighed, so they are reported beside the total and never folded into it as zero.
 */
export function PlanBudgetReview({
  lines,
  decisions,
  totals,
}: {
  lines: PlanLine[];
  decisions: PlanDecisionMap;
  totals: PlanTotals;
}) {
  const [budgetText, setBudgetText] = useState('');
  const budget = budgetText.trim() === '' ? null : Number(budgetText);
  const verdict = budgetVerdict(totals, budget);
  const cuts = proposeCuts(lines, decisions, budget);

  return (
    <Card className="p-4">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <div>
            <div className="text-2xs uppercase tracking-wide text-muted-foreground">Decided</div>
            <div className="text-lg font-semibold tabular-nums">
              {fmtInt(totals.decided)}
              <span className="ms-1 text-sm font-normal text-muted-foreground">
                of {fmtInt(totals.decided + totals.undecided)}
              </span>
            </div>
          </div>
          <div>
            <div className="text-2xs uppercase tracking-wide text-muted-foreground">Buying</div>
            <div className="text-lg font-semibold tabular-nums">
              {fmtInt(totals.buying)}
              <span className="ms-1 text-sm font-normal text-muted-foreground">
                lines, {fmtInt(totals.units)} units
              </span>
            </div>
          </div>
          <div>
            <div className="text-2xs uppercase tracking-wide text-muted-foreground">Cost</div>
            <div className="text-lg font-semibold tabular-nums">{fmtMoney(totals.cost)}</div>
          </div>
          {totals.unpriced > 0 ? (
            <div>
              <div className="text-2xs uppercase tracking-wide text-muted-foreground">No price</div>
              <div className="text-lg font-semibold tabular-nums text-scm-overstock">
                {fmtInt(totals.unpriced)}
              </div>
            </div>
          ) : null}
        </div>

        {totals.undecided > 0 ? (
          <p className="text-xs text-muted-foreground">
            {fmtInt(totals.undecided)} line{totals.undecided === 1 ? '' : 's'} still to decide, so
            this total is not the whole plan yet.
          </p>
        ) : null}

        {totals.unpriced > 0 ? (
          <p className="text-xs text-muted-foreground">
            {fmtInt(totals.unpriced)} of the lines you are buying{' '}
            {totals.unpriced === 1 ? 'has' : 'have'} no price, so{' '}
            {totals.unpriced === 1 ? 'it is' : 'they are'} not in the cost above and cannot be
            checked against a budget.
          </p>
        ) : null}

        <div className="flex flex-wrap items-end gap-3 border-t pt-3">
          <div className="space-y-1">
            <Label htmlFor="plan-budget" className="text-xs text-muted-foreground">
              Budget for this round
            </Label>
            <div className="flex items-center gap-1">
              <span className="text-xs text-muted-foreground">RM</span>
              <Input
                id="plan-budget"
                inputMode="numeric"
                value={budgetText}
                onChange={(e) => setBudgetText(e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="Enter to check"
                className="h-9 w-36 text-right tabular-nums"
              />
            </div>
          </div>

          {verdict.budget === null ? null : verdict.over ? (
            <div className="flex items-center gap-2 text-sm text-scm-stockout">
              <AlertTriangle className="size-4 shrink-0" aria-hidden />
              <span>
                Over by <span className="font-semibold tabular-nums">{fmtMoney(Math.abs(verdict.remaining ?? 0))}</span>
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-scm-incoming">
              <CheckCircle2 className="size-4 shrink-0" aria-hidden />
              {/* Qualified whenever a decided buy could not be priced. A clean "Within budget"
                  there would be arithmetically true and misleading: the missing lines could
                  cost anything, so the verdict covers only what we can actually add up. */}
              <span>
                {verdict.unpriced > 0 ? 'Within budget on what we can price' : 'Within budget'},{' '}
                <span className="font-semibold tabular-nums">{fmtMoney(verdict.remaining ?? 0)}</span> left
              </span>
            </div>
          )}
        </div>

        {cuts.length > 0 ? (
          <div className="rounded-lg border border-scm-overstock/40 bg-scm-overstock-soft/30 p-3">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium">
              <Scissors className="size-4" aria-hidden />
              Dropping these {fmtInt(cuts.length)} would bring it inside the budget
            </div>
            {/* A proposal, worst-ranked first, not an action. Each is the buyer's to take or
                leave - the allocator advises here, it does not decide. */}
            <ul className="space-y-1">
              {cuts.slice(0, 8).map((l) => (
                <li key={l.id} className="flex justify-between gap-3 text-xs">
                  <span className="truncate" title={`${l.sku} at ${l.warehouse}`}>
                    {l.sku}
                    <span className="text-muted-foreground"> at {l.warehouse}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    #{l.rankOrder ?? '-'}
                  </span>
                </li>
              ))}
            </ul>
            {cuts.length > 8 ? (
              <p className="mt-1 text-2xs text-muted-foreground">
                and {fmtInt(cuts.length - 8)} more.
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
