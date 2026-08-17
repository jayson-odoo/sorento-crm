'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';

/**
 * Icon-only switch between two ways of showing the same rows.
 *
 * Icons alone, no words: the labels ("Board" / "Grid") doubled the width of a control whose
 * two icons already say it, and the client asked for the icon on its own.
 *
 * The LIST is always the default view (ADR 1d) - a card layout is a view somebody chooses,
 * never what they land on, because cards cannot be scanned down a column or sorted.
 */
export type ViewOption<TValue extends string> = {
  value: TValue;
  icon: React.ReactNode;
  /** Used for the tooltip and the accessible name, since there is no visible text. */
  label: string;
};

export function ViewToggle<TValue extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: TValue;
  options: ViewOption<TValue>[];
  onChange: (next: TValue) => void;
  ariaLabel: string;
}) {
  return (
    <div
      className="inline-flex rounded-md border border-border p-0.5"
      role="group"
      aria-label={ariaLabel}
    >
      {options.map((option) => (
        <Button
          key={option.value}
          type="button"
          size="sm"
          mode="icon"
          variant={value === option.value ? 'primary' : 'ghost'}
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
          aria-label={option.label}
          title={option.label}
        >
          {option.icon}
        </Button>
      ))}
    </div>
  );
}
