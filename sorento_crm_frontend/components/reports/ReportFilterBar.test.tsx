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
import { render, screen } from '@testing-library/react';

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
