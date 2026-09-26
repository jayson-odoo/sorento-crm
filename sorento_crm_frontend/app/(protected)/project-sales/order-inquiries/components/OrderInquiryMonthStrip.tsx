'use client';

import * as React from 'react';
import { format } from 'date-fns';

import { cn } from '@/lib/utils';
import { deliveryMonthLabel } from '../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryMonthTotal } from '../../_shared/types/orderInquiry.types';

/**
 * The delivery-month tab strip (S2, PLAN-scm-oi-worklist-excel-parity.md R-G): the same
 * job the spreadsheet's twelve sheet tabs did, above the grid rather than the "Delivery
 * month" select the Filters popover carried before this slice.
 *
 * "All" first, then one tab per month that actually has rows, in date order, each
 * carrying its own count - a month with nothing raised gets no tab at all, the same rule
 * the old select's options already followed. The current month scrolls into view on
 * first open WITHOUT selecting it (the owner did not ask for a pre-filter; "All" stays
 * the default), so a buyer opening the page mid-month lands where they would look first
 * without the list narrowing itself for them.
 *
 * "All" SITS OUTSIDE THE SCROLLER (review round). It is the way back to the unfiltered
 * list, and the same first-open scroll that puts the current month in view had pushed it
 * off the left edge - the one tab a buyer reaches for after pressing a month was the one
 * tab they could not see.
 */
export function OrderInquiryMonthStrip({
  months,
  active,
  onSelect,
}: {
  months: OrderInquiryMonthTotal[];
  /** Empty string reads as "All". */
  active: string;
  onSelect: (month: string) => void;
}) {
  // The LOCAL month, never `toISOString()`: in Malaysia (+08) the first eight hours of
  // every 1st of the month are still the previous month in UTC, so the strip would have
  // scrolled to the month that just ended.
  const currentMonth = React.useMemo(() => format(new Date(), 'yyyy-MM'), []);
  const currentRef = React.useRef<HTMLButtonElement | null>(null);
  const scrolled = React.useRef(false);

  React.useEffect(() => {
    if (scrolled.current || !currentRef.current) return;
    scrolled.current = true;
    currentRef.current.scrollIntoView({ inline: 'center', block: 'nearest' });
  }, [months]);

  const withRows = months.filter((entry) => entry.rows > 0);
  if (withRows.length === 0) return null;

  return (
    <div
      data-testid="order-inquiry-month-strip"
      className="flex items-start gap-1.5 pb-1"
    >
      <MonthTab
        label="All"
        count={null}
        selected={active === ''}
        onClick={() => onSelect('')}
      />
      <div className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto">
        {withRows.map((entry) => (
          <MonthTab
            key={entry.month}
            ref={entry.month === currentMonth ? currentRef : undefined}
            label={entry.label ?? deliveryMonthLabel(entry.month) ?? entry.month}
            count={entry.rows}
            selected={active === entry.month}
            onClick={() => onSelect(entry.month)}
          />
        ))}
      </div>
    </div>
  );
}

const MonthTab = React.forwardRef<
  HTMLButtonElement,
  {
    label: string;
    count: number | null;
    selected: boolean;
    onClick: () => void;
  }
>(function MonthTab({ label, count, selected, onClick }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      data-testid={`order-inquiry-month-tab-${label}`}
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        'shrink-0 whitespace-nowrap rounded-md border px-2.5 py-1.5 text-xs font-medium tabular-nums transition-colors',
        selected
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-input hover:bg-accent',
      )}
    >
      {label}
      {count !== null ? ` (${count})` : ''}
    </button>
  );
});
