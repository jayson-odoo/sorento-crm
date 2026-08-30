'use client';

import { useEffect, useMemo, useState } from 'react';
import { CalendarIcon, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

export type PeriodGranularity = 'day' | 'month' | 'year';

export interface PeriodValue {
  granularity: PeriodGranularity;
  from?: Date;
  to?: Date;
}

interface Props {
  value: PeriodValue;
  onChange: (next: PeriodValue) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}
function formatDDMMYYYY(d: Date): string {
  return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
}
function lastDayOfMonth(year: number, monthZeroBased: number): number {
  return new Date(year, monthZeroBased + 1, 0).getDate();
}

function displayPeriod(v: PeriodValue): string {
  if (!v.from && !v.to) return '';
  const f = v.from;
  const t = v.to ?? v.from;
  if (!f || !t) return '';
  if (v.granularity === 'year') {
    return f.getFullYear() === t.getFullYear()
      ? `${f.getFullYear()}`
      : `${f.getFullYear()} - ${t.getFullYear()}`;
  }
  if (v.granularity === 'month') {
    const left = `${pad2(f.getMonth() + 1)}/${f.getFullYear()}`;
    const right = `${pad2(t.getMonth() + 1)}/${t.getFullYear()}`;
    return left === right ? left : `${left} - ${right}`;
  }
  const left = formatDDMMYYYY(f);
  const right = formatDDMMYYYY(t);
  return left === right ? left : `${left} - ${right}`;
}

/**
 * Convert a PeriodValue into ISO date bounds for the backend.
 * - year: start = Jan 1 of from-year, end = Dec 31 of to-year
 * - month: start = day 1 of from-month, end = last day of to-month
 * - day: literal day boundaries
 */
export function periodToIsoBounds(
  v: PeriodValue,
): { start_date?: string; end_date?: string } {
  if (!v.from && !v.to) return {};
  const f = v.from ?? v.to!;
  const t = v.to ?? v.from!;
  if (v.granularity === 'year') {
    return {
      start_date: `${f.getFullYear()}-01-01`,
      end_date: `${t.getFullYear()}-12-31`,
    };
  }
  if (v.granularity === 'month') {
    const start = `${f.getFullYear()}-${pad2(f.getMonth() + 1)}-01`;
    const last = lastDayOfMonth(t.getFullYear(), t.getMonth());
    const end = `${t.getFullYear()}-${pad2(t.getMonth() + 1)}-${pad2(last)}`;
    return { start_date: start, end_date: end };
  }
  const start = `${f.getFullYear()}-${pad2(f.getMonth() + 1)}-${pad2(f.getDate())}`;
  const end = `${t.getFullYear()}-${pad2(t.getMonth() + 1)}-${pad2(t.getDate())}`;
  return { start_date: start, end_date: end };
}

export function PeriodPicker({
  value,
  onChange,
  placeholder = 'dd/mm/yyyy - dd/mm/yyyy',
  disabled,
  className,
}: Props) {
  const [open, setOpen] = useState(false);
  const display = displayPeriod(value);

  const clear = () => onChange({ granularity: value.granularity });

  return (
    <div className={cn('flex gap-2', className)}>
      <Input
        readOnly
        type="text"
        value={display}
        placeholder={placeholder}
        disabled={disabled}
        className="flex-1 cursor-pointer"
        onClick={() => !disabled && setOpen(true)}
      />
      {display && !disabled && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={clear}
          aria-label="Clear period"
        >
          <X className="h-4 w-4" />
        </Button>
      )}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={disabled}
            aria-label="Pick a period"
          >
            <CalendarIcon className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-3" align="end">
          <Tabs
            value={value.granularity}
            onValueChange={(v) =>
              onChange({
                granularity: v as PeriodGranularity,
                from: undefined,
                to: undefined,
              })
            }
          >
            <TabsList variant="default" className="mb-3">
              <TabsTrigger value="day">Day</TabsTrigger>
              <TabsTrigger value="month">Month</TabsTrigger>
              <TabsTrigger value="year">Year</TabsTrigger>
            </TabsList>
            <TabsContent value="day" className="mt-0">
              <Calendar
                mode="range"
                selected={
                  value.from || value.to
                    ? { from: value.from, to: value.to }
                    : undefined
                }
                onSelect={(range) =>
                  onChange({
                    granularity: 'day',
                    from: range?.from,
                    to: range?.to,
                  })
                }
                numberOfMonths={2}
                initialFocus
              />
            </TabsContent>
            <TabsContent value="month" className="mt-0">
              <MonthRangePicker
                from={value.from}
                to={value.to}
                onChange={(from, to) =>
                  onChange({ granularity: 'month', from, to })
                }
              />
            </TabsContent>
            <TabsContent value="year" className="mt-0">
              <YearRangePicker
                from={value.from}
                to={value.to}
                onChange={(from, to) =>
                  onChange({ granularity: 'year', from, to })
                }
              />
            </TabsContent>
          </Tabs>
          <div className="mt-3 flex justify-between gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={clear}>
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

const MONTH_NAMES = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

function MonthRangePicker({
  from,
  to,
  onChange,
}: {
  from?: Date;
  to?: Date;
  onChange: (from?: Date, to?: Date) => void;
}) {
  const today = new Date();
  const [year, setYear] = useState<number>(
    (from ?? to ?? today).getFullYear(),
  );
  const [pickEndNext, setPickEndNext] = useState<boolean>(!from || !!to);

  // Re-sync the displayed year if the parent value changes.
  useEffect(() => {
    if (from) setYear(from.getFullYear());
    else if (to) setYear(to.getFullYear());
  }, [from, to]);

  const fromKey = from
    ? `${from.getFullYear()}-${from.getMonth()}`
    : null;
  const toKey = to ? `${to.getFullYear()}-${to.getMonth()}` : null;

  const isInRange = (y: number, m: number) => {
    if (!from || !to) return false;
    const k = y * 100 + m;
    const a = from.getFullYear() * 100 + from.getMonth();
    const b = to.getFullYear() * 100 + to.getMonth();
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    return k >= lo && k <= hi;
  };

  const handleClick = (m: number) => {
    const clicked = new Date(year, m, 1);
    if (!from || (from && to)) {
      onChange(clicked, undefined);
      setPickEndNext(true);
      return;
    }
    // from set, to unset: this click finalizes range
    if (clicked.getTime() < from.getTime()) {
      onChange(clicked, from);
    } else {
      onChange(from, clicked);
    }
    setPickEndNext(false);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setYear((y) => y - 1)}
        >
          ◀
        </Button>
        <span className="text-sm font-medium">{year}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setYear((y) => y + 1)}
        >
          ▶
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-1">
        {MONTH_NAMES.map((name, m) => {
          const k = `${year}-${m}`;
          const isFrom = fromKey === k;
          const isTo = toKey === k;
          const inRange = isInRange(year, m);
          return (
            <button
              key={name}
              type="button"
              onClick={() => handleClick(m)}
              className={cn(
                'rounded-md px-3 py-2 text-sm transition',
                isFrom || isTo
                  ? 'bg-primary text-primary-foreground'
                  : inRange
                    ? 'bg-accent'
                    : 'hover:bg-accent/60',
              )}
            >
              {name}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        {pickEndNext && from && !to
          ? 'Click another month to set the end of the range, or the same month for a single-month period.'
          : 'Click a month to start a range.'}
      </p>
    </div>
  );
}

function YearRangePicker({
  from,
  to,
  onChange,
}: {
  from?: Date;
  to?: Date;
  onChange: (from?: Date, to?: Date) => void;
}) {
  const today = new Date();
  const anchor = (from ?? to ?? today).getFullYear();
  const [pageStart, setPageStart] = useState<number>(
    Math.floor(anchor / 12) * 12,
  );

  const years = useMemo(
    () => Array.from({ length: 12 }, (_, i) => pageStart + i),
    [pageStart],
  );

  const fromYear = from?.getFullYear();
  const toYear = to?.getFullYear();

  const inRange = (y: number) => {
    if (fromYear == null || toYear == null) return false;
    const lo = Math.min(fromYear, toYear);
    const hi = Math.max(fromYear, toYear);
    return y >= lo && y <= hi;
  };

  const handleClick = (y: number) => {
    const clicked = new Date(y, 0, 1);
    if (!from || (from && to)) {
      onChange(clicked, undefined);
      return;
    }
    const fy = from.getFullYear();
    if (y < fy) onChange(clicked, from);
    else onChange(from, clicked);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setPageStart((s) => s - 12)}
        >
          ◀
        </Button>
        <span className="text-sm font-medium">
          {pageStart} - {pageStart + 11}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setPageStart((s) => s + 12)}
        >
          ▶
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-1">
        {years.map((y) => {
          const isFrom = fromYear === y;
          const isTo = toYear === y;
          const r = inRange(y);
          return (
            <button
              key={y}
              type="button"
              onClick={() => handleClick(y)}
              className={cn(
                'rounded-md px-3 py-2 text-sm transition',
                isFrom || isTo
                  ? 'bg-primary text-primary-foreground'
                  : r
                    ? 'bg-accent'
                    : 'hover:bg-accent/60',
              )}
            >
              {y}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        Click a year to start; click another year for a range, or the same year
        twice for a single-year period.
      </p>
    </div>
  );
}
