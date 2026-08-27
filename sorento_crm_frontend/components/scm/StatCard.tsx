'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * One boxed figure: what it is, how much, and one line saying what it is made of.
 *
 * Lifted out of `BoardCellBreakdownDialog`'s "Quantity needed" box (project-sales fulfilment
 * planning), which is where this shape was settled, so the loading plan's cards, that dialog
 * and the loading plan's own row popover cannot drift into three boxes that merely resemble
 * each other. The swatch is the same paint the board's supply bar uses, and it is what
 * replaces a separate legend: a card that carries the colour explains the colour.
 */
export function StatCard({
  label,
  value,
  sub,
  swatch,
  tone,
  className,
  testId,
}: {
  label: string;
  value: React.ReactNode;
  /** One line under the number - what it is made of, never an explanation of the feature. */
  sub?: React.ReactNode;
  /** Tailwind background token for the colour dot, e.g. `bg-emerald-500`. */
  swatch?: string;
  /** Tailwind text token for the number, e.g. `text-rose-700`. Defaults to the body colour. */
  tone?: string;
  className?: string;
  testId?: string;
}) {
  return (
    <div
      data-testid={testId}
      className={cn('rounded-lg border border-border p-3', className)}
    >
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {swatch ? (
          <span aria-hidden className={cn('size-2.5 shrink-0 rounded-sm', swatch)} />
        ) : null}
        <span className="min-w-0 break-words">{label}</span>
      </p>
      <p className={cn('text-2xl font-semibold tabular-nums', tone)}>{value}</p>
      {sub ? <p className="text-xs text-muted-foreground break-words">{sub}</p> : null}
    </div>
  );
}

export default StatCard;
