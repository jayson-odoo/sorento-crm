/**
 * The report filter bar, rendered from param meta alone (AC-C6, AC-E4).
 *
 * Two rules it has to keep whatever the data says:
 *
 * - The year the report is OPEN ON is always offerable. Offering only the years the
 *   dataset holds rows for leaves the control blank in a year nobody has filed a form in
 *   yet, which reads as a broken screen on 1 January.
 * - A date RANGE is one control (ADR 1c), not two date pickers the user can cross over.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Native equivalents of the shared searchable selects: what is asserted here is which
// OPTIONS a control offers, not popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <select
      data-testid={id}
      aria-label={placeholder}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: () => <div />,
}));

// The range picker is a popover calendar. What is asserted here is what the bar DOES with
// the two ends it is handed, so the stub just hands them over.
vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: ({
    onChange,
    ...props
  }: {
    onChange: (next: { from: string | null; to: string | null }) => void;
    'aria-label'?: string;
  }) => (
    <div>
      <button type="button" aria-label={props['aria-label']} />
      <button type="button" onClick={() => onChange({ from: null, to: null })}>
        Clear dates
      </button>
      <button type="button" onClick={() => onChange({ from: '2026-05-01', to: null })}>
        Pick a start
      </button>
    </div>
  ),
}));

import { ReportFilterBar } from './ReportFilterBar';
import type { ReportParamMeta, ReportPeriod } from '@/services/reportService';

function periodParam(years: number[], fallback: ReportPeriod): ReportParamMeta {
  return { kind: 'period', key: 'period', label: 'Period', default: fallback, years };
}

function renderBar(param: ReportParamMeta, period: ReportPeriod) {
  const onChange = vi.fn();
  render(<ReportFilterBar params={[param]} values={{ period }} onChange={onChange} />);
  return onChange;
}

function optionsOf(testId: string): string[] {
  return Array.from(screen.getByTestId(testId).querySelectorAll('option')).map((o) => o.value);
}

describe('ReportFilterBar period', () => {
  it('offers the year it is open on even when the dataset holds no rows for it', () => {
    // 1 January: nothing is filed in the new year yet, so `years` is last year only.
    renderBar(periodParam([2025], { kind: 'year', year: 2026 }), { kind: 'year', year: 2026 });

    const select = screen.getByTestId('report-param-period') as HTMLSelectElement;
    expect(optionsOf('report-param-period')).toContain('2026');
    expect(select.value).toBe('2026');
  });

  it('offers the current year, newest first, with no duplicates', () => {
    const thisYear = new Date().getFullYear();
    renderBar(periodParam([2024, 2023], { kind: 'year', year: 2024 }), {
      kind: 'year',
      year: 2024,
    });

    const years = optionsOf('report-param-period').filter((v) => /^\d{4}$/.test(v));
    expect(years).toContain(String(thisYear));
    expect(new Set(years).size).toBe(years.length);
    expect([...years]).toEqual([...years].sort((a, b) => Number(b) - Number(a)));
  });

  it('offers a saved view year the dataset no longer holds', () => {
    renderBar(periodParam([2026], { kind: 'year', year: 2026 }), { kind: 'year', year: 2019 });

    expect(optionsOf('report-param-period')).toContain('2019');
  });

  it('picks a custom range with ONE range control, not two date pickers', () => {
    renderBar(periodParam([2026], { kind: 'year', year: 2026 }), {
      kind: 'custom',
      from: '2026-02-01',
      to: '2026-03-15',
    });

    expect(screen.getByRole('button', { name: /Custom date range/ })).toBeInTheDocument();
    expect(screen.queryByLabelText('From')).toBeNull();
    expect(screen.queryByLabelText('To')).toBeNull();
  });
});

describe('ReportFilterBar custom dates', () => {
  const period: ReportPeriod = { kind: 'custom', from: '2026-02-01', to: '2026-03-15' };

  it('clears both ends when the picker is cleared', () => {
    // Mapping a null end back onto the previous value made Clear a no-op: the button moved
    // nothing on screen and the same range ran again.
    const onChange = renderBar(periodParam([2026], { kind: 'year', year: 2026 }), period);

    fireEvent.click(screen.getByRole('button', { name: 'Clear dates' }));

    expect(onChange).toHaveBeenCalledWith('period', { kind: 'custom', from: '', to: '' });
  });

  it('does not keep the old end when a new start is picked', () => {
    // The first click of a two-click range carries a start only. Keeping the previous end
    // can put the end BEFORE the start, which the backend answers with a 422.
    const onChange = renderBar(periodParam([2026], { kind: 'year', year: 2026 }), period);

    fireEvent.click(screen.getByRole('button', { name: 'Pick a start' }));

    expect(onChange).toHaveBeenCalledWith('period', {
      kind: 'custom',
      from: '2026-05-01',
      to: '',
    });
  });
});

describe('ReportFilterBar month chips (AC-G1)', () => {
  it('offers All and the twelve months while the period is a year', () => {
    renderBar(periodParam([2025], { kind: 'year', year: 2025 }), { kind: 'year', year: 2025 });

    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
    for (const month of ['Jan', 'Jun', 'Dec']) {
      expect(screen.getByRole('button', { name: month })).toHaveAttribute('aria-pressed', 'false');
    }
  });

  it('a month chip is a one-month period, which is the client monthly sheet', () => {
    const onChange = renderBar(periodParam([2025], { kind: 'year', year: 2025 }), {
      kind: 'year',
      year: 2025,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mar' }));

    expect(onChange).toHaveBeenCalledWith('period', {
      kind: 'month_range',
      year: 2025,
      from_month: 3,
      to_month: 3,
    });
  });

  it('reflects the month the period is already on, and All returns to the year', () => {
    const onChange = renderBar(periodParam([2025], { kind: 'year', year: 2025 }), {
      kind: 'month_range',
      year: 2025,
      from_month: 3,
      to_month: 3,
    });

    expect(screen.getByRole('button', { name: 'Mar' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(onChange).toHaveBeenCalledWith('period', { kind: 'year', year: 2025 });
  });

  it('keeps Year, From and To beside the chips while the range is one month', () => {
    // The chip and the selects describe the SAME period and must agree. Hiding them left a
    // single month with no way out: Period read "Month range", so re-picking it changed
    // nothing, and Mar could not become Mar..Jun without going back through All.
    renderBar(periodParam([2025], { kind: 'year', year: 2025 }), {
      kind: 'month_range',
      year: 2025,
      from_month: 3,
      to_month: 3,
    });

    expect(screen.getByTestId('report-param-period-year')).toHaveValue('2025');
    expect(screen.getByTestId('report-param-period-from')).toHaveValue('3');
    expect(screen.getByTestId('report-param-period-to')).toHaveValue('3');
    expect(screen.getByRole('button', { name: 'Mar' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('widens a single month into a range from the To control', () => {
    const onChange = renderBar(periodParam([2025], { kind: 'year', year: 2025 }), {
      kind: 'month_range',
      year: 2025,
      from_month: 3,
      to_month: 3,
    });

    fireEvent.change(screen.getByTestId('report-param-period-to'), { target: { value: '6' } });

    expect(onChange).toHaveBeenCalledWith('period', {
      kind: 'month_range',
      year: 2025,
      from_month: 3,
      to_month: 6,
    });
  });

  it('names the chip row for a screen reader', () => {
    renderBar(periodParam([2025], { kind: 'year', year: 2025 }), { kind: 'year', year: 2025 });

    expect(screen.getByRole('group', { name: 'Month' })).toBeInTheDocument();
  });

  it('leaves a multi-month range to the From and To controls', () => {
    renderBar(periodParam([2025], { kind: 'year', year: 2025 }), {
      kind: 'month_range',
      year: 2025,
      from_month: 3,
      to_month: 6,
    });

    expect(screen.queryByRole('button', { name: 'All' })).toBeNull();
    expect(screen.getByTestId('report-param-period-from')).toBeInTheDocument();
  });

  it('shows no chips on a custom date range', () => {
    renderBar(periodParam([2025], { kind: 'year', year: 2025 }), {
      kind: 'custom',
      from: '2025-02-01',
      to: '2025-03-15',
    });

    expect(screen.queryByRole('button', { name: 'Jan' })).toBeNull();
  });
});
