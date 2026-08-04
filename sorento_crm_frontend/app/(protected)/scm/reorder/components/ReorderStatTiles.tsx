'use client';

import {
  AlertTriangle,
  ClipboardList,
  FileSpreadsheet,
  PackageX,
  ShoppingCart,
  Wallet,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { fmtInt, fmtMoney } from '../../lib/format';

/** Which recommendation set the plan view is filtered to. Cash impact is a stat,
 *  not a view, so it never appears here. */
export type ReorderPlanView = 'buy' | 'disposition' | 'order_summary';

/** Shown instead of a count when nothing computes it yet. */
const UNKNOWN_VALUE = '-';
const UNKNOWN_SUBLABEL = 'not computed yet';

function Tile({
  label,
  value,
  subLabel,
  icon: Icon,
  valueClass,
  iconClass,
  active,
  activeRingClass,
  onClick,
}: {
  label: string;
  value: string;
  subLabel?: string;
  icon: typeof Wallet;
  valueClass?: string;
  iconClass?: string;
  active?: boolean;
  activeRingClass?: string;
  onClick?: () => void;
}) {
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
      title={clickable ? `Show ${label} recommendations` : undefined}
      className={cn(
        'p-4',
        clickable &&
          'cursor-pointer transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active && cn('ring-2 ring-inset', activeRingClass ?? 'ring-primary'),
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 truncate text-xs font-medium text-muted-foreground">{label}</div>
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
 * SCM M8 summary cards for today's plan (M8-C0), now five - Buy,
 * Stock allocation, Cash impact, Plan exceptions, PO worklist. Buy and Stock
 * allocation are clickable FILTERS
 * that switch the plan table between the buy cash co-pilot and the read-only
 * allocation list (the selected card shows an active ring); Cash impact is a stat
 * only. The Stock allocation count is ACTIONABLE dispositions only (Discontinue /
 * Promote); FYI "hold" lines are excluded and shown as a muted "N on hold" sub-label
 * (M8-F18). The internal view key stays `disposition` (M8-C12 relabels the UI only).
 * The prior Today's-plan / Stock-warning / Within-budget / Over-budget cards are gone:
 * within/over counts live in the table section headers, and stock warning moved
 * to the SCM dashboard (M8-B). Prototype: counts are mock.
 *
 * Plan exceptions and the PO worklist are TILES, not pages (AC-B9), so a count is
 * visible without navigating. They are stats for now, not clickable filters: the two
 * views themselves land in S4 (worklist) and S5 (exceptions), and a card that
 * switched to a view that does not exist yet would be worse than a plain count.
 *
 * Order summary (S3b, AC-C2.1) is the THIRD clickable view: the weekly sheet Mr Loo
 * decides order quantities on. Its count is the products still waiting for a
 * quantity, which is the only question he has when he opens it.
 */
export function ReorderStatTiles({
  buyCount,
  dispositionCount,
  cashTotal,
  planExceptionCount = null,
  poWorklistCount = null,
  orderSummaryPendingCount = null,
  activeView,
  onSelectView,
}: {
  buyCount: number;
  /** ACTIONABLE dispositions only (Discontinue / Promote) - hold lines are excluded
   *  from the plan entirely and are NOT surfaced here (they carry no action). */
  dispositionCount: number;
  cashTotal: number;
  /** Open plan exceptions waiting on a decision (S5). */
  /** Null when no engine computes it yet. NOT 0: zero reads as "nothing waiting". */
  planExceptionCount?: number | null;
  /** Decided buys still to be keyed into AutoCount (S4). */
  /** Null when no engine computes it yet. NOT 0: zero reads as "nothing left to key". */
  poWorklistCount?: number | null;
  /** Short products with no order quantity decided yet (S3b). */
  /** Null until the report has been read once. See the tile body for why it is
   *  not fetched eagerly. */
  orderSummaryPendingCount?: number | null;
  activeView: ReorderPlanView;
  onSelectView: (view: ReorderPlanView) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      <Tile
        label="Buy"
        value={fmtInt(buyCount)}
        icon={ShoppingCart}
        valueClass="text-scm-incoming"
        iconClass="bg-scm-incoming-soft text-scm-incoming"
        active={activeView === 'buy'}
        activeRingClass="ring-scm-incoming"
        onClick={() => onSelectView('buy')}
      />
      <Tile
        label="Stock allocation"
        value={fmtInt(dispositionCount)}
        icon={PackageX}
        valueClass="text-scm-overstock"
        iconClass="bg-scm-overstock-soft text-scm-overstock"
        active={activeView === 'disposition'}
        activeRingClass="ring-scm-overstock"
        onClick={() => onSelectView('disposition')}
      />
      <Tile
        label="Order summary"
        // Null until the report has actually been read. It used to render a hard-coded
        // mock constant of 2 against a real book of 317 undecided rows - the same defect
        // as the plan-exception tile, and worse for being plausible. The count is NOT
        // fetched eagerly to fill it: the report is the whole book, and pulling it on every
        // page load to populate one tile is a cost nobody asked for. Open the report and
        // the tile becomes true.
        value={
          orderSummaryPendingCount === null
            ? UNKNOWN_VALUE
            : fmtInt(orderSummaryPendingCount)
        }
        subLabel={
          orderSummaryPendingCount === null
            ? 'open to count'
            : orderSummaryPendingCount
              ? 'waiting on a quantity'
              : 'every planned item decided'
        }
        icon={FileSpreadsheet}
        active={activeView === 'order_summary'}
        onClick={() => onSelectView('order_summary')}
      />
      <Tile label="Cash impact" value={fmtMoney(cashTotal)} icon={Wallet} />
      {/* Both of these read "not computed" until their engines exist. A number here has to
          come from somewhere: a fabricated count is a decision made on invented data, and a
          0 is worse still, because "nothing waiting" is itself a claim. */}
      <Tile
        label="Plan exceptions"
        value={planExceptionCount === null ? UNKNOWN_VALUE : fmtInt(planExceptionCount)}
        subLabel={
          planExceptionCount === null
            ? UNKNOWN_SUBLABEL
            : planExceptionCount
              ? 'waiting on a decision'
              : 'nothing disagrees with placed supply'
        }
        icon={AlertTriangle}
        valueClass={planExceptionCount ? 'text-scm-stockout' : undefined}
        iconClass={planExceptionCount ? 'bg-scm-stockout-soft text-scm-stockout' : undefined}
      />
      <Tile
        label="PO worklist"
        value={poWorklistCount === null ? UNKNOWN_VALUE : fmtInt(poWorklistCount)}
        subLabel={
          poWorklistCount === null
            ? UNKNOWN_SUBLABEL
            : poWorklistCount
              ? 'not yet keyed into AutoCount'
              : 'nothing left to key'
        }
        icon={ClipboardList}
      />
    </div>
  );
}
