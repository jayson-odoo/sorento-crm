'use client';

import { useState } from 'react';
import { X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

/**
 * A free-text list edited as chips - one word or phrase per Enter, removable by its
 * own `x`. For a field whose values are not drawn from a catalog (switch words,
 * intents, base property words) so `SearchableMultiSelect` would have nothing to
 * search against.
 */
export default function StringChipInput({
  value,
  onChange,
  placeholder = 'Type and press Enter',
  disabled = false,
  className,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}) {
  const [draft, setDraft] = useState('');

  const commit = () => {
    const next = draft.trim();
    if (!next || value.includes(next)) {
      setDraft('');
      return;
    }
    onChange([...value, next]);
    setDraft('');
  };

  return (
    <div
      className={cn(
        'flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5',
        disabled && 'opacity-50',
        className,
      )}
    >
      {value.map((word) => (
        <span
          key={word}
          className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-sm"
        >
          {word}
          {!disabled && (
            <button
              type="button"
              aria-label={`Remove ${word}`}
              onClick={() => onChange(value.filter((w) => w !== word))}
            >
              <X className="size-3" />
            </button>
          )}
        </span>
      ))}
      {!disabled && (
        <Input
          className="h-6 min-w-32 flex-1 border-0 p-0 shadow-none focus-visible:ring-0"
          placeholder={value.length === 0 ? placeholder : ''}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commit();
            }
          }}
          onBlur={commit}
        />
      )}
    </div>
  );
}
