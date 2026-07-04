'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { diffStats, lineDiff } from '../../lib/lineDiff';

/**
 * Client-side unified line diff between two version templates (PLAN §9b Q2).
 */
export function DiffView({
  a,
  b,
  aLabel,
  bLabel,
}: {
  a: string;
  b: string;
  aLabel: string;
  bLabel: string;
}) {
  const rows = useMemo(() => lineDiff(a, b), [a, b]);
  const stats = useMemo(() => diffStats(rows), [rows]);

  return (
    <div className="space-y-2" data-testid="diff-view">
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>
          Comparing <span className="font-medium">{aLabel}</span> →{' '}
          <span className="font-medium">{bLabel}</span>
        </span>
        <span className="text-emerald-600" data-testid="diff-added-count">
          +{stats.added}
        </span>
        <span className="text-destructive" data-testid="diff-removed-count">
          −{stats.removed}
        </span>
      </div>
      <div className="max-h-[480px] overflow-auto rounded-md border">
        <pre className="min-w-full text-xs leading-relaxed">
          {rows.map((r, i) => (
            <div
              key={i}
              data-testid={`diff-row-${r.op}`}
              className={cn(
                'flex gap-2 px-2',
                r.op === 'added' && 'bg-emerald-50 text-emerald-900',
                r.op === 'removed' && 'bg-red-50 text-red-900',
              )}
            >
              <span className="w-4 shrink-0 select-none text-muted-foreground">
                {r.op === 'added' ? '+' : r.op === 'removed' ? '−' : ' '}
              </span>
              <span className="whitespace-pre-wrap break-words">{r.text || ' '}</span>
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}
