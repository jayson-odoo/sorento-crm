'use client';

import { AlertTriangle, PackageX, ShoppingCart, Wallet } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { fmtInt, fmtMoney } from '../../lib/format';
import type { ReorderRecType, ReorderRunSummary } from '../types/reorder.types';

function Tile({
  label,
  value,
  icon: Icon,
  valueClass,
  iconClass,
  filterType,
  active,
  activeRingClass,
  onToggle,
}: {
  label: string;
  value: string;
  icon: typeof Wallet;
  valueClass?: string;
  iconClass?: string;
  /** When set, the whole card toggle-filters the grid to this recommendation type. */
  filterType?: ReorderRecType;
  active?: boolean;
  activeRingClass?: string;
  onToggle?: (type: ReorderRecType) => void;
}) {
  const clickable = !!filterType && !!onToggle;
  const activate = () => filterType && onToggle?.(filterType);
  return (
    <Card
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? activate : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                activate();
              }
            }
          : undefined
      }
      title={clickable ? (active ? `Clear ${label} filter` : `Filter to ${label}`) : undefined}
      aria-pressed={clickable ? active : undefined}
      className={cn(
        'p-4',
        clickable &&
          'cursor-pointer transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active && cn('ring-2 ring-inset', activeRingClass ?? 'ring-primary'),
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 truncate text-xs font-medium text-muted-foreground">{label}</div>
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted',
            iconClass,
          )}
        >
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
    </Card>
  );
}

/** Roll-up tiles for a completed run: # buy, # disposition, # exceptions, cash.
 *  The three count tiles toggle-filter the results grid by type (like the M2
 *  dashboard health tiles); the cash tile stays non-interactive. */
export function ReorderStatTiles({
  summary,
  activeType,
  onToggle,
}: {
  summary: ReorderRunSummary;
  /** Currently active grid type filter ('' = none) — drives the selected ring. */
  activeType: string;
  onToggle: (type: ReorderRecType) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Tile
        label="Buy recommendations"
        value={fmtInt(summary.buy_count)}
        icon={ShoppingCart}
        valueClass="text-scm-incoming"
        iconClass="bg-scm-incoming-soft text-scm-incoming"
        filterType="buy"
        active={activeType === 'buy'}
        activeRingClass="ring-scm-incoming"
        onToggle={onToggle}
      />
      <Tile
        label="Dispositions"
        value={fmtInt(summary.disposition_count)}
        icon={PackageX}
        valueClass="text-scm-overstock"
        iconClass="bg-scm-overstock-soft text-scm-overstock"
        filterType="disposition"
        active={activeType === 'disposition'}
        activeRingClass="ring-scm-overstock"
        onToggle={onToggle}
      />
      <Tile
        label="No-supplier exceptions"
        value={fmtInt(summary.exception_count)}
        icon={AlertTriangle}
        valueClass="text-scm-stockout"
        iconClass="bg-scm-stockout-soft text-scm-stockout"
        filterType="exception"
        active={activeType === 'exception'}
        activeRingClass="ring-scm-stockout"
        onToggle={onToggle}
      />
      <Tile
        label="Total cash impact"
        value={fmtMoney(summary.total_cash_impact)}
        icon={Wallet}
      />
    </div>
  );
}
