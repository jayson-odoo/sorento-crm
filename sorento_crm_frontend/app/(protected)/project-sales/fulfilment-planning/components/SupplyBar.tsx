'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { COLOURS, LABELS } from '../../_shared/lib/supplyVocabulary';
import { toMinor } from '../../_shared/lib/supplyComposition';

/**
 * Anything with a kind and a quantity. The board's `SupplySegment` is one of these; the
 * order inquiry's three-kind segment (`orderInquiryKinds`) is the other, and it names its
 * own words and its own paint through `labels` / `colours` below.
 */
export interface BarSegment {
  kind: string;
  qty: string;
}

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
 * Shared by the grid and the list so the two views cannot disagree about a colour - and
 * by the order inquiry's schedule and list (section 3.I2), which asks the same question
 * of a purchasing row with a three-word vocabulary of its own. The words and the paint
 * are props with the board's own as defaults, so there is ONE bar rather than a second
 * one that could drift from it by a pixel or a rounding.
 */
export function SupplyBar({
  segments,
  decided,
  className,
  labels = LABELS,
  colours = COLOURS,
}: {
  segments: BarSegment[];
  decided: boolean;
  className?: string;
  labels?: Record<string, string>;
  colours?: Record<string, { bar: string }>;
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
          title={`${labels[segment.kind]} ${segment.qty}`}
          className={cn('h-full', colours[segment.kind].bar)}
          style={{ width: `${(Math.abs(toMinor(segment.qty)) / total) * 100}%` }}
        />
      ))}
    </span>
  );
}
