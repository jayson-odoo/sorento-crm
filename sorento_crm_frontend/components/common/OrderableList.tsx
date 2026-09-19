'use client';

import { ArrowDown, ArrowUp, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * A short ordered list, reordered by Up / Down rather than drag-and-drop (D14: no new
 * motion on this plan's surfaces, and dnd-kit's own drag affordance is exactly that).
 * Used for the tier order and the cross-domain ladder (M5), and a domain's own ladder
 * tab (M2) - anywhere the mockups draw a numbered list with a reorder handle.
 */
export default function OrderableList({
  items,
  labelFor = (item) => item,
  onChange,
  onRemove,
  disabled = false,
  className,
}: {
  items: string[];
  labelFor?: (item: string) => string;
  onChange: (items: string[]) => void;
  onRemove?: (item: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing in this order yet.</p>;
  }

  return (
    <ol className={cn('space-y-1', className)}>
      {items.map((item, index) => (
        <li
          key={item}
          className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-sm"
        >
          <span className="w-5 shrink-0 text-muted-foreground tabular-nums">{index + 1}.</span>
          <span className="min-w-0 flex-1 truncate" title={labelFor(item)}>
            {labelFor(item)}
          </span>
          <div className="flex shrink-0 items-center gap-0.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              aria-label={`Move ${labelFor(item)} up`}
              disabled={disabled || index === 0}
              onClick={() => move(index, -1)}
            >
              <ArrowUp className="size-3.5" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="size-7 p-0"
              aria-label={`Move ${labelFor(item)} down`}
              disabled={disabled || index === items.length - 1}
              onClick={() => move(index, 1)}
            >
              <ArrowDown className="size-3.5" />
            </Button>
            {onRemove && !disabled && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="size-7 p-0 text-destructive"
                aria-label={`Remove ${labelFor(item)}`}
                onClick={() => onRemove(item)}
              >
                <X className="size-3.5" />
              </Button>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
