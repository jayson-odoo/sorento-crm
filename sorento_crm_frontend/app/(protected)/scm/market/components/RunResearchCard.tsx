'use client';

import { AlertTriangle, Check, LoaderCircle, RotateCcw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { fmtInt } from '../../lib/format';
import type { MarketResearchRun } from '../types/market.types';

/**
 * Running → complete → failed feedback for a market-research run, mirroring the
 * reorder RunProgressCard shape. Running shows a spinner + "searching sources";
 * completed shows the fresh-signal count (dismissible); failed offers a retry.
 */
export function RunResearchCard({
  run,
  isRunning,
  onRetry,
  onDismiss,
}: {
  /** null while idle (card renders nothing). */
  run: MarketResearchRun | null;
  isRunning: boolean;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  if (isRunning) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-scm-incoming-soft text-scm-incoming">
            <LoaderCircle className="size-5 animate-spin" aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="text-sm font-semibold">Researching market signals…</div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Searching market and economic sources for your active topics.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  if (!run) return null;

  if (run.status === 'failed') {
    return (
      <Card className="border-scm-stockout/40 bg-scm-stockout-soft/40 p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-scm-stockout-soft text-scm-stockout">
            <AlertTriangle className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-scm-stockout">Market research failed</div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {run.error ?? 'The research run did not complete. Retry the run.'}
            </p>
            <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
              <RotateCcw className="size-4" />
              Retry research
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  // completed
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-scm-healthy-soft text-scm-healthy">
            <Check className="size-5" aria-hidden />
          </span>
          <div>
            <div className="text-sm font-semibold">Research complete</div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {fmtInt(run.signal_count)} new signal{run.signal_count === 1 ? '' : 's'} captured across{' '}
              {fmtInt(run.topic_count)} active topic{run.topic_count === 1 ? '' : 's'}.
            </p>
          </div>
        </div>
        <Button
          mode="icon"
          variant="ghost"
          size="sm"
          aria-label="Dismiss"
          title="Dismiss"
          onClick={onDismiss}
        >
          <X className="size-4" />
        </Button>
      </div>
    </Card>
  );
}
