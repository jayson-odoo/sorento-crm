'use client';

import { ArrowDownRight, ArrowUpRight, ExternalLink, Minus, Radar } from 'lucide-react';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { EM_DASH, fmtDecimal } from '../../lib/format';
import { TREND_META, resolveCategoryLabel, trendKey } from '../lib/marketLabels';
import type { MarketSignal, MarketTrend } from '../types/market.types';

const TREND_ICON = {
  up: ArrowUpRight,
  down: ArrowDownRight,
  flat: Minus,
  unknown: Minus,
} as const;

function TrendChip({ trend }: { trend: MarketTrend }) {
  const key = trendKey(trend);
  const meta = TREND_META[key];
  const Icon = TREND_ICON[key];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-2xs font-medium',
        meta.softBgClass,
        meta.textClass,
      )}
      title={`Trend: ${meta.label}`}
    >
      <Icon className="size-3" aria-hidden />
      {meta.label}
    </span>
  );
}

function SignalCard({
  signal,
  categoryOptions,
}: {
  signal: MarketSignal;
  categoryOptions: SearchableSelectOption[] | undefined;
}) {
  const category = resolveCategoryLabel(signal.category_ref, categoryOptions);
  const valueText =
    signal.value != null
      ? `${signal.currency ? `${signal.currency} ` : ''}${fmtDecimal(signal.value, signal.value % 1 === 0 ? 0 : 2)}`
      : EM_DASH;
  return (
    <Card className="flex flex-col gap-2.5 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" title={signal.topic_label}>
            {signal.topic_label}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            {category ? (
              <Badge variant="secondary" appearance="light" size="sm">
                <span className="max-w-[10rem] truncate" title={category}>
                  {category}
                </span>
              </Badge>
            ) : null}
            {signal.currency ? (
              <Badge variant="info" appearance="light" size="sm">
                {signal.currency}
              </Badge>
            ) : null}
          </div>
        </div>
        <TrendChip trend={signal.trend} />
      </div>

      <div
        className={cn('text-xl font-semibold tabular-nums tracking-tight', TREND_META[trendKey(signal.trend)].textClass)}
        title={valueText}
      >
        {valueText}
      </div>

      <p className="text-sm leading-snug text-muted-foreground">{signal.summary}</p>

      <div className="mt-auto flex items-center justify-between gap-2 pt-1 text-2xs text-muted-foreground">
        <span title={formatDateTimeInMalaysia(signal.captured_at)}>
          Captured {formatDateTimeInMalaysia(signal.captured_at)}
        </span>
        {signal.source_url ? (
          <a
            href={signal.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium text-primary underline-offset-2 hover:underline"
          >
            Source
            <ExternalLink className="size-3" aria-hidden />
          </a>
        ) : null}
      </div>
    </Card>
  );
}

/** Read-only market-signal viz: one trend card per cached signal (newest first).
 *  Own loading / error / empty states so it always renders (CRUD UX standard). */
export function MarketSignalsPanel({
  signals,
  categoryOptions,
  isLoading,
  isError,
  error,
}: {
  signals: MarketSignal[];
  categoryOptions: SearchableSelectOption[] | undefined;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
}) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <Card className="border-scm-stockout/40 bg-scm-stockout-soft/30 p-6 text-sm text-scm-stockout">
        {error instanceof Error ? error.message : 'Failed to load market signals.'}
      </Card>
    );
  }

  if (signals.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Radar className="size-6" aria-hidden />
        </span>
        <div>
          <div className="text-sm font-semibold">No market signals yet</div>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            Run research to capture the latest market and economic signals for your active topics.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {signals.map((s) => (
        <SignalCard key={s.id} signal={s} categoryOptions={categoryOptions} />
      ))}
    </div>
  );
}
