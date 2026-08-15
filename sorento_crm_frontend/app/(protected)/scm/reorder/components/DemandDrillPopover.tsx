'use client';

import { useState } from 'react';
import { AlertCircle, Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import { dayLabel } from '../lib/coverageTimeline';
import { useOrderSummaryDemand } from '../hooks/useSummaryOrder';
import type { OrderSummaryDemandKind } from '../types/summaryOrder.types';

/**
 * One aggregate on the Summary Order Report, opened behind an information icon
 * (AC-C2.2a).
 *
 * The row carries the total and nothing else. Preventing information fatigue is
 * a stated requirement, not a preference: the printed sheet Mr Loo works from
 * has one number per column, and a screen that inlines every contributing line
 * is a worse sheet, not a better one. So the aggregate is a figure with an icon
 * beside it, and the lines are fetched only when the icon is opened.
 *
 * Project demand decomposes into project, sales order, quantity and required
 * date (AC-C2.3). Dealer outstanding decomposes into dealer, sales order,
 * quantity and DAYS OUTSTANDING (AC-C2.4) - the column the printed sheet has no
 * room for, and the reason a 2-unit line that has waited 214 days outranks a
 * 96-unit line raised in May.
 *
 * **The ordering is the server's.** Dealer lines arrive worst-first and are
 * rendered in the order received, so the ageing a person reads is the ageing the
 * server computed. Nothing here re-sorts.
 */

const KIND_LABEL: Record<OrderSummaryDemandKind, string> = {
  project: 'Project demand',
  dealer: 'Dealer outstanding',
};

/** Ageing tone. Only the worst band is coloured, so the colour still means something. */
function ageTone(days: number): string {
  if (days >= 180) return 'text-scm-stockout';
  if (days >= 60) return 'text-scm-overstock';
  return 'text-muted-foreground';
}

export interface DemandDrillPopoverProps {
  productCode: string;
  productName?: string | null;
  kind: OrderSummaryDemandKind;
  /** The aggregate shown on the row. The drill's total must agree with it. */
  totalQty: number;
  /** How many lines are behind it, so the icon can be skipped when there are none. */
  lineCount: number;
  /** Opaque run key, passed through so a past week drills to that week's lines. */
  runId: string | null;
}

export function DemandDrillPopover({
  productCode,
  productName,
  kind,
  totalQty,
  lineCount,
  runId,
}: DemandDrillPopoverProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, error, refetch } = useOrderSummaryDemand(
    productCode,
    kind,
    runId,
    open,
  );

  // Nothing contributes, so there is nothing to open. The figure still renders.
  if (lineCount === 0) {
    return (
      <span className="tabular-nums" data-testid={`demand-total-${kind}`}>
        {fmtInt(totalQty)}
      </span>
    );
  }

  return (
    <span className="flex items-center justify-end gap-1">
      <span className="tabular-nums" data-testid={`demand-total-${kind}`}>
        {fmtInt(totalQty)}
      </span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            onClick={(e) => e.stopPropagation()}
            aria-label={`${KIND_LABEL[kind]} for ${productCode}, ${lineCount} ${
              lineCount === 1 ? 'line' : 'lines'
            }`}
            className="inline-flex shrink-0 items-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Info className="size-3.5" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent
            align="end"
            collisionPadding={8}
            onClick={(e) => e.stopPropagation()}
            className="w-[min(22rem,calc(100vw-2rem))] p-0"
          >
            <div className="flex flex-col gap-1 border-b px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 break-words">
                <div className="text-xs font-semibold">{KIND_LABEL[kind]}</div>
                <div className="text-2xs text-muted-foreground">
                  {productCode}
                  {productName ? ` · ${productName}` : ''}
                </div>
              </div>
              <Badge variant="secondary" appearance="light" size="xs" className="w-fit shrink-0">
                {fmtInt(totalQty)}
              </Badge>
            </div>

            {isLoading ? (
              <div className="space-y-2 p-3" aria-label="Loading contributing lines" aria-busy="true">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full rounded-md" />
                ))}
              </div>
            ) : isError || !data ? (
              <div className="flex flex-col items-center gap-2 p-4 text-center">
                <AlertCircle className="size-4 text-destructive" aria-hidden />
                <p className="text-2xs text-muted-foreground">
                  {error instanceof Error ? error.message : 'Failed to load the contributing lines.'}
                </p>
                <Button variant="outline" size="sm" onClick={() => void refetch()}>
                  Try again
                </Button>
              </div>
            ) : kind === 'project' ? (
              <ProjectLines drill={data} />
            ) : (
              <DealerLines drill={data} />
            )}
          </PopoverContent>
        </PopoverPortal>
      </Popover>
    </span>
  );
}

function EmptyLines({ children }: { children: React.ReactNode }) {
  return <div className="px-3 py-4 text-center text-2xs text-muted-foreground">{children}</div>;
}

function ProjectLines({
  drill,
}: {
  drill: NonNullable<ReturnType<typeof useOrderSummaryDemand>['data']>;
}) {
  if (drill.project_lines.length === 0) {
    return <EmptyLines>No project has committed this item.</EmptyLines>;
  }
  return (
    <div className="max-h-64 overflow-y-auto" data-testid="project-lines">
      {drill.project_lines.map((line, i) => (
        <div
          key={`${line.so_number}-${i}`}
          className="flex items-start justify-between gap-3 border-b px-3 py-2 text-sm last:border-b-0"
        >
          <div className="min-w-0">
            <div className="truncate font-medium" title={line.project_name}>
              {line.project_name}
            </div>
            <div className="truncate text-2xs text-muted-foreground">
              {line.so_number} · needed {line.required_date ? dayLabel(line.required_date) : 'no date'}
            </div>
          </div>
          <span className="shrink-0 tabular-nums">{fmtInt(line.qty)}</span>
        </div>
      ))}
    </div>
  );
}

function DealerLines({
  drill,
}: {
  drill: NonNullable<ReturnType<typeof useOrderSummaryDemand>['data']>;
}) {
  if (drill.dealer_lines.length === 0) {
    return <EmptyLines>No dealer order is outstanding on this item.</EmptyLines>;
  }
  return (
    <div className="max-h-64 overflow-y-auto" data-testid="dealer-lines">
      {drill.dealer_lines.map((line, i) => (
        <div
          key={`${line.so_number}-${i}`}
          className="flex items-start justify-between gap-3 border-b px-3 py-2 text-sm last:border-b-0"
        >
          <div className="min-w-0">
            <div className="truncate font-medium" title={line.dealer_name}>
              {line.dealer_name}
            </div>
            <div className="truncate text-2xs text-muted-foreground">
              {line.so_number} · raised{' '}
              {line.ordered_date ? dayLabel(line.ordered_date) : EM_DASH}
            </div>
          </div>
          <div className="shrink-0 text-end">
            <div className="tabular-nums">{fmtInt(line.qty)}</div>
            <div className={cn('text-2xs tabular-nums', ageTone(line.days_outstanding))}>
              {fmtInt(line.days_outstanding)} days
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default DemandDrillPopover;
