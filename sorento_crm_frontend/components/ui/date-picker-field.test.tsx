/**
 * `DatePickerField` (DATE-PICKER-UNIFY AC1-AC3, AC9): the string-valued wrapper around `DatePicker`.
 * `value` and `onChange` speak `YYYY-MM-DD | null`, the shape the API already uses, so a caller
 * swapping a native `<input type="date">` changes no payload. The typed text is `dd/mm/yyyy` in
 * every browser locale and no browser timezone shifts the day.
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { DatePickerField } from './date-picker';

function setup(props: Partial<React.ComponentProps<typeof DatePickerField>> = {}) {
  const onChange = vi.fn();
  render(<DatePickerField value={null} onChange={onChange} ariaLabel="Due" {...props} />);
  const input = screen.getByLabelText('Due') as HTMLInputElement;
  return { onChange, input };
}

function suite() {
  it('shows a stored 2026-11-05 as 05/11/2026', () => {
    const { input } = setup({ value: '2026-11-05' });
    expect(input.value).toBe('05/11/2026');
  });

  it('typing 05/11/2026 and blurring emits 2026-11-05', () => {
    const { onChange, input } = setup();
    fireEvent.change(input, { target: { value: '05/11/2026' } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledWith('2026-11-05');
  });

  it('typing 5/11/2026 and pressing Enter emits 2026-11-05', () => {
    const { onChange, input } = setup();
    fireEvent.change(input, { target: { value: '5/11/2026' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('2026-11-05');
  });

  it('typing 31/02/2026 and blurring emits nothing', () => {
    const { onChange, input } = setup({ value: '2026-11-05' });
    fireEvent.change(input, { target: { value: '31/02/2026' } });
    fireEvent.blur(input);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('clearing the text and blurring emits null when not required and a value is set', () => {
    const { onChange, input } = setup({ value: '2026-11-05' });
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledWith(null);
  });
}

describe('DatePickerField', () => {
  suite();
});

describe.each(['America/New_York', 'Asia/Kuala_Lumpur'])('DatePickerField under TZ %s', (zone) => {
  const original = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = zone;
  });
  afterAll(() => {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  });

  it('displays 2026-11-05 as 05/11/2026 with no day shift', () => {
    const { input } = setup({ value: '2026-11-05' });
    expect(input.value).toBe('05/11/2026');
  });

  it('typing 05/11/2026 emits 2026-11-05 with no day shift', () => {
    const { onChange, input } = setup();
    fireEvent.change(input, { target: { value: '05/11/2026' } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledWith('2026-11-05');
  });
});
