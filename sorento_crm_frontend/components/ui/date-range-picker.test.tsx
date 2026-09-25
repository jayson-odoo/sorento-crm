/**
 * `DateRangePicker` (R14c, owner 24 Sep, reversing R14b on sight): "use the same date
 * range component but I can type; I don't want two different date fields." ONE shared
 * control stays the standard for any "X from / X to" pair (the component's own file
 * header) - it just gains a typeable trigger instead of the plain label+icon `Button` it
 * renders today.
 *
 * Contract (read off `date-range-picker.tsx` itself, current props untouched -
 * `from`/`to` as `YYYY-MM-DD | null`, `onChange({ from, to })` emitted together, both
 * `YYYY-MM-DD | null`, `placeholder`, `disabled`, `className`, `id`, `'aria-label'`):
 * the trigger becomes a text input showing `DD/MM/YYYY - DD/MM/YYYY` (the placeholder
 * stays the same string for the empty state); typing a full pair and blurring or
 * pressing Enter emits the range; typing a single `DD/MM/YYYY` emits `from = to` = that
 * day; unparseable text leaves the value unchanged and restores the previous label on
 * blur; the calendar popover (unchanged) still opens off an icon button beside the
 * input and click-selection on it still works; Clear still empties both ends.
 *
 * No repo test today drives the real react-day-picker `Calendar` grid under jsdom -
 * every existing caller (`SalesOrdersList.filters.test.tsx`, `SalesAgentDetail.test.tsx`,
 * `ReportFilterBar.test.tsx`) mocks `DateRangePicker` wholesale. Test (d) below is the
 * first to drive the real Calendar: react-day-picker's day cells expose their FULL
 * accessible date as the aria-label ("Sunday, 5 November 2026" or similar, locale/ICU
 * dependent), but their VISIBLE text is always just the bare day number - so it queries
 * `button` elements by exact `textContent`, not by role name, to stay independent of
 * exact date-string formatting. System time is pinned so the calendar opens already on
 * November 2026 with no month navigation needed.
 *
 * The icon button beside the input is assumed to follow the sibling `DatePicker`
 * (`@/components/ui/date-picker.tsx`) component's own naming convention, extended for a
 * range: `aria-label={ariaLabel ? `Pick a date range for ${ariaLabel}` : 'Pick a date range'}`
 * (the DatePicker's own is `Pick a date for ${ariaLabel}` / `Pick a date`). This is a
 * naming CHOICE for the coder to match or to change together with this test, not a prop.
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DateRangePicker } from './date-range-picker';

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 10, 15));
});

afterEach(() => {
  vi.useRealTimers();
});

function clickDay(dayNumber: number) {
  const buttons = screen.getAllByRole('button');
  const day = buttons.find((button) => button.textContent?.trim() === String(dayNumber));
  if (!day) throw new Error(`No calendar day button with text "${dayNumber}"`);
  fireEvent.click(day);
}

describe('DateRangePicker (R14c)', () => {
  it('typing a full "DD/MM/YYYY - DD/MM/YYYY" pair and pressing Enter emits the range', () => {
    // RED today: the trigger is a `<button>` with no typeable value at all - there is
    // no `textbox` role to find in the first place.
    const onChange = vi.fn();
    render(<DateRangePicker from={null} to={null} onChange={onChange} aria-label="Delivery" />);

    const input = screen.getByLabelText('Delivery') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '01/11/2026 - 30/11/2026' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith({ from: '2026-11-01', to: '2026-11-30' });
  });

  it('typing a single "DD/MM/YYYY" and blurring emits from = to = that day', () => {
    const onChange = vi.fn();
    render(<DateRangePicker from={null} to={null} onChange={onChange} aria-label="Delivery" />);

    const input = screen.getByLabelText('Delivery') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '05/11/2026' } });
    fireEvent.blur(input);

    expect(onChange).toHaveBeenCalledWith({ from: '2026-11-05', to: '2026-11-05' });
  });

  it('unparseable text emits nothing and restores the previous label on blur', () => {
    const onChange = vi.fn();
    render(
      <DateRangePicker
        from="2026-11-01"
        to="2026-11-30"
        onChange={onChange}
        aria-label="Delivery"
      />,
    );

    const input = screen.getByLabelText('Delivery') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'garbage' } });
    fireEvent.blur(input);

    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe('01/11/2026 - 30/11/2026');
  });

  it('the calendar button still opens the popover and clicking a day still works', async () => {
    const onChange = vi.fn();
    render(<DateRangePicker from={null} to={null} onChange={onChange} aria-label="Delivery" />);

    // See the file header: assumed to mirror the sibling `DatePicker`'s own
    // `Pick a date for X` convention, extended for a range.
    fireEvent.click(screen.getByRole('button', { name: 'Pick a date range for Delivery' }));
    clickDay(5);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ from: '2026-11-05' }),
    );
  });

  it('Clear empties both ends', () => {
    const onChange = vi.fn();
    render(
      <DateRangePicker
        from="2026-11-01"
        to="2026-11-30"
        onChange={onChange}
        aria-label="Delivery"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Pick a date range for Delivery' }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));

    expect(onChange).toHaveBeenCalledWith({ from: null, to: null });
  });
});
