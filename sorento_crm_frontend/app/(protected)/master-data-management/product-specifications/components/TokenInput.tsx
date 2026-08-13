'use client';

import { useState } from 'react';
import { Undo2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

/**
 * A list of short strings, edited as pills. Type, press Enter, it joins the list.
 *
 * Replaces a comma-separated text field. The old control asked people to hold the
 * whole list in their head as one string and gave no way to remove one item without
 * re-reading the punctuation — and a trailing comma silently created an empty word.
 *
 * `muted` items render quieter (something shipped, removable but not yours).
 * `suppressed` items are shipped entries this business has taken away: they render
 * struck through with an undo control, because a chip that simply vanished gave no way
 * to discover what had been removed, let alone put it back.
 */
export default function TokenInput({
  values,
  onChange,
  placeholder = 'add one',
  muted = [],
  suppressed = [],
  onRestore,
  normalise,
  ariaLabel,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  /** e.g. lowercase + underscores for a spec value. Left alone for customer words. */
  normalise?: (raw: string) => string;
  muted?: string[];
  /** Shipped entries currently taken away. Rendered after the live ones. */
  suppressed?: string[];
  onRestore?: (value: string) => void;
  ariaLabel?: string;
}) {
  const [draft, setDraft] = useState('');

  const commit = () => {
    const raw = draft.trim();
    if (!raw) return;
    const value = normalise ? normalise(raw) : raw;
    if (value && !values.includes(value)) onChange([...values, value]);
    setDraft('');
  };

  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5 focus-within:ring-1 focus-within:ring-ring">
      {values.map((value) => (
        <Badge
          key={value}
          variant={muted.includes(value) ? 'outline' : 'secondary'}
          size="sm"
          appearance="light"
          shape="circle"
        >
          {value}
          <button
            type="button"
            className="ml-1 cursor-pointer opacity-60 hover:opacity-100"
            onClick={() => onChange(values.filter((v) => v !== value))}
            aria-label={`Remove ${value}`}
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}

      {suppressed.map((value) => (
        <Badge
          key={`suppressed-${value}`}
          variant="outline"
          size="sm"
          appearance="light"
          shape="circle"
          className="text-muted-foreground line-through decoration-muted-foreground/60"
        >
          {value}
          {onRestore && (
            <button
              type="button"
              className="ml-1 cursor-pointer no-underline opacity-60 hover:opacity-100"
              onClick={() => onRestore(value)}
              aria-label={`Put ${value} back`}
            >
              <Undo2 className="size-3" />
            </button>
          )}
        </Badge>
      ))}

      <input
        className="min-w-[8rem] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        placeholder={placeholder}
        aria-label={ariaLabel}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            commit();
            return;
          }
          // Backspace on an empty box removes the last pill, the way every tag field
          // people already use behaves.
          if (e.key === 'Backspace' && !draft && values.length > 0) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={commit}
      />
    </div>
  );
}
