'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Boxes, Info, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt, fmtMoney } from '../lib/format';
import { healthMeta } from '../lib/health';
import type { ScmFilters } from '../services/scmDashboardService';
import type { HealthState, WarehouseHealth } from '../types/scm.types';
import { CompositionBar, HealthLegend, StateChip } from './HealthIndicators';
import { ProductListDialog } from './ProductListDialog';
import { ScmPager } from './ScmPager';

/** Attention weight — stockout warehouses float to the top of the grid. */
const RANK: Record<string, number> = { stockout: 0, dead: 1, low: 2, overstock: 3, incoming: 4, healthy: 5 };

/** Cards per page — 12 divides the 3- and 4-column grid cleanly. */
const WH_PAGE_SIZE = 12;

interface DrillTarget {
  title: string;
  warehouse: string;
  status?: HealthState;
}

function WarehouseTile({
  wh,
  active,
  onOpenDialog,
  onToggle,
}: {
  wh: WarehouseHealth;
  active: boolean;
  onOpenDialog: (target: DrillTarget) => void;
  onToggle: (warehouse: string) => void;
}) {
  const meta = healthMeta(wh.worst_state);
  const needsAction = wh.worst_state === 'stockout' || wh.worst_state === 'dead';

  const openCount = (status: HealthState, label: string) =>
    onOpenDialog({
      title: `${label} — ${wh.warehouse_name}`,
      warehouse: wh.warehouse_code,
      status,
    });

  const openAll = () =>
    onOpenDialog({
      title: `Products — ${wh.warehouse_name}`,
      warehouse: wh.warehouse_code,
    });

  return (
    <Card
      role="button"
      tabIndex={0}
      aria-pressed={active}
      onClick={() => onToggle(wh.warehouse_code)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle(wh.warehouse_code);
        }
      }}
      title={
        active
          ? `Clear the ${wh.warehouse_name} filter`
          : `Filter to ${wh.warehouse_name} products`
      }
      className={cn(
        'relative cursor-pointer overflow-hidden p-4 pl-5 transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active && 'ring-2 ring-inset ring-primary',
        !active && needsAction && 'ring-1 ring-inset',
        !active && wh.worst_state === 'stockout' && 'ring-scm-stockout/30',
        !active && wh.worst_state === 'dead' && 'ring-scm-dead/30',
      )}
    >
      {/* Left accent bar = worst health state. */}
      <span className={cn('absolute inset-y-0 left-0 w-1.5', meta.solidClass)} aria-hidden />

      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className={cn('truncate font-semibold', needsAction && 'text-[0.95rem]')} title={wh.warehouse_name}>
            {wh.warehouse_name}
          </div>
          <div className="mt-1">
            <StateChip state={wh.worst_state} />
          </div>
        </div>
        <div className="flex items-start gap-2">
          <div className="text-right">
            <div className="text-2xs text-muted-foreground">Stock valuation</div>
            <div className="whitespace-nowrap font-semibold tabular-nums">
              {wh.stock_valuation === null ? (
                <span className="text-muted-foreground" title="No costed SKUs in this warehouse yet">
                  {EM_DASH}
                </span>
              ) : (
                fmtMoney(wh.stock_valuation)
              )}
            </div>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                className="size-7 shrink-0 text-muted-foreground"
                onClick={(e) => {
                  e.stopPropagation();
                  openAll();
                }}
                aria-label={`View products in ${wh.warehouse_name}`}
              >
                <Info className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>View products</TooltipContent>
          </Tooltip>
        </div>
      </div>

      <div className="mt-3">
        <CompositionBar composition={wh.composition} />
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <CountStat
          label="Stockout"
          value={wh.stockout_count}
          tone={wh.stockout_count > 0 ? 'text-scm-stockout' : undefined}
          onOpen={() => openCount('stockout', 'Stockouts')}
        />
        <CountStat
          label="Dead"
          value={wh.dead_count}
          tone={wh.dead_count > 0 ? 'text-scm-dead' : undefined}
          onOpen={() => openCount('dead', 'Dead stock')}
        />
        <CountStat
          label="Incoming"
          value={wh.incoming_po_count}
          tone={wh.incoming_po_count > 0 ? 'text-scm-incoming' : undefined}
          onOpen={() => openCount('incoming', 'Incoming')}
        />
      </div>
      <div className="mt-2 text-2xs text-muted-foreground">{fmtInt(wh.sku_count)} SKUs stocked</div>
    </Card>
  );
}

function CountStat({
  label,
  value,
  tone,
  onOpen,
}: {
  label: string;
  value: number;
  tone?: string;
  onOpen: () => void;
}) {
  const disabled = value === 0;
  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          onOpen();
        }}
        aria-label={`${value} ${label} — view products`}
        className={cn(
          'rounded-sm text-lg font-semibold tabular-nums underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          disabled ? 'cursor-default text-muted-foreground' : 'cursor-pointer hover:underline',
          tone,
        )}
      >
        {fmtInt(value)}
      </button>
      <div className="text-2xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function WarehouseHealthGrid({
  data,
  isLoading,
  isError,
  onRetry,
  filters,
  activeState,
  onToggleHealth,
  activeWarehouses,
  onToggleWarehouse,
  onViewProducts,
}: {
  data?: WarehouseHealth[];
  isLoading: boolean;
  isError: boolean;
  onRetry?: () => void;
  /** Current dashboard filters — scope the drill-down popups. */
  filters: ScmFilters;
  activeState?: HealthState | null;
  onToggleHealth: (state: HealthState) => void;
  activeWarehouses: string[];
  onToggleWarehouse: (warehouse: string) => void;
  onViewProducts: (warehouse: string, status?: HealthState) => void;
}) {
  const [dialog, setDialog] = useState<DrillTarget | null>(null);
  const [page, setPage] = useState(1);

  const sorted = useMemo(
    () => (data ? [...data].sort((a, b) => RANK[a.worst_state] - RANK[b.worst_state]) : []),
    [data],
  );

  // Reset to page 1 whenever the in-scope set changes (a filter / health chip /
  // search re-fetch hands us a new array reference).
  useEffect(() => {
    setPage(1);
  }, [data]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / WH_PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const paged = useMemo(
    () => sorted.slice((safePage - 1) * WH_PAGE_SIZE, safePage * WH_PAGE_SIZE),
    [sorted, safePage],
  );

  if (isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <div className="text-sm text-scm-stockout">Couldn&apos;t load warehouse health.</div>
        {onRetry ? (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="p-4">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="mt-2 h-4 w-20" />
            <Skeleton className="mt-3 h-1.5 w-full" />
            <Skeleton className="mt-3 h-10 w-full" />
          </Card>
        ))}
      </div>
    );
  }

  if (!sorted.length) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-muted">
          <Boxes className="size-6 text-muted-foreground" />
        </span>
        <div>
          <div className="font-medium">No warehouses in scope</div>
          <div className="mt-1 text-sm text-muted-foreground">
            Add a warehouse or widen the warehouse filter to see health tiles.
          </div>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/inventory-management/warehouses">
            <Plus className="size-4" />
            Manage warehouses
          </Link>
        </Button>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {paged.map((wh) => (
          <WarehouseTile
            key={wh.warehouse_code}
            wh={wh}
            active={activeWarehouses.includes(wh.warehouse_code)}
            onOpenDialog={setDialog}
            onToggle={onToggleWarehouse}
          />
        ))}
      </div>
      <ScmPager
        page={safePage}
        pageCount={pageCount}
        total={sorted.length}
        unit="warehouse"
        onPageChange={setPage}
      />
      <HealthLegend className="px-1" activeState={activeState} onToggle={onToggleHealth} />

      <ProductListDialog
        open={!!dialog}
        onOpenChange={(o) => !o && setDialog(null)}
        title={dialog?.title ?? ''}
        filters={filters}
        target={dialog ? { warehouse: dialog.warehouse, status: dialog.status ?? null } : null}
        onViewInList={
          dialog ? () => onViewProducts(dialog.warehouse, dialog.status) : undefined
        }
      />
    </div>
  );
}
