'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { toMinor } from '../lib/supplyComposition';

/**
 * Anything with a kind and a quantity, where the kinds are ONE closed vocabulary. The
 * board's `SupplySegment` is one of these (`SupplyKind`); the order inquiry's three-kind
 * segment (`orderInquiryKinds`) is the other, and each names its own words and its own
 * paint through `labels` / `colours` below.
 *
 * The kind is a TYPE PARAMETER rather than a bare `string` because `colours[kind]` is
 * read without a guard: with `string` a caller could hand over a vocabulary its palette
 * has no entry for, and the mismatch arrives as "Cannot read properties of undefined" in
 * a cell rather than as a red squiggle on the call.
 */
export interface BarSegment<K extends string = string> {
  kind: K;
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
 * come in as props and there is no default vocabulary, so there is ONE bar rather than a
 * second one that could drift from it by a pixel or a rounding, and the bar itself knows
 * about neither vocabulary. Which is why it lives in `_shared` rather than under one of
 * the two screens that draw it.
 */
export function SupplyBar<K extends string>({
  segments,
  decided,
  className,
  labels,
  colours,
}: {
  segments: BarSegment<K>[];
  decided: boolean;
  className?: string;
  labels: Record<K, string>;
  colours: Record<K, { bar: string }>;
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
