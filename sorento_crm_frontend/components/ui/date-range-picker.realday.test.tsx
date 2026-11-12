/**
 * DATE-PICKER-UNIFY AC4: the range field refuses a day that does not exist. Today
 * `new Date(2026, 1, 31)` rolls 31/02 into 03/03 and the range is emitted as if typed that way.
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DateRangePicker } from './date-range-picker';

describe('DateRangePicker real-day check (AC4)', () => {
  it('31/02/2026 - 01/03/2026 emits nothing and the text reverts to the previous label', () => {
    const onChange = vi.fn();
    render(
      <DateRangePicker from="2026-11-01" to="2026-11-30" onChange={onChange} aria-label="Window" />,
    );
    const input = screen.getByLabelText('Window') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '31/02/2026 - 01/03/2026' } });
    fireEvent.blur(input);

    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe('01/11/2026 - 30/11/2026');
  });

  it('control: 01/11/2026 - 30/11/2026 emits both ends', () => {
    const onChange = vi.fn();
    render(<DateRangePicker from={null} to={null} onChange={onChange} aria-label="Window" />);
    const input = screen.getByLabelText('Window') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '01/11/2026 - 30/11/2026' } });
    fireEvent.blur(input);

    expect(onChange).toHaveBeenCalledWith({ from: '2026-11-01', to: '2026-11-30' });
  });
});
