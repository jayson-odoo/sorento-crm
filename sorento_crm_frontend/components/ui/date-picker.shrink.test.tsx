/**
 * DATE-PICKER-UNIFY: in a narrow panel (Chat History filter, w-72) the typed input must be able to
 * shrink, or it pushes the calendar button out of the box and clips it. A flex child keeps its
 * intrinsic min width unless it carries `min-w-0`; the button must not be squeezed (`shrink-0`).
 */
import * as React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DatePicker } from './date-picker';
import { DateRangePicker } from './date-range-picker';

describe('DateRangePicker shrinks inside a narrow flex row', () => {
  it('root is w-full, the text input has min-w-0 and the calendar button has shrink-0', () => {
    const { container } = render(
      <DateRangePicker from={null} to={null} onChange={() => {}} aria-label="Window" />,
    );
    const input = screen.getByLabelText('Window');
    const button = screen.getByRole('button', { name: 'Pick a date range for Window' });
    expect((container.firstElementChild as HTMLElement).className).toContain('w-full');
    expect(input.className).toContain('min-w-0');
    expect(button.className).toContain('shrink-0');
  });
});

describe('DatePicker shrinks inside a narrow flex row', () => {
  it('the text input has min-w-0 and the calendar button has shrink-0', () => {
    render(<DatePicker onChange={() => {}} ariaLabel="Day" />);
    const input = screen.getByLabelText('Day');
    const button = screen.getByRole('button', { name: 'Pick a date for Day' });
    expect(input.className).toContain('min-w-0');
    expect(button.className).toContain('shrink-0');
  });
});
