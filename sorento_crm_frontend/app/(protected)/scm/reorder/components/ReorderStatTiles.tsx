'use client';

import { PackageX, ShoppingCart, Wallet } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { fmtInt, fmtMoney } from '../../lib/format';

/** Which recommendation set the plan view is filtered to. Cash impact is a stat,
 *  not a view, so it never appears here. */
export type ReorderPlanView = 'buy' | 'disposition';

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
 * SCM M8 summary cards for today's plan (M8-C0): exactly three - Buy,
 * Stock allocation, Cash impact. Buy and Stock allocation are clickable FILTERS
 * that switch the plan table between the buy cash co-pilot and the read-only
 * allocation list (the selected card shows an active ring); Cash impact is a stat
 * only. The Stock allocation count is ACTIONABLE dispositions only (Discontinue /
 * Promote); FYI "hold" lines are excluded and shown as a muted "N on hold" sub-label
 * (M8-F18). The internal view key stays `disposition` (M8-C12 relabels the UI only).
 * The prior Today's-plan / Stock-warning / Within-budget / Over-budget cards are gone:
 * within/over counts live in the table section headers, and stock warning moved
 * to the SCM dashboard (M8-B). Prototype: counts are mock.
 */
export function ReorderStatTiles({
  buyCount,
  dispositionCount,
  cashTotal,
  activeView,
  onSelectView,
}: {
  buyCount: number;
  /** ACTIONABLE dispositions only (Discontinue / Promote) - hold lines are excluded
   *  from the plan entirely and are NOT surfaced here (they carry no action). */
  dispositionCount: number;
  cashTotal: number;
  activeView: ReorderPlanView;
  onSelectView: (view: ReorderPlanView) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
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
      <Tile label="Cash impact" value={fmtMoney(cashTotal)} icon={Wallet} />
    </div>
  );
}
