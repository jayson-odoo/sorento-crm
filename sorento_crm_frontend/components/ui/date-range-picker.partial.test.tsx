/**
 * DATE-PICKER-UNIFY AC10: the range field clears on empty text, accepts a half-open range, and its
 * label round-trips (a lone From reads `05/11/2026 -`, a lone To reads `- 30/11/2026`).
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DateRangePicker } from './date-range-picker';

function setup(from: string | null, to: string | null) {
  const onChange = vi.fn();
  render(<DateRangePicker from={from} to={to} onChange={onChange} aria-label="Window" />);
  return { onChange, input: screen.getByLabelText('Window') as HTMLInputElement };
}

function typeAndBlur(input: HTMLInputElement, text: string) {
  fireEvent.change(input, { target: { value: text } });
  fireEvent.blur(input);
}

describe('DateRangePicker partial ranges (AC10)', () => {
  it('emptying the text and blurring clears both ends', () => {
    const { onChange, input } = setup('2026-11-01', '2026-11-30');
    typeAndBlur(input, '');
    expect(onChange).toHaveBeenCalledWith({ from: null, to: null });
  });

  it('"05/11/2026 -" sets From only', () => {
    const { onChange, input } = setup(null, null);
    typeAndBlur(input, '05/11/2026 -');
    expect(onChange).toHaveBeenCalledWith({ from: '2026-11-05', to: null });
  });

  it('"- 30/11/2026" sets To only', () => {
    const { onChange, input } = setup(null, null);
    typeAndBlur(input, '- 30/11/2026');
    expect(onChange).toHaveBeenCalledWith({ from: null, to: '2026-11-30' });
  });

  it('a From-only value reads "05/11/2026 -"', () => {
    const { input } = setup('2026-11-05', null);
    expect(input.value).toBe('05/11/2026 -');
  });

  it('a To-only value reads "- 30/11/2026"', () => {
    const { input } = setup(null, '2026-11-30');
    expect(input.value).toBe('- 30/11/2026');
  });
});
