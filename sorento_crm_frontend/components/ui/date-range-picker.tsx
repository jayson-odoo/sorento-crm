'use client';

import * as React from 'react';
import { CalendarIcon } from 'lucide-react';
import type { DateRange } from 'react-day-picker';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Input } from '@/components/ui/input';
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
 *
 * R14c (owner, 24 Sep, reversing the two-field R14b on sight: "use the same date range
 * component but I can type; I don't want two different date fields"): the trigger is a
 * typeable `DD/MM/YYYY - DD/MM/YYYY` text input, with the calendar popover behind a
 * separate icon button beside it - the same two-piece shape `DatePicker`
 * (`@/components/ui/date-picker.tsx`) already uses for a single date, extended to a pair.
 * Typing is parsed on blur or Enter only, never per keystroke: a half-typed date is not a
 * date yet, and reformatting it mid-keystroke would fight the caret.
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

/** The input's own displayed text for the current `from`/`to` pair - never `?`, since
 *  unlike the old read-only label this string is what a re-typed value would replace. */
function formatRangeLabel(from?: string | null, to?: string | null): string {
  const start = parseIsoDate(from);
  const end = parseIsoDate(to);
  if (start && end) {
    return from === to
      ? formatDDMMYYYY(start)
      : `${formatDDMMYYYY(start)} - ${formatDDMMYYYY(end)}`;
  }
  if (start) return formatDDMMYYYY(start);
  if (end) return formatDDMMYYYY(end);
  return '';
}

const RANGE_INPUT_RE =
  /^(\d{1,2})\/(\d{1,2})\/(\d{4})\s*-\s*(\d{1,2})\/(\d{1,2})\/(\d{4})$/;
const SINGLE_INPUT_RE = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/;

function dateFromParts(d: string, m: string, y: string): Date | undefined {
  const date = new Date(Number(y), Number(m) - 1, Number(d));
  return Number.isNaN(date.getTime()) ? undefined : date;
}

/** Typed `DD/MM/YYYY - DD/MM/YYYY` or a single `DD/MM/YYYY` (from = to = that day);
 *  anything else, including blank, is unparseable - the caller reverts the input rather
 *  than emitting a change. */
function parseRangeInput(raw: string): { from: Date; to: Date } | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const range = RANGE_INPUT_RE.exec(trimmed);
  if (range) {
    const [, d1, m1, y1, d2, m2, y2] = range;
    const from = dateFromParts(d1, m1, y1);
    const to = dateFromParts(d2, m2, y2);
    return from && to ? { from, to } : null;
  }
  const single = SINGLE_INPUT_RE.exec(trimmed);
  if (single) {
    const [, d, m, y] = single;
    const day = dateFromParts(d, m, y);
    return day ? { from: day, to: day } : null;
  }
  return null;
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
  placeholder = 'DD/MM/YYYY - DD/MM/YYYY',
  disabled = false,
  className,
  id,
  'aria-label': ariaLabel,
}: DateRangePickerProps) {
  const [open, setOpen] = React.useState(false);
  const [inputValue, setInputValue] = React.useState(() => formatRangeLabel(from, to));

  React.useEffect(() => {
    setInputValue(formatRangeLabel(from, to));
  }, [from, to]);

  const selected: DateRange | undefined = React.useMemo(() => {
    const start = parseIsoDate(from);
    const end = parseIsoDate(to);
    if (!start && !end) return undefined;
    // react-day-picker needs a `from` to render a range at all, so an end-only range is
    // shown anchored on the end. The user can still correct either side.
    return { from: start ?? end, to: end };
  }, [from, to]);

  /** Parses the CURRENT typed text and either emits the pair or reverts the input to
   *  the last committed label - never leaves half-typed, unparseable text sitting in a
   *  field the caller never heard about. */
  const commit = () => {
    const parsed = parseRangeInput(inputValue);
    if (parsed) {
      onChange({ from: toIsoDate(parsed.from), to: toIsoDate(parsed.to) });
    } else {
      setInputValue(formatRangeLabel(from, to));
    }
  };

  return (
    <div className={cn('flex gap-2', className)}>
      <Input
        id={id}
        type="text"
        placeholder={placeholder}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            commit();
          }
        }}
        disabled={disabled}
        aria-label={ariaLabel}
        className="flex-1"
        autoComplete="off"
      />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={disabled}
            className="shrink-0"
            aria-label={ariaLabel ? `Pick a date range for ${ariaLabel}` : 'Pick a date range'}
          >
            <CalendarIcon className="size-4" aria-hidden />
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
    </div>
  );
}
