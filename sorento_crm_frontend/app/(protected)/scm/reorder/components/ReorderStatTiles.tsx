'use client';

import { CheckCircle2, Wallet } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { fmtInt, fmtMoney } from '../../lib/format';

/**
 * Which recommendation set the plan view is filtered to. Cash impact is a stat, not a
 * view, so it never appears here. `needs_level` and `disposition` (Stock allocation) are
 * NOT views here either (user feedback, 2026-08-12: "I don't really need these" tiles) -
 * both are already reachable as a Status filter on the one grid (`buy`), so removing the
 * shortcut tile lost nothing. `order_summary` / `plan_exceptions` / `po_worklist` are
 * genuinely separate reports with no row in the grid to filter to, so THEIR entry points
 * moved to a quiet action in the grid's own toolbar (`PlanLinesGrid`'s secondary actions,
 * next to Filters / Columns / Export) instead of disappearing.
 */
export type ReorderPlanView = 'buy' | 'order_summary' | 'plan_exceptions' | 'po_worklist';

function Tile({
  label,
  value,
  subLabel,
  icon: Icon,
  valueClass,
  iconClass,
}: {
  label: string;
  value: string;
  subLabel?: string;
  icon: typeof Wallet;
  valueClass?: string;
  iconClass?: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 text-xs font-medium text-muted-foreground" title={label}>
          {label}
        </div>
        <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted', iconClass)}>
          <Icon className="size-4.5" aria-hidden />
        </span>
      </div>
      <div
        title={value}
        className={cn(
          'mt-1 w-full min-w-0 truncate whitespace-nowrap text-2xl font-semibold tabular-nums tracking-tight',
          valueClass,
        )}
      >
        {value}
      </div>
      {subLabel ? (
        <div className="mt-0.5 w-full min-w-0 truncate text-2xs text-muted-foreground" title={subLabel}>
          {subLabel}
        </div>
      ) : null}
    </Card>
  );
}

/**
 * The PRIMARY tile (user markup, 2026-08-12): "I want the decision to be emphasized ... so
 * they can decide until all outstanding decisions are cleared." Replaces the Buy / Covered by
 * stock tiles, which reported a STATUS classification the user said he doubted ("a line can
 * be buy + PO + SPO + use stock in any combination ... I go straight to the table"). Progress
 * against decisions taken is unambiguous in a way a status count never was: every line counts
 * exactly once, whichever mixture it was decided as.
 *
 * Clicking it narrows the grid to undecided lines, same mechanism as every other tile here -
 * a filter, never a navigation.
 */
function DecisionProgressTile({
  decided,
  total,
  active,
  onClick,
}: {
  decided: number;
  total: number;
  active: boolean;
  onClick?: () => void;
}) {
  const pct = total > 0 ? Math.round((decided / total) * 100) : 0;
  const complete = total > 0 && decided === total;
  const subLabel =
    total === 0 ? 'nothing to decide yet' : complete ? `All ${fmtInt(total)} decided` : `${fmtInt(total - decided)} left to decide`;
  const clickable = !!onClick;

  return (
    <Card
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      aria-pressed={clickable ? active : undefined}
      title={clickable ? 'Show only lines still to decide' : undefined}
      className={cn(
        'p-4 sm:col-span-2',
        clickable &&
          'cursor-pointer transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active && 'ring-2 ring-inset ring-primary',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 text-xs font-medium text-muted-foreground">Decisions</div>
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted',
            complete && 'bg-scm-incoming-soft text-scm-incoming',
          )}
        >
          <CheckCircle2 className="size-4.5" aria-hidden />
        </span>
      </div>
      <div className="mt-1 w-full min-w-0 truncate text-2xl font-semibold tabular-nums tracking-tight">
        {`${fmtInt(decided)} of ${fmtInt(total)} made`}
      </div>
      <Progress value={pct} className="mt-2" indicatorClassName={complete ? 'bg-scm-incoming' : undefined} />
      <div className="mt-1 w-full min-w-0 truncate text-2xs text-muted-foreground">{subLabel}</div>
    </Card>
  );
}

/**
 * SCM M8 summary cards for today's plan, reworked around DECISION PROGRESS (user markup,
 * 2026-08-12): "I want the decision to be emphasized ... so they can decide until all
 * outstanding decisions are cleared." The old Buy / Covered by stock tiles counted a STATUS
 * the user said he no longer trusted at a glance - a line can be buy + PO + SPO + use stock
 * in any combination, so "Buy 31" never matched what the table actually showed. They are
 * gone. The PRIMARY tile now reports how much of the plan has actually been decided, and
 * Cash impact splits into what is ACTUALLY committed (the decided buys) versus what EVERY
 * suggestion would cost if accepted as-is - two different numbers the single old tile
 * conflated.
 *
 * The secondary row (Needs a level, Stock allocation, Order summary, Plan exceptions, PO
 * worklist) is gone entirely (direct user feedback, 2026-08-12: "I don't really need
 * these"). It is not a loss of reach: Needs a level and Stock allocation are Status values
 * on the same grid these tiles used to shortcut into, still one Filters click away; Order
 * summary, Plan exceptions and PO worklist are separate reports whose entry point moved to
 * a quiet action in the grid's toolbar rather than disappearing (see `PlanLinesGrid`).
 */
export function ReorderStatTiles({
  decided,
  total,
  cashCommitted,
  cashTotal,
  undecidedFilterActive = false,
  onToggleUndecidedFilter,
}: {
  /** Lines the buyer has settled, whichever way (buy, stock, PO, skip - any mixture). */
  decided: number;
  /** Every line on the plan, decided or not. */
  total: number;
  /** Sum of the buy cost on every DECIDED line - what is actually committed so far. */
  cashCommitted: number;
  /** What EVERY suggestion would cost if every one of them were accepted as offered - the
   *  existing cash-impact figure, unrelated to what has actually been decided. */
  cashTotal: number;
  /** Whether the grid is currently narrowed to undecided lines by the Decisions tile. */
  undecidedFilterActive?: boolean;
  onToggleUndecidedFilter?: () => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <DecisionProgressTile
        decided={decided}
        total={total}
        active={undecidedFilterActive}
        onClick={onToggleUndecidedFilter}
      />
      <Tile
        label="Cash committed so far"
        value={fmtMoney(cashCommitted)}
        icon={Wallet}
        valueClass="text-scm-incoming"
        iconClass="bg-scm-incoming-soft text-scm-incoming"
      />
      <Tile label="Cash if all accepted" value={fmtMoney(cashTotal)} icon={Wallet} />
    </div>
  );
}
