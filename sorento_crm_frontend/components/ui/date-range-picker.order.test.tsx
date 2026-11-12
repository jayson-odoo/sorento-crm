/**
 * DATE-PICKER-UNIFY: the range field refuses an end before the start, the same rule as a day
 * that does not exist (31/02): nothing is emitted and the text reverts.
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DateRangePicker } from './date-range-picker';

describe('DateRangePicker end-before-start check', () => {
  it('30/11/2026 - 01/11/2026 emits nothing and the text reverts to the previous label', () => {
    const onChange = vi.fn();
    render(
      <DateRangePicker from="2026-11-01" to="2026-11-30" onChange={onChange} aria-label="Window" />,
    );
    const input = screen.getByLabelText('Window') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '30/11/2026 - 01/11/2026' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe('01/11/2026 - 30/11/2026');
  });

  it('control: 01/11/2026 - 01/11/2026 emits the same day at both ends', () => {
    const onChange = vi.fn();
    render(<DateRangePicker from={null} to={null} onChange={onChange} aria-label="Window" />);
    const input = screen.getByLabelText('Window') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '01/11/2026 - 01/11/2026' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith({ from: '2026-11-01', to: '2026-11-01' });
  });
});
