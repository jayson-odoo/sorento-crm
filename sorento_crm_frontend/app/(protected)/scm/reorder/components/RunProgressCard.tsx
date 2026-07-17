'use client';

import { AlertTriangle, ArrowRight, Check, LoaderCircle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { fmtInt, fmtMoney } from '../../lib/format';
import { RUN_STAGES } from '../hooks/useReorderRun';
import type { ReorderRun } from '../types/reorder.types';

/** Live running stepper + on-complete summary + failed state, in one card. */
export function RunProgressCard({
  run,
  stageIndex,
  isStalled = false,
  onReview,
  onRetry,
}: {
  run: ReorderRun;
  stageIndex: number;
  /** Still `running` past the poll cap — polling stopped, surface a retry. */
  isStalled?: boolean;
  onReview: () => void;
  onRetry: () => void;
}) {
  // A run still "running" past the poll cap: stop pretending it's live and let the user
  // retry. The original run may still finish server-side, but we no longer poll it.
  if (isStalled && run.status === 'running') {
    return (
      <Card className="border-scm-stockout/40 bg-scm-stockout-soft/40 p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-scm-stockout-soft text-scm-stockout">
            <AlertTriangle className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-scm-stockout">
              This run is taking longer than expected
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              It may have failed to start. Retry the run.
            </p>
            <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
              <RotateCcw className="size-4" />
              Retry run
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  if (run.status === 'failed') {
    return (
      <Card className="border-scm-stockout/40 bg-scm-stockout-soft/40 p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-scm-stockout-soft text-scm-stockout">
            <AlertTriangle className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-scm-stockout">Planning run failed</div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {run.error ?? 'The run did not complete. Retry the run.'}
            </p>
            <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
              <RotateCcw className="size-4" />
              Retry run
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  if (run.status === 'completed' && run.summary) {
    const s = run.summary;
    return (
      <Card className="p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-scm-healthy-soft text-scm-healthy">
              <Check className="size-5" aria-hidden />
            </span>
            <div>
              <div className="text-sm font-semibold">Planning complete</div>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {fmtInt(s.buy_count)} buy · {fmtInt(s.disposition_count)} disposition ·{' '}
                {fmtInt(s.exception_count)} no-supplier ·{' '}
                <span className="tabular-nums" title={fmtMoney(s.total_cash_impact)}>
                  {fmtMoney(s.total_cash_impact)}
                </span>{' '}
                cash impact
              </p>
            </div>
          </div>
          <Button onClick={onReview} className="shrink-0">
            Review {fmtInt(s.recommendation_count)} recommendations
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </Card>
    );
  }

  // running
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-2">
        <LoaderCircle className="size-4 shrink-0 animate-spin text-primary" aria-hidden />
        <span className="text-sm font-semibold">Running planning…</span>
      </div>
      <ol className="space-y-2.5">
        {RUN_STAGES.map((stage, i) => {
          const done = i < stageIndex;
          const active = i === stageIndex;
          return (
            <li key={stage.key} className="flex items-center gap-2.5 text-sm">
              <span
                className={cn(
                  'flex size-5 shrink-0 items-center justify-center rounded-full border',
                  done && 'border-scm-healthy bg-scm-healthy-soft text-scm-healthy',
                  active && 'border-primary text-primary',
                  !done && !active && 'border-border text-muted-foreground',
                )}
              >
                {done ? (
                  <Check className="size-3" aria-hidden />
                ) : active ? (
                  <LoaderCircle className="size-3 animate-spin" aria-hidden />
                ) : (
                  <span className="size-1.5 rounded-full bg-current" aria-hidden />
                )}
              </span>
              <span
                className={cn(
                  done && 'text-muted-foreground line-through',
                  active && 'font-medium',
                  !done && !active && 'text-muted-foreground',
                )}
              >
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
