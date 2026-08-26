'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * One card of a decision strip: a coloured swatch, the kind's name, and whatever figures
 * that strip counts, in a shape a person can compare across cards by position alone.
 *
 * Shared by the fulfilment board's strip (`DecisionStrip`, two figures per card,
 * suggested against decided) and the order inquiry's (`OrderInquiryStrip`, one figure -
 * purchasing has no "suggested" to compare against, only what the documents say). The
 * SHELL is the thing worth sharing: the press behaviour, the pressed state, the disabled
 * state and the spacing are what make a strip readable, and two copies of them drift.
 *
 * A CARD READING NOTHING IS DISABLED RATHER THAN HIDDEN: nothing in view is that kind, so
 * there is nothing to filter to, and a press that emptied the screen would read as a
 * broken filter. It keeps its place, because a card that came and went would move every
 * card beside it.
 */
export function SupplyKindCard({
  kind,
  label,
  swatchClass,
  selected,
  disabled,
  onClick,
  testId,
  mark,
  children,
}: {
  /** Only ever an attribute for the tests and the swatch - never rendered as words. */
  kind: string;
  label: string;
  swatchClass: string;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
  testId: string;
  /** A dot beside the label when this strip has something to mark on the card. */
  mark?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'rounded-lg border p-2.5 text-start transition-colors',
        disabled ? 'opacity-60' : 'hover:bg-accent',
        selected ? 'border-primary bg-accent' : 'border-border',
      )}
    >
      <span className="flex items-center gap-1.5">
        <span
          data-kind={kind}
          aria-hidden
          className={cn('size-2.5 shrink-0 rounded-sm', swatchClass)}
        />
        <span className="min-w-0 truncate text-xs font-medium" title={label}>
          {label}
        </span>
        {mark}
      </span>
      {children}
    </button>
  );
}
