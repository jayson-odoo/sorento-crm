import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/sponsorship-forms/report',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null, toString: () => '' }),
}));

// DataGrid persists column prefs through this hook (which fires network); without the stub
// the grid renders skeletons forever and no row can be asserted.
const prefsGate = vi.hoisted(() => ({ isLoading: false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: prefsGate.isLoading }),
}));

// The filter bar's controls are the shared searchable selects. Native equivalents here:
// the assertions are about which STATE the page is in, not about popover mechanics.
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
    <select aria-label={id} value={value} onChange={(e) => onChange?.(e.target.value)}>
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
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <div aria-label={placeholder ?? 'multi-select'}>
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

// Container pulls SettingsProvider context this unit test does not need.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const fetchReportMeta = vi.fn();
const runReport = vi.fn();
const fetchReportViews = vi.fn();
const exportReport = vi.fn();

vi.mock('@/services/reportService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/reportService')>();
  return {
    ...actual,
    fetchReportMeta: (...args: unknown[]) => fetchReportMeta(...args),
    runReport: (...args: unknown[]) => runReport(...args),
    fetchReportViews: (...args: unknown[]) => fetchReportViews(...args),
    exportReport: (...args: unknown[]) => exportReport(...args),
    createReportView: vi.fn(),
    deleteReportView: vi.fn(),
    publishReportView: vi.fn(),
    setDefaultReportView: vi.fn(),
  };
});

import type { ReportMeta, ReportResult } from '@/services/reportService';
import { ReportPage } from './ReportPage';

const PERIOD = { kind: 'year' as const, year: 2026 };

const META = {
  key: 'zzt_sort',
  title: 'ZZT sort',
  permission: 'sales.reports.view',
  dataset_param: null,
  pivot_rows_by: null,
  opens_on: 'summary',
  params: [{ kind: 'period', key: 'period', label: 'Period', default: PERIOD, years: [2026] }],
  catalog: [
    { key: 'sales_agent', label: 'Sales agent', type: 'text', tag: 'dimension', unavailable_for: [] },
    { key: 'debtor_type', label: 'Debtor type', type: 'text', tag: 'dimension', unavailable_for: [] },
    { key: 'sales_value', label: 'Sales value', type: 'money', tag: 'measure', unavailable_for: [] },
  ],
  default_view: {
    params: { period: PERIOD },
    detail: { columns: ['sales_agent'], order: ['sales_agent'] },
    pivot: { rows: 'sales_agent', cols: 'debtor_type', measures: ['sales_value'] },
  },
  can_publish: false,
} as unknown as ReportMeta;

const RESULT = {
  key: 'zzt_sort',
  period_label: '2026',
  row_count: 1,
  layouts: {
    detail: {
      key: 'detail',
      title: 'Lines',
      columns: [{ key: 'sales_agent', label: 'Sales agent', type: 'text', size: 140 }],
      column_groups: [],
      rows: [{ sales_agent: 'ALICE' }],
      totals: {},
    },
    summary: {
      key: 'summary',
      title: 'Sales by agent',
      row_dim: { key: 'sales_agent', label: 'Sales agent' },
      col_dim: { key: 'debtor_type', label: 'Debtor type', values: ['BRAVAT'] },
      measures: [{ key: 'sales_value', label: 'Sales value', type: 'money' }],
      row_values: ['ALICE'],
      cells: { ALICE: { BRAVAT: { sales_value: '10.00' } } },
      row_totals: { ALICE: { sales_value: '10.00' } },
      col_totals: { BRAVAT: { sales_value: '10.00' } },
      grand_total: { sales_value: '10.00' },
    },
  },
} as unknown as ReportResult;

type View = {
  detail: { sort?: { key: string; dir: string } | null };
  pivot: { sort?: { key: string; dir: string } | null };
};
const lastView = () => (runReport.mock.calls.at(-1) as [string, unknown, View])[2];

function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <ReportPage reportKey="zzt_sort" breadcrumb={[{ label: 'Sales' }, { label: 'ZZT sort' }]} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  prefsGate.isLoading = false;
  fetchReportMeta.mockResolvedValue(META);
  runReport.mockResolvedValue(RESULT);
  fetchReportViews.mockResolvedValue({ mine: [], shared: [] });
  exportReport.mockResolvedValue({ download_id: 'd1', filename: 'x.xlsx' });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('ReportPage server-side sort', () => {
  it('a summary header click re-runs with the pivot sort and a second click flips it', async () => {
    render();
    fireEvent.click(await screen.findByRole('button', { name: 'Sort by BRAVAT' }));
    await waitFor(() => expect(lastView().pivot.sort).toEqual({ key: 'BRAVAT', dir: 'asc' }));

    fireEvent.click(screen.getByRole('button', { name: 'Sort by BRAVAT' }));
    await waitFor(() => expect(lastView().pivot.sort).toEqual({ key: 'BRAVAT', dir: 'desc' }));
    expect(screen.getByRole('button', { name: 'Sort by BRAVAT' }).getAttribute('data-sort')).toBe(
      'desc',
    );
  });

  it('the row label and Total headers sort by their reserved keys', async () => {
    render();
    fireEvent.click(await screen.findByRole('button', { name: 'Sort by Sales agent' }));
    await waitFor(() => expect(lastView().pivot.sort).toEqual({ key: '__row__', dir: 'asc' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sort by Total' }));
    await waitFor(() => expect(lastView().pivot.sort).toEqual({ key: '__total__', dir: 'asc' }));
  });

  it('a detail header click re-runs with the detail sort', async () => {
    render();
    const tab = await screen.findByRole('tab', { name: /Lines/ });
    fireEvent.mouseDown(tab);
    fireEvent.click(tab);
    fireEvent.click(await screen.findByRole('button', { name: /Sales agent/ }));
    await waitFor(() => expect(lastView().detail.sort).toEqual({ key: 'sales_agent', dir: 'asc' }));
  });

  it('the sort travels with the exported view', async () => {
    render();
    fireEvent.click(await screen.findByRole('button', { name: 'Sort by Total' }));
    await waitFor(() => expect(lastView().pivot.sort).toEqual({ key: '__total__', dir: 'asc' }));
    fireEvent.click(screen.getAllByRole('button', { name: /Export to Excel/i })[0]);
    await waitFor(() => expect(exportReport).toHaveBeenCalled());
    expect(JSON.stringify(exportReport.mock.calls[0])).toContain('"sort":{"key":"__total__","dir":"asc"}');
  });
});
