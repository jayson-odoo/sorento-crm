'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { COLOURS, LABELS, ORDER } from '../../_shared/lib/supplyVocabulary';

/**
 * What the colours on the board mean: six swatches, six words (AC-C5).
 *
 * Above the grid and above the list, so a colour never has to be looked up somewhere else. Just
 * the swatches and their labels - a sentence explaining the bar would be a feature explanation
 * in the UI, and a bar that needs one has failed.
 */
export function SupplyLegend({ className }: { className?: string }) {
  return (
    <div
      data-testid="supply-legend"
      className={cn('flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs', className)}
    >
      {ORDER.map((kind) => (
        <span key={kind} className="flex items-center gap-1.5">
          <span
            data-kind={kind}
            aria-hidden
            className={cn('size-2.5 rounded-sm', COLOURS[kind].bar)}
          />
          <span className="text-muted-foreground">{LABELS[kind]}</span>
        </span>
      ))}
    </div>
  );
}
