'use client';

import * as React from 'react';
import { CalendarIcon } from 'lucide-react';
import type { DateRange } from 'react-day-picker';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

/**
 * ONE control for a date range. Never two date fields side by side.
 *
 * Two fields make the user hold the relationship in their head: nothing stops "to" landing
 * before "from", the two labels have to be read separately to learn they are one fact, and
 * on a narrow screen they wrap apart so the pair stops looking like a pair at all. A range
 * picker enforces the order by construction - you cannot pick an end before a start.
 *
 * Standard across the system: any "X from / X to" pair renders this. See
 * `documentation/ARCHITECTURE-RULES.md`.
 *
 * Both ends stay optional, because a half-known range is a real answer: a developer often
 * gives the start of a delivery window months before the end of it.
 */
function formatDDMMYYYY(value: Date): string {
  const d = String(value.getDate()).padStart(2, '0');
  const m = String(value.getMonth() + 1).padStart(2, '0');
  return `${d}/${m}/${value.getFullYear()}`;
}

/** `YYYY-MM-DD` (what the API speaks) to a local Date. */
export function parseIsoDate(value?: string | null): Date | undefined {
  if (!value) return undefined;
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(value.trim());
  if (!match) return undefined;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? undefined : date;
}

/** A local Date back to `YYYY-MM-DD`, without a timezone shifting the day. */
export function toIsoDate(value?: Date): string | null {
  if (!value) return null;
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${value.getFullYear()}-${m}-${d}`;
}

export interface DateRangePickerProps {
  from?: string | null;
  to?: string | null;
  /** Both ends, as `YYYY-MM-DD` or null. Emitted together: they are one fact. */
  onChange: (next: { from: string | null; to: string | null }) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
  'aria-label'?: string;
}

export function DateRangePicker({
  from,
  to,
  onChange,
  placeholder = 'Pick a date range',
  disabled = false,
  className,
  id,
  'aria-label': ariaLabel,
}: DateRangePickerProps) {
  const [open, setOpen] = React.useState(false);

  const selected: DateRange | undefined = React.useMemo(() => {
    const start = parseIsoDate(from);
    const end = parseIsoDate(to);
    if (!start && !end) return undefined;
    // react-day-picker needs a `from` to render a range at all, so an end-only range is
    // shown anchored on the end. The user can still correct either side.
    return { from: start ?? end, to: end };
  }, [from, to]);

  const label = React.useMemo(() => {
    const start = parseIsoDate(from);
    const end = parseIsoDate(to);
    if (start && end) return `${formatDDMMYYYY(start)} - ${formatDDMMYYYY(end)}`;
    if (start) return `${formatDDMMYYYY(start)} - ?`;
    if (end) return `? - ${formatDDMMYYYY(end)}`;
    return null;
  }, [from, to]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          disabled={disabled}
          aria-label={ariaLabel ?? placeholder}
          className={cn(
            'w-full justify-start font-normal',
            !label && 'text-muted-foreground',
            className,
          )}
        >
          <CalendarIcon className="size-4 shrink-0" aria-hidden />
          <span className="truncate">{label ?? placeholder}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          selected={selected}
          onSelect={(range) =>
            onChange({ from: toIsoDate(range?.from), to: toIsoDate(range?.to) })
          }
          autoFocus
          numberOfMonths={1}
        />
        <div className="flex items-center justify-between border-t border-border px-3 py-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onChange({ from: null, to: null })}
          >
            Clear
          </Button>
          <Button type="button" size="sm" onClick={() => setOpen(false)}>
            Done
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
