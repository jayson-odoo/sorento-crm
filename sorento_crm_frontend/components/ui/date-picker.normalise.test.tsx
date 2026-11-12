/**
 * DATE-PICKER-UNIFY: leaving the box always rewrites the text to the committed value, so
 * `8/12/2026` never lingers when it is the day already held, and junk reverts (the same rule
 * as DateRangePicker).
 */
import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { DatePicker, DatePickerField } from './date-picker';

afterEach(cleanup);

const box = () => screen.getByLabelText('Day') as HTMLInputElement;
function typeAndLeave(text: string) {
  fireEvent.change(box(), { target: { value: text } });
  fireEvent.blur(box());
}

function Date_({ initial, onChange }: { initial?: Date; onChange: (d?: Date) => void }) {
  const [value, setValue] = useState<Date | undefined>(initial);
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

function Field({ initial, onChange }: { initial: string | null; onChange: (v: string | null) => void }) {
  const [value, setValue] = useState<string | null>(initial);
  return (
    <DatePickerField
      ariaLabel="Day"
      value={value}
      onChange={(v) => {
        onChange(v);
        setValue(v);
      }}
    />
  );
}

describe('DatePicker normalises on leave', () => {
  it('same day typed short (8/12/2026) is rewritten to 08/12/2026 and onChange is not called', () => {
    const onChange = vi.fn();
    render(<Date_ initial={new Date(2026, 11, 8)} onChange={onChange} />);
    typeAndLeave('8/12/2026');
    expect(onChange).not.toHaveBeenCalled();
    expect(box().value).toBe('08/12/2026');
  });

  it('from empty, 8/12/2026 commits once and the box reads 08/12/2026', () => {
    const onChange = vi.fn();
    render(<Date_ onChange={onChange} />);
    typeAndLeave('8/12/2026');
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(box().value).toBe('08/12/2026');
  });

  it('unparseable text (8/12/20) reverts to the last committed 08/12/2026', () => {
    const onChange = vi.fn();
    render(<Date_ initial={new Date(2026, 11, 8)} onChange={onChange} />);
    typeAndLeave('8/12/20');
    expect(onChange).not.toHaveBeenCalled();
    expect(box().value).toBe('08/12/2026');
  });
});

describe('DatePickerField normalises on leave', () => {
  it('same day typed short is rewritten to 08/12/2026 and onChange is not called', () => {
    const onChange = vi.fn();
    render(<Field initial="2026-12-08" onChange={onChange} />);
    typeAndLeave('8/12/2026');
    expect(onChange).not.toHaveBeenCalled();
    expect(box().value).toBe('08/12/2026');
  });

  it('from empty, 8/12/2026 commits 2026-12-08 once and the box reads 08/12/2026', () => {
    const onChange = vi.fn();
    render(<Field initial={null} onChange={onChange} />);
    typeAndLeave('8/12/2026');
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('2026-12-08');
    expect(box().value).toBe('08/12/2026');
  });

  it('unparseable text (8/12/20) reverts to the last committed 08/12/2026', () => {
    const onChange = vi.fn();
    render(<Field initial="2026-12-08" onChange={onChange} />);
    typeAndLeave('8/12/20');
    expect(onChange).not.toHaveBeenCalled();
    expect(box().value).toBe('08/12/2026');
  });
});
