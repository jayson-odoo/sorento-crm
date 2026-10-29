/**
 * OI-LINE-SPLIT AC-G8: a typed date commits when the person LEAVES the box (blur or Enter),
 * never per keystroke; a calendar pick commits at once.
 */
import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { DatePicker } from './date-picker';

afterEach(cleanup);

function Controlled({ onChange }: { onChange: (d: Date | undefined) => void }) {
  const [value, setValue] = useState<Date | undefined>(new Date(2026, 10, 20));
  return (
    <DatePicker
      ariaLabel="Day"
      value={value}
      onChange={(d) => {
        onChange(d);
        setValue(d);
      }}
    />
  );
}

const ymd = (d: Date | undefined) =>
  d ? [d.getFullYear(), d.getMonth() + 1, d.getDate()] : undefined;
const box = () => screen.getByLabelText('Day') as HTMLInputElement;

describe('DatePicker commits on leave', () => {
  it('shows the value as 20/11/2026', () => {
    render(<Controlled onChange={vi.fn()} />);
    expect(box().value).toBe('20/11/2026');
  });

  it('deleting one 1 (20/1/2026) does not commit; blur commits 2026-01-20 once', () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    fireEvent.change(box(), { target: { value: '20/1/2026' } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.blur(box());
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(ymd(onChange.mock.calls[0][0])).toEqual([2026, 1, 20]);
  });

  it('typing 20/11/2029 then Enter commits 2029-11-20', () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    fireEvent.change(box(), { target: { value: '20/11/2029' } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.keyDown(box(), { key: 'Enter' });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(ymd(onChange.mock.calls[0][0])).toEqual([2029, 11, 20]);
  });

  it('an invalid final text on blur commits no date', () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    fireEvent.change(box(), { target: { value: '31/02/2026' } });
    fireEvent.blur(box());
    expect(onChange).not.toHaveBeenCalled();
  });

  it('picking a day in the calendar commits at once', async () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pick a date for Day' }));
    const day = (await screen.findAllByRole('button')).find(
      (b) => b.textContent === '15' && b.closest('[role="grid"], table'),
    );
    expect(day, 'day 15 in the open calendar').toBeTruthy();
    fireEvent.click(day!);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(ymd(onChange.mock.calls[0][0])?.[2]).toBe(15);
  });
});
