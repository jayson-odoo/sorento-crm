'use client';

import { useState } from 'react';
import { AlertTriangle, Ban, Layers, TrendingDown, Truck, Wallet } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtDate, fmtInt, fmtMoney } from '../lib/format';
import type { ScmFilters } from '../services/scmDashboardService';
import type { HealthState, ScmRollups } from '../types/scm.types';
import { ProductListDialog } from './ProductListDialog';

interface DrillTarget {
  title: string;
  status: HealthState;
}

interface TileProps {
  label: string;
  value: string;
  icon: typeof Wallet;
  /** Relocated from the card face into a tooltip on the icon (AC: less text). */
  hint: string;
  valueClass?: string;
  iconClass?: string;
  deferred?: boolean;
  /** When set, the big number becomes a button that opens the drill-down popup. */
  onDrill?: () => void;
  /** When set, the card BODY toggles this health filter on the dashboard. */
  filterStatus?: HealthState;
  active?: boolean;
  activeRingClass?: string;
  onToggleFilter?: (status: HealthState) => void;
}

function Tile({
  label,
  value,
  icon: Icon,
  hint,
  valueClass,
  iconClass,
  deferred,
  onDrill,
  filterStatus,
  active,
  activeRingClass,
  onToggleFilter,
}: TileProps) {
  const filterable = !!filterStatus && !!onToggleFilter;
  const toggle = () => filterStatus && onToggleFilter?.(filterStatus);

  return (
    <Card
      role={filterable ? 'button' : undefined}
      tabIndex={filterable ? 0 : undefined}
      onClick={filterable ? toggle : undefined}
      onKeyDown={
        filterable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggle();
              }
            }
          : undefined
      }
      title={filterable ? `Filter to ${label}` : undefined}
      aria-pressed={filterable ? active : undefined}
      className={cn(
        'p-4',
        deferred && 'opacity-70',
        filterable &&
          'cursor-pointer transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active && cn('ring-2 ring-inset', activeRingClass ?? 'ring-primary'),
      )}
    >
      {/* Top row: label (left) + icon (right) — icon no longer shares the
          value's row, so a long value can never collide with it. */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 truncate text-xs font-medium text-muted-foreground">{label}</div>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              role="img"
              aria-label={hint}
              onClick={(e) => e.stopPropagation()}
              className={cn(
                'flex size-9 shrink-0 cursor-help items-center justify-center rounded-lg bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                iconClass,
              )}
            >
              <Icon className="size-4.5" aria-hidden />
            </span>
          </TooltipTrigger>
          <TooltipContent>{hint}</TooltipContent>
        </Tooltip>
      </div>

      {/* Value row: full tile width, no wrap. min-w-0 + truncate lets an
          extreme value shrink gracefully instead of overflowing. */}
      {onDrill ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDrill();
          }}
          aria-label={`${label}: ${value}. View products`}
          title={value}
          className={cn(
            'mt-1 block w-full min-w-0 cursor-pointer truncate whitespace-nowrap rounded-sm text-start text-2xl font-semibold tabular-nums tracking-tight underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            valueClass,
          )}
        >
          {value}
        </button>
      ) : (
        <div
          title={value}
          className={cn(
            'mt-1 w-full min-w-0 truncate whitespace-nowrap text-2xl font-semibold tabular-nums tracking-tight',
            deferred && 'text-muted-foreground',
            valueClass,
          )}
        >
          {value}
        </div>
      )}
    </Card>
  );
}

export function RollupTiles({
  data,
  isLoading,
  isError,
  filters,
  onViewInList,
  activeStatus,
  onToggleFilter,
}: {
  data?: ScmRollups;
  isLoading: boolean;
  isError: boolean;
  /** Current dashboard filters — scope the drill-down popups. */
  filters: ScmFilters;
  /** Deep-link into the Product perspective pre-filtered to a health status. */
  onViewInList: (status: HealthState) => void;
  /** Currently active health filter (shared with the legend + warehouse cards). */
  activeStatus?: HealthState | null;
  /** Toggle a health filter from a stat card body. */
  onToggleFilter: (status: HealthState) => void;
}) {
  const [drill, setDrill] = useState<DrillTarget | null>(null);

  if (isError) {
    return (
      <Card className="p-4 text-sm text-scm-stockout">
        Couldn&apos;t load roll-up figures. Retry from the toolbar.
      </Card>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="p-4">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-2 h-7 w-20" />
            <Skeleton className="mt-2 h-3 w-16" />
          </Card>
        ))}
      </div>
    );
  }

  // M2 tile — real Σ stock_valuation where days-of-cover > overstock_days. The
  // "Below reorder point" figure stays DEFERRED to M3 (needs a real reorder point).
  const overstockValuation = data.overstock_valuation;

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Tile
          label="Total stock valuation"
          value={fmtMoney(data.total_stock_valuation)}
          icon={Wallet}
          hint={
            data.valuation_missing_cost_count > 0
              ? `${data.valuation_missing_cost_count} SKU without cost — excluded from valuation`
              : 'On-hand × cost price'
          }
        />
        <Tile
          label="Dead-stock valuation"
          value={fmtMoney(data.dead_stock_valuation)}
          icon={Ban}
          valueClass="text-scm-dead"
          iconClass="bg-scm-dead-soft text-scm-dead"
          hint="No movement beyond the dead-stock window"
          filterStatus="dead"
          active={activeStatus === 'dead'}
          activeRingClass="ring-scm-dead"
          onToggleFilter={onToggleFilter}
          onDrill={() => setDrill({ title: 'Dead stock', status: 'dead' })}
        />
        <Tile
          label="Stockouts"
          value={fmtInt(data.stockout_count)}
          icon={AlertTriangle}
          valueClass="text-scm-stockout"
          iconClass="bg-scm-stockout-soft text-scm-stockout"
          hint="On-hand = 0"
          filterStatus="stockout"
          active={activeStatus === 'stockout'}
          activeRingClass="ring-scm-stockout"
          onToggleFilter={onToggleFilter}
          onDrill={() => setDrill({ title: 'Stockouts', status: 'stockout' })}
        />
        <Tile
          label="Incoming POs"
          value={fmtInt(data.incoming_po_count)}
          icon={Truck}
          valueClass="text-scm-incoming"
          iconClass="bg-scm-incoming-soft text-scm-incoming"
          hint={
            data.incoming_po_next_eta
              ? `Next ETA ${fmtDate(data.incoming_po_next_eta)}`
              : 'None inbound'
          }
          filterStatus="incoming"
          active={activeStatus === 'incoming'}
          activeRingClass="ring-scm-incoming"
          onToggleFilter={onToggleFilter}
          onDrill={() => setDrill({ title: 'Incoming purchase orders', status: 'incoming' })}
        />
        {/* DEFERRED to M3 — a real reorder point needs demand × lead time +
            safety stock, which doesn't exist yet, so this tile is greyed and
            inert (no drill, no card-filter) rather than showing a faked count. */}
        <Tile
          label="Below reorder point"
          value={EM_DASH}
          icon={TrendingDown}
          hint="Available in M3 — needs reorder point"
          deferred
        />
        <Tile
          label="Overstock valuation"
          value={fmtMoney(overstockValuation)}
          icon={Layers}
          valueClass="text-scm-overstock"
          iconClass="bg-scm-overstock-soft text-scm-overstock"
          hint="Stock value over the days-of-cover ceiling"
          filterStatus="overstock"
          active={activeStatus === 'overstock'}
          activeRingClass="ring-scm-overstock"
          onToggleFilter={onToggleFilter}
          onDrill={() => setDrill({ title: 'Overstock', status: 'overstock' })}
        />
      </div>

      <ProductListDialog
        open={!!drill}
        onOpenChange={(o) => !o && setDrill(null)}
        title={drill?.title ?? ''}
        filters={filters}
        target={drill ? { status: drill.status } : null}
        onViewInList={drill ? () => onViewInList(drill.status) : undefined}
      />
    </>
  );
}
