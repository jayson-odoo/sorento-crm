'use client';

import { cn } from '@/lib/utils';

/**
 * A number on the plan row that opens the documents behind it (plan 4.6, F1).
 *
 * The number IS the trigger. What stood here before was a figure with a small (i) beside it
 * and a hover popover on the icon - two targets per cell, one of which only worked with a
 * mouse, and a row of six of them read as six warnings rather than six doors.
 *
 * A dotted underline is the whole affordance: it says "there is more here" without adding a
 * glyph, and it is the same treatment on all six cells so one look teaches all of them.
 */
export function PlanNumberButton({
  value,
  label,
  onClick,
  disabled,
}: {
  /** Already formatted - this component never decides how a number is written. */
  value: string;
  /** What the dialog will show, for the screen reader and the tooltip. */
  label: string;
  onClick: () => void;
  /** A row with nothing to open (no product id, no run) shows the figure as plain text. */
  disabled?: boolean;
}) {
  if (disabled) return <span className="tabular-nums">{value}</span>;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        'rounded-sm tabular-nums underline decoration-dotted underline-offset-2',
        'hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      )}
    >
      {value}
    </button>
  );
}
