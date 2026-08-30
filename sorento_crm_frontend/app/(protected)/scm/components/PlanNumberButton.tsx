'use client';

import { cn } from '@/lib/utils';

/**
 * A number on an SCM plan row that opens the documents behind it (R7).
 *
 * The number IS the trigger. What this replaces was a hover popover on a small (i) beside the
 * figure: a mouse-only affordance, several per row, each too narrow for a document table and
 * each dismissed by the mouse drifting off it.
 *
 * A dotted underline is the whole affordance - it says "there is more here" without adding a
 * glyph, and the same treatment on every drillable cell teaches all of them at once.
 *
 * Copied from the reorder-revamp lane's own `PlanNumberButton` so the two screens' figures
 * behave and read identically; one file survives at whichever merge lands second (plan
 * section 9).
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
  /** A row with nothing to open (no product id) shows the figure as plain text. */
  disabled?: boolean;
}) {
  if (disabled) return <span className="tabular-nums">{value}</span>;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        // The cell can sit inside a whole-row click target; opening a dialog is not
        // navigating to the record.
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

export default PlanNumberButton;
