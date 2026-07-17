'use client';

import { useMemo } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useCategoryOptions } from '../../hooks/useScmOptions';
import { useMarketSignals, useMarketTopics, useRunResearch } from '../hooks/useMarket';
import { MarketSignalsPanel } from './MarketSignalsPanel';
import { MarketSignalTiles } from './MarketSignalTiles';
import { MarketTopicsGrid } from './MarketTopicsGrid';
import { RunResearchCard } from './RunResearchCard';

export function MarketSignalsView() {
  const signals = useMarketSignals();
  const topics = useMarketTopics();
  const { data: categoryOptions } = useCategoryOptions();
  const { run, isRunning, start, reset } = useRunResearch();

  const signalRows = useMemo(() => signals.data ?? [], [signals.data]);
  const activeTopicCount = (topics.data ?? []).filter((t) => t.is_active).length;
  // Signals arrive newest-first — the head is the last captured.
  const lastCapturedAt = signalRows.length ? signalRows[0].captured_at : null;

  return (
    <div className="space-y-8">
      {/* ── Market signals ─────────────────────────────────────────── */}
      <section className="space-y-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold">Market signals</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Latest market and economic reads for your active topics. Advisory only — figures never
              change a recommendation on their own.
            </p>
          </div>
          <Button onClick={() => void start()} disabled={isRunning} className="shrink-0">
            <RefreshCw className={isRunning ? 'size-4 animate-spin' : 'size-4'} />
            Run research
          </Button>
        </div>

        <RunResearchCard run={run} isRunning={isRunning} onRetry={() => void start()} onDismiss={reset} />

        <MarketSignalTiles
          activeTopicCount={activeTopicCount}
          signalCount={signalRows.length}
          lastCapturedAt={lastCapturedAt}
        />

        <MarketSignalsPanel
          signals={signalRows}
          categoryOptions={categoryOptions}
          isLoading={signals.isLoading}
          isError={signals.isError}
          error={signals.error as Error | null}
        />
      </section>

      {/* ── Research topics ────────────────────────────────────────── */}
      <section className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">Research topics</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Configure what the research job searches for. Each topic's prompt drives a web search on
            its cadence; matching signals appear above.
          </p>
        </div>
        <MarketTopicsGrid />
      </section>
    </div>
  );
}
