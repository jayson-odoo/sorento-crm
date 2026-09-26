'use client';

/**
 * Who prints the tags (r9 S3/D7).
 *
 * A segmented control with NO default: the salesperson has to say, because the
 * answer decides whether the request ends at approved or carries on to a
 * collection hand-over, and a guessed default would quietly send half the
 * requests down the wrong one. The same control serves the portal form and the
 * office's own Edit request, so the two can never offer different words for
 * the same choice.
 */

import type React from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { PRINT_BY_OPTIONS, type PrintBy } from '@/lib/dealer-kit/print-collection';

interface PrintBySelectProps {
  value: PrintBy | null;
  onChange: (value: PrintBy) => void;
  /** Lets the office unset a wrong choice; the portal never passes it. */
  onClear?: () => void;
  disabled?: boolean;
  /** Named inline when Submit found it missing. */
  error?: string | null;
  'aria-labelledby'?: string;
}

export function PrintBySelect({
  value,
  onChange,
  onClear,
  disabled,
  error,
  'aria-labelledby': ariaLabelledBy,
}: PrintBySelectProps) {
  /**
   * ArrowLeft/ArrowRight walk the group and CHOOSE as they go, which is how a
   * radio group behaves: the option under the focus ring is the answer.
   */
  const move = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step =
      event.key === 'ArrowRight' || event.key === 'ArrowDown'
        ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
          ? -1
          : 0;
    if (step === 0 || disabled) return;
    event.preventDefault();
    const next =
      (index + step + PRINT_BY_OPTIONS.length) % PRINT_BY_OPTIONS.length;
    onChange(PRINT_BY_OPTIONS[next].value);
    const group = event.currentTarget.parentElement;
    const target = group?.children[next];
    if (target instanceof HTMLElement) target.focus();
  };

  return (
    <div className="space-y-1.5">
      <div
        role="radiogroup"
        aria-labelledby={ariaLabelledBy}
        aria-label={ariaLabelledBy ? undefined : 'Printing'}
        className="inline-flex items-center rounded-md border p-0.5"
      >
        {PRINT_BY_OPTIONS.map((option, index) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            disabled={disabled}
            // One stop for the whole group, and the arrows move between the
            // options inside it - what a radio group does everywhere else. Two
            // tab stops made Tab walk THROUGH the answer instead of past it.
            tabIndex={value === option.value || (!value && index === 0) ? 0 : -1}
            onKeyDown={(event) => move(event, index)}
            className={cn(
              'rounded px-3 py-1.5 text-sm transition-colors disabled:pointer-events-none disabled:opacity-50',
              value === option.value
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted',
            )}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {onClear && value && (
        <Button
          variant="ghost"
          size="sm"
          className="ml-2 text-xs text-muted-foreground"
          disabled={disabled}
          onClick={onClear}
        >
          Clear
        </Button>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export default PrintBySelect;
