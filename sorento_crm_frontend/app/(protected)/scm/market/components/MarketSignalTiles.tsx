'use client';

import { Activity, Clock, ListChecks } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { EM_DASH, fmtInt } from '../../lib/format';

function Tile({
  label,
  value,
  icon: Icon,
  iconClass,
  title,
}: {
  label: string;
  value: string;
  icon: typeof Activity;
  iconClass?: string;
  title?: string;
}) {
  return (
    <Card className="p-4">
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
        title={title ?? value}
        className="mt-1 w-full min-w-0 truncate whitespace-nowrap text-2xl font-semibold tabular-nums tracking-tight"
      >
        {value}
      </div>
    </Card>
  );
}

/** Roll-up tiles above the signals panel: active topics, signals captured, last
 *  captured time. Non-interactive (unlike the reorder tiles) - pure summary. */
export function MarketSignalTiles({
  activeTopicCount,
  signalCount,
  lastCapturedAt,
}: {
  activeTopicCount: number;
  signalCount: number;
  /** Naive-UTC ISO of the newest signal; null when none captured yet. */
  lastCapturedAt: string | null;
}) {
  const lastLabel = lastCapturedAt ? formatDateTimeInMalaysia(lastCapturedAt) : EM_DASH;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Tile
        label="Active topics"
        value={fmtInt(activeTopicCount)}
        icon={ListChecks}
        iconClass="bg-scm-incoming-soft text-scm-incoming"
      />
      <Tile
        label="Signals captured"
        value={fmtInt(signalCount)}
        icon={Activity}
        iconClass="bg-scm-healthy-soft text-scm-healthy"
      />
      <Tile
        label="Last captured"
        value={lastLabel}
        icon={Clock}
        title={lastLabel}
      />
    </div>
  );
}
