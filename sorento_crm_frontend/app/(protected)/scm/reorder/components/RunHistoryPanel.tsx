'use client';

import { useState } from 'react';
import { AlertCircle, ChevronLeft, ChevronRight, History, Warehouse } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTitle, CardToolbar } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatDateTimeInMalaysia, timeAgo } from '@/lib/helpers';
import { EM_DASH, fmtInt, fmtMoney } from '../../lib/format';
import { useReorderRunHistory } from '../hooks/useReorderRun';
import type { ReorderRunHistoryItem } from '../services/reorderRunService';
import type { ReorderRunStatus } from '../types/reorder.types';

const PAGE_SIZE = 8;

/** Parse a naive-UTC ISO string (as emitted by the backend) as UTC so relative time
 *  is not skewed by the browser's local zone (see the audit-time lesson). */
function toUtcMs(raw: string | null): number | null {
  if (!raw) return null;
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(raw);
  const ms = new Date(hasTz ? raw : `${raw}Z`).getTime();
  return Number.isNaN(ms) ? null : ms;
}

const STATUS_META: Record<
  ReorderRunStatus,
  { label: string; variant: 'success' | 'info' | 'destructive' }
> = {
  completed: { label: 'Completed', variant: 'success' },
  running: { label: 'Running', variant: 'info' },
  failed: { label: 'Failed', variant: 'destructive' },
};

function StatusBadge({ status }: { status: ReorderRunStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.running;
  return (
    <Badge variant={meta.variant} appearance="light" size="sm">
      {meta.label}
    </Badge>
  );
}

/** Warehouse scope as human codes, truncated with an overflow count. Never a UUID. */
function WarehouseScope({ codes, count }: { codes: string[]; count: number }) {
  const shown = codes.slice(0, 3);
  const overflow = count - shown.length;
  const full = codes.length ? codes.join(', ') : `${count} warehouse${count === 1 ? '' : 's'}`;
  return (
    <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground" title={full}>
      <Warehouse className="size-3.5 shrink-0" aria-hidden />
      <span className="truncate">
        {shown.length ? shown.join(', ') : `${count} warehouse${count === 1 ? '' : 's'}`}
        {overflow > 0 ? ` +${overflow}` : ''}
      </span>
    </span>
  );
}

/** A labelled count chip (buy / disposition / exception). */
function CountChip({ label, value, className }: { label: string; value: number; className?: string }) {
  return (
    <span className="flex flex-col items-end leading-tight">
      <span className={cn('text-sm font-semibold tabular-nums', className)}>{fmtInt(value)}</span>
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
    </span>
  );
}

function RunRow({
  run,
  selected,
  onSelect,
}: {
  run: ReorderRunHistoryItem;
  selected: boolean;
  onSelect: (run: ReorderRunHistoryItem) => void;
}) {
  const ms = toUtcMs(run.started_at);
  const relative = ms !== null ? timeAgo(new Date(ms)) : EM_DASH;
  const absolute = run.started_at ? formatDateTimeInMalaysia(run.started_at) : EM_DASH;
  const s = run.summary;
  return (
    <button
      type="button"
      onClick={() => onSelect(run)}
      aria-pressed={selected}
      className={cn(
        'flex w-full flex-col gap-3 rounded-lg border p-3 text-left transition-colors',
        'hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        'sm:flex-row sm:items-center sm:justify-between',
        selected ? 'border-primary bg-primary/5 ring-1 ring-inset ring-primary' : 'border-border',
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{relative}</span>
          <StatusBadge status={run.status} />
          {selected ? (
            <Badge variant="primary" appearance="light" size="sm">
              Viewing
            </Badge>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-xs text-muted-foreground" title={absolute}>
            {absolute}
          </span>
          <WarehouseScope codes={run.warehouse_codes} count={run.warehouse_count} />
        </div>
      </div>

      <div className="flex items-center gap-4 sm:gap-5">
        {s ? (
          <>
            <CountChip label="Buy" value={s.buy_count} className="text-scm-incoming" />
            <CountChip label="Disp." value={s.disposition_count} className="text-scm-overstock" />
            <CountChip label="Exc." value={s.exception_count} className="text-scm-stockout" />
            <span className="flex flex-col items-end leading-tight">
              <span className="text-sm font-semibold tabular-nums">
                {fmtMoney(s.total_cash_impact)}
              </span>
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Cash</span>
            </span>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">
            {run.status === 'failed' ? 'No results' : 'In progress'}
          </span>
        )}
      </div>
    </button>
  );
}

/**
 * Run history — a collapsible-free panel listing recent planning runs newest-first.
 * Clicking a run asks the parent to LOAD it (summary + recommendations) into the
 * main view without re-running. Renders explicit loading / empty / error states.
 */
export function RunHistoryPanel({
  selectedRunId,
  onSelect,
}: {
  selectedRunId: string | null;
  onSelect: (run: ReorderRunHistoryItem) => void;
}) {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error, refetch, isFetching } = useReorderRunHistory(
    page,
    PAGE_SIZE,
  );

  const runs = data?.data ?? [];
  const totalPages = data?.pagination.total_pages ?? 1;
  const total = data?.pagination.total ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4 text-muted-foreground" aria-hidden />
            Run history
          </CardTitle>
        </CardHeading>
        {total > 0 ? (
          <CardToolbar>
            <span className="text-xs text-muted-foreground tabular-nums">
              {total} run{total === 1 ? '' : 's'}
            </span>
          </CardToolbar>
        ) : null}
      </CardHeader>

      <div className="space-y-2 p-4">
        {isLoading ? (
          <div className="space-y-2" aria-label="Loading run history">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <AlertCircle className="size-5" aria-hidden />
            </span>
            <p className="max-w-sm text-sm text-muted-foreground">
              {error instanceof Error ? error.message : 'Failed to load run history.'}
            </p>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              Try again
            </Button>
          </div>
        ) : runs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <History className="size-5" aria-hidden />
            </span>
            <div className="text-sm font-medium">No runs yet</div>
            <p className="max-w-sm text-sm text-muted-foreground">
              Once you run planning, each run is saved here so you can revisit and compare them.
            </p>
          </div>
        ) : (
          <>
            {runs.map((run) => (
              <RunRow
                key={run.run_id}
                run={run}
                selected={run.run_id === selectedRunId}
                onSelect={onSelect}
              />
            ))}
          </>
        )}
      </div>

      {totalPages > 1 ? (
        <div className="flex items-center justify-between border-t px-4 py-3">
          <span className="text-xs text-muted-foreground tabular-nums">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || isFetching}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="size-4" />
              Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages || isFetching}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
