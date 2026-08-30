'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type {
  ImportOutcomeBreakdownEntry,
  ImportJobResultEnvelope,
} from '../types/importJob.types';

type Group = 'successful' | 'skipped' | 'failed';

const GROUP_META: Record<Group, { title: string; tone: string; empty: string }> = {
  successful: {
    title: 'Successful',
    tone: 'text-emerald-600 dark:text-emerald-400',
    empty: 'Nothing was written by this job.',
  },
  skipped: {
    title: 'Skipped',
    tone: 'text-amber-600 dark:text-amber-500',
    empty: 'No rows were skipped.',
  },
  failed: {
    title: 'Failed',
    tone: 'text-red-600 dark:text-red-400',
    empty: 'No rows failed.',
  },
};

function groupTotal(entries: ImportOutcomeBreakdownEntry[] | undefined): number {
  return (entries ?? []).reduce((sum, entry) => sum + (entry.count || 0), 0);
}

function ReasonRow({
  entry,
  active,
  onSelect,
}: {
  entry: ImportOutcomeBreakdownEntry;
  active: boolean;
  onSelect?: (code: string) => void;
}) {
  const topValues = entry.top_values ?? [];
  return (
    <div
      className={cn(
        'rounded-md border px-3 py-2',
        active ? 'border-primary bg-primary/5' : 'border-border bg-muted/40',
      )}
    >
      <button
        type="button"
        onClick={() => onSelect?.(entry.code)}
        className="flex w-full items-baseline justify-between gap-3 text-start"
        title={`Show only ${entry.label} rows`}
      >
        <span className="min-w-0 truncate text-sm" title={entry.label}>
          {entry.label}
        </span>
        <span className="shrink-0 font-mono text-sm tabular-nums">
          {entry.count.toLocaleString()}
        </span>
      </button>
      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{entry.code}</p>
      {topValues.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {topValues.map((tv) => (
            <li
              key={tv.value}
              className="flex items-baseline justify-between gap-3 font-mono text-[11px] text-muted-foreground"
            >
              <span className="min-w-0 truncate" title={tv.value}>
                {tv.value}
              </span>
              <span className="shrink-0 tabular-nums">×{tv.count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface OutcomeBreakdownCardProps {
  result?: ImportJobResultEnvelope | null;
  /** Currently filtered reason code, so the matching row can be highlighted. */
  activeCode?: string;
  onSelectCode?: (code: string, outcome: Group) => void;
}

export function OutcomeBreakdownCard({
  result,
  activeCode,
  onSelectCode,
}: OutcomeBreakdownCardProps) {
  const breakdown = result?.breakdown;
  // Legacy jobs predate the envelope - say so plainly instead of rendering three
  // empty columns that read as "nothing happened".
  const isLegacy = !breakdown;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Outcome breakdown</CardTitle>
          {result?.rows_truncated && (
            <Badge variant="secondary">
              Row capture truncated
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLegacy ? (
          <p className="text-sm text-muted-foreground">
            This job ran before per-row outcome capture existed, so it has no breakdown. Its
            original result is still available under “Full result (JSON)” below.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {(['successful', 'skipped', 'failed'] as Group[]).map((group) => {
              const entries = breakdown?.[group] ?? [];
              const meta = GROUP_META[group];
              return (
                // min-w-0: without it a long reason label widens the grid track and
                // pushes the whole page into horizontal overflow on narrow screens.
                <div key={group} className="min-w-0">
                  <div className="mb-2 flex items-baseline justify-between gap-2">
                    <p
                      className={cn(
                        'text-xs font-semibold uppercase tracking-wider',
                        meta.tone,
                      )}
                    >
                      {meta.title}
                    </p>
                    <p className={cn('font-mono text-sm tabular-nums', meta.tone)}>
                      {groupTotal(entries).toLocaleString()}
                    </p>
                  </div>
                  {entries.length === 0 ? (
                    <div className="rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted-foreground">
                      {meta.empty}
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {entries.map((entry) => (
                        <ReasonRow
                          key={entry.code}
                          entry={entry}
                          active={activeCode === entry.code}
                          onSelect={(code) => onSelectCode?.(code, group)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default OutcomeBreakdownCard;
