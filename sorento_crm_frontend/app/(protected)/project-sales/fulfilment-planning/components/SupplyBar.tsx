'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { COLOURS, LABELS, type SupplySegment } from '../../_shared/lib/supplyVocabulary';
import { toMinor } from '../../_shared/lib/supplyComposition';

/**
 * Where a quantity is going to come from, as a thin bar under it (PLAN section C).
 *
 * The captain, on the grid: "a cell says nothing about the suggestion until it is opened".
 * One segment per kind, in proportion, so a board is scannable without opening anything. One
 * kind is one solid segment; a mixed cell shows the mix at the width it actually is.
 *
 * SOLID MEANS DECIDED. A proposal is drawn at half opacity, so the difference between what the
 * engine suggests and what somebody has committed to is visible across a whole board at once
 * rather than one popover at a time.
 *
 * Shared by the grid and the list so the two views cannot disagree about a colour.
 */
export function SupplyBar({
  segments,
  decided,
  className,
}: {
  segments: SupplySegment[];
  decided: boolean;
  className?: string;
}) {
  const total = segments.reduce((sum, segment) => sum + Math.abs(toMinor(segment.qty)), 0);
  if (segments.length === 0 || total === 0) return null;

  return (
    <span
      data-testid="supply-bar"
      data-decided={String(decided)}
      className={cn(
        'flex h-1.5 w-full overflow-hidden rounded-sm',
        decided ? 'opacity-100' : 'opacity-50',
        className,
      )}
    >
      {segments.map((segment) => (
        <span
          key={segment.kind}
          data-kind={segment.kind}
          data-qty={segment.qty}
          title={`${LABELS[segment.kind]} ${segment.qty}`}
          className={cn('h-full', COLOURS[segment.kind].bar)}
          style={{ width: `${(Math.abs(toMinor(segment.qty)) / total) * 100}%` }}
        />
      ))}
    </span>
  );
}
