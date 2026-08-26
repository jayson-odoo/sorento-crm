/**
 * Configure summary (AC-C2, AC-C6) - reshaping the pivot without a developer.
 *
 * Rows and Columns offer every catalog DIMENSION, Measures every catalog MEASURE, and the
 * dialog refuses to pivot a dimension against itself: the engine answers 422 for that, and
 * a validation message beats a failed run the user has to interpret.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options = [],
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
  }) => (
    <select id={id} value={value} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options = [],
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: Array<{ value: string; label: string }>;
  }) => (
    <div aria-label="Measures">
      {options.map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            aria-label={o.label}
            checked={value.includes(o.value)}
            onChange={(e) =>
              onChange(e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value))
            }
          />
          {o.label}
        </label>
      ))}
    </div>
  ),
}));

import { ConfigureSummaryDialog } from './ConfigureSummaryDialog';
import type { ReportCatalogColumn } from '@/services/reportService';

const CATALOG: ReportCatalogColumn[] = [
  { key: 'sales_agent', label: 'Sales agent', type: 'text', tag: 'dimension' },
  { key: 'month', label: 'Month', type: 'text', tag: 'dimension' },
  { key: 'sponsor_subject', label: 'Sponsor project', type: 'text', tag: 'dimension' },
  { key: 'project_value', label: 'Project value', type: 'money', tag: 'measure' },
  { key: 'sample_price', label: 'Sample price', type: 'money', tag: 'measure' },
  { key: 'purpose', label: 'Purpose', type: 'text', tag: 'text' },
];

const VALUE = { rows: 'sales_agent', cols: 'month', measures: ['project_value'] };

function open(onApply = vi.fn(), onOpenChange = vi.fn()) {
  render(
    <ConfigureSummaryDialog
      open
      onOpenChange={onOpenChange}
      catalog={CATALOG}
      value={VALUE}
      onApply={onApply}
    />,
  );
  return { onApply, onOpenChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('ConfigureSummaryDialog', () => {
  it('offers every dimension for Rows and Columns, and nothing else', () => {
    open();

    const rows = screen.getByLabelText('Rows') as HTMLSelectElement;
    const labels = Array.from(rows.options).map((o) => o.textContent);

    expect(labels).toEqual(['Sales agent', 'Month', 'Sponsor project']);
    // A measure is not a grouping, and neither is a free-text column.
    expect(labels).not.toContain('Project value');
    expect(labels).not.toContain('Purpose');
  });

  it('offers every measure, and only measures, for Measures', () => {
    open();

    expect(screen.getByRole('checkbox', { name: 'Project value' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Sample price' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Sales agent' })).not.toBeInTheDocument();
  });

  it('applies the new shape and closes', () => {
    const { onApply, onOpenChange } = open();

    fireEvent.change(screen.getByLabelText('Rows'), { target: { value: 'sponsor_subject' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sample price' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(onApply).toHaveBeenCalledWith({
      rows: 'sponsor_subject',
      cols: 'month',
      measures: ['project_value', 'sample_price'],
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('refuses to pivot a dimension against itself', () => {
    const { onApply } = open();

    fireEvent.change(screen.getByLabelText('Columns'), { target: { value: 'sales_agent' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByText('Rows and Columns must be different.')).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
  });

  it('refuses a summary with no measure to total', () => {
    const { onApply } = open();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Project value' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByText('Pick at least one measure.')).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
  });
});
