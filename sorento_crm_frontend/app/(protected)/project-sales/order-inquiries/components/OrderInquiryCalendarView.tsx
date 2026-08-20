'use client';

import * as React from 'react';
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  isToday,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from 'date-fns';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { statusPillClass } from '@/lib/status-pill';
import { VERB_LABEL, VERB_PALETTE_KEY } from '../../_shared/components/OrderInquiryVerbPill';
import { formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryDayTotal } from '../../_shared/types/orderInquiry.types';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
/** As many chips as a cell has room for before the rest fold into "+N more". */
const MAX_CHIPS = 3;

function monthKey(date: Date): string {
  return format(date, 'yyyy-MM');
}

/**
 * The calendar the captain asked for in place of the month button row.
 *
 * A day cell shows what purchasing owes that day - the row and quantity totals, and up
 * to a few chips naming the item and instruction - without opening anything. Clicking a
 * day with rows narrows the list below the grid to that one day (`onSelectDay`); a day
 * with nothing raised is not a button at all, because there is nothing to open.
 */
export function OrderInquiryCalendarView({
  month,
  onMonthChange,
  byDay,
  isLoading,
  selectedDay,
  onSelectDay,
}: {
  /** `YYYY-MM`, the month currently displayed. */
  month: string;
  onMonthChange: (next: string) => void;
  byDay: OrderInquiryDayTotal[];
  isLoading: boolean;
  selectedDay: string | null;
  onSelectDay: (day: string | null) => void;
}) {
  const monthDate = React.useMemo(() => parseISO(`${month}-01`), [month]);
  const byDayMap = React.useMemo(
    () => new Map(byDay.map((entry) => [entry.date, entry])),
    [byDay],
  );
  const days = React.useMemo(() => {
    const start = startOfWeek(startOfMonth(monthDate), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(monthDate), { weekStartsOn: 1 });
    return eachDayOfInterval({ start, end });
  }, [monthDate]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Previous month"
            onClick={() => onMonthChange(monthKey(subMonths(monthDate, 1)))}
          >
            <ChevronLeft className="size-4" aria-hidden />
          </Button>
          <span className="min-w-36 text-center text-sm font-semibold">
            {format(monthDate, 'MMMM yyyy')}
          </span>
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Next month"
            onClick={() => onMonthChange(monthKey(addMonths(monthDate, 1)))}
          >
            <ChevronRight className="size-4" aria-hidden />
          </Button>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onMonthChange(monthKey(new Date()))}
        >
          Today
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <div className="grid grid-cols-7 border-b bg-muted/40">
          {WEEKDAYS.map((label) => (
            <div
              key={label}
              className="px-2 py-1.5 text-center text-xs font-medium text-muted-foreground"
            >
              {label}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {isLoading
            ? Array.from({ length: 7 }).map((_, index) => (
                <div key={index} className="min-h-24 border-b border-r p-1.5 last:border-r-0">
                  <Skeleton className="h-4 w-4" />
                </div>
              ))
            : days.map((day) => {
                const key = format(day, 'yyyy-MM-dd');
                const entry = byDayMap.get(key);
                const inMonth = isSameMonth(day, monthDate);
                const chips = entry?.top.slice(0, MAX_CHIPS) ?? [];
                const more = Math.max((entry?.top.length ?? 0) - chips.length, 0);
                const selected = selectedDay === key;
                return (
                  <button
                    key={key}
                    type="button"
                    disabled={!entry}
                    onClick={() => onSelectDay(selected ? null : key)}
                    aria-pressed={selected}
                    aria-label={
                      entry
                        ? `${format(day, 'd MMMM yyyy')}, ${entry.rows} row${entry.rows === 1 ? '' : 's'}`
                        : format(day, 'd MMMM yyyy')
                    }
                    className={cn(
                      'flex min-h-24 flex-col items-stretch gap-1 border-b border-r p-1.5 text-left last:border-r-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                      !inMonth && 'bg-muted/20',
                      entry ? 'cursor-pointer hover:bg-muted/50' : 'cursor-default',
                      selected && 'bg-primary/10 ring-2 ring-inset ring-primary',
                    )}
                  >
                    <span
                      className={cn(
                        'text-xs font-medium',
                        !inMonth && 'text-muted-foreground',
                        isToday(day) && inMonth && 'text-primary',
                      )}
                    >
                      {format(day, 'd')}
                    </span>
                    {entry && (
                      <>
                        <span className="text-[11px] whitespace-nowrap text-muted-foreground">
                          {entry.rows} row{entry.rows === 1 ? '' : 's'} ·{' '}
                          {formatInquiryQty(entry.qty)} qty
                        </span>
                        <div className="flex min-w-0 flex-col gap-0.5">
                          {chips.map((chip, index) => (
                            <span
                              key={index}
                              title={`${chip.item_code ?? 'Unresolved'} × ${formatInquiryQty(chip.qty)} (${VERB_LABEL[chip.verb] ?? chip.verb})`}
                              className={cn(
                                'block truncate rounded px-1 py-0.5 text-[10px] font-medium',
                                statusPillClass(VERB_PALETTE_KEY[chip.verb] ?? 'draft'),
                              )}
                            >
                              {chip.item_code ?? 'Unresolved'} × {formatInquiryQty(chip.qty)}
                            </span>
                          ))}
                          {more > 0 && (
                            <span className="text-[10px] text-muted-foreground">
                              +{more} more
                            </span>
                          )}
                        </div>
                      </>
                    )}
                  </button>
                );
              })}
        </div>
      </div>
    </div>
  );
}
