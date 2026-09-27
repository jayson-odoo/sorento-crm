import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen } from '@testing-library/react';
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
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: prefsGate.isLoading,
  }),
}));

// The filter bar's controls are the shared searchable selects. Native equivalents here:
// the assertions are about which STATE the page is in, not about popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <select
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
              onChange(
                e.target.checked
                  ? [...value, o.value]
                  : value.filter((v) => v !== o.value),
              )
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
  Container: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

const fetchReportMeta = vi.fn();
const runReport = vi.fn();
const fetchReportViews = vi.fn();
const exportReport = vi.fn();

vi.mock('@/services/reportService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/services/reportService')>();
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

import type {
  ReportMeta,
  ReportPivotLayout,
  ReportResult,
} from '@/services/reportService';
import { ReportPage } from './ReportPage';

/**
 * S1 (#1267): the Yearly comparison on the kernel's own page. AC-S1-13 (the basis line,
 * the blocks, a chart under each), AC-S1-15 (an empty block keeps its table and says so),
 * AC-R2-17 (variance row, whole ringgit, brackets), AC-R3-3 (Basis is a required filter),
 * and the page opening on the Summary tab.
 */

const MONTHS = [
  '01',
  '02',
  '03',
  '04',
  '05',
  '06',
  '07',
  '08',
  '09',
  '10',
  '11',
  '12',
];
const LABELS = Object.fromEntries(
  MONTHS.map((m, i) => [
    m,
    [
      'JAN',
      'FEB',
      'MAR',
      'APR',
      'MAY',
      'JUN',
      'JUL',
      'AUG',
      'SEP',
      'OCT',
      'NOV',
      'DEC',
    ][i],
  ]),
);

function pivot(
  cells: ReportPivotLayout['cells'],
  variance?: ReportPivotLayout['variance_row'],
): ReportPivotLayout {
  return {
    key: 'summary',
    title: 'Year by month',
    row_dim: { key: 'year', label: 'Year' },
    col_dim: {
      key: 'month_of_year',
      label: 'Month',
      values: MONTHS,
      value_labels: LABELS,
    },
    measures: [{ key: 'sales_value', label: 'RM', type: 'money' }],
    row_values: ['2024', '2025', '2026'],
    cells,
    row_totals: {},
    col_totals: {},
    grand_total: {},
    variance_row: variance ?? null,
    variance_total: variance ? { sales_value: '-30.40' } : null,
    variance_label: variance ? 'VARIANCE' : null,
    chart: 'line',
    whole_units: true,
    show_column_totals: false,
  };
}

const DEALER = pivot(
  {
    '2025': { '01': { sales_value: '100.00' } },
    '2026': { '01': { sales_value: '69.60' } },
  },
  { '01': { sales_value: '-30.40' } },
);
const PROJECT = pivot({});

const META: ReportMeta = {
  key: 'sales_yearly',
  title: 'Yearly comparison',
  permission: 'sales.reports.view',
  opens_on: 'summary',
  params: [
    {
      kind: 'select',
      key: 'company',
      label: 'Company',
      multi: false,
      clearable: false,
      default: [],
      options: [{ value: 'c-1', label: 'Sorento' }],
    },
    {
      kind: 'select',
      key: 'channel',
      label: 'Channel',
      multi: true,
      clearable: true,
      default: ['dealer', 'project'],
      options: [
        { value: 'dealer', label: 'Dealer' },
        { value: 'project', label: 'Project team' },
      ],
    },
    {
      kind: 'select',
      key: 'basis',
      label: 'Basis',
      multi: false,
      clearable: false,
      default: ['delivered'],
      options: [
        { value: 'delivered', label: 'Delivered' },
        { value: 'ordered', label: 'Ordered' },
      ],
    },
    {
      kind: 'date_basis',
      key: 'date_basis',
      label: 'Date basis',
      default: 'order_date',
      options: [{ value: 'order_date', label: 'Order date' }],
    },
    {
      kind: 'period',
      key: 'period',
      label: 'As at',
      default: { kind: 'custom', from: '2024-01-01', to: '2026-09-26' },
      years: [2026, 2025, 2024],
    },
  ],
  catalog: [
    { key: 'year', label: 'Year', type: 'text', tag: 'dimension' },
    { key: 'month_of_year', label: 'Month', type: 'text', tag: 'dimension' },
    { key: 'sales_value', label: 'RM', type: 'money', tag: 'measure' },
  ],
  default_view: {
    params: {
      company: ['c-1'],
      channel: ['dealer', 'project'],
      basis: ['delivered'],
      date_basis: 'order_date',
    },
    detail: { columns: ['so_number', 'sales_value'], order: [] },
    pivot: { rows: 'year', cols: 'month_of_year', measures: ['sales_value'] },
  },
  can_publish: false,
};

const RESULT: ReportResult = {
  key: 'sales_yearly',
  period_label: '01/01/2024 to 26/09/2026',
  row_count: 2,
  note: 'Basis: Delivered (transferred to DO), by sales order date. Sales orders, not invoices.',
  layouts: {
    detail: {
      key: 'detail',
      title: 'Sales order lines',
      columns: [
        { key: 'so_number', label: 'SO no', type: 'text' },
        { key: 'sales_value', label: 'RM', type: 'money' },
      ],
      column_groups: [],
      rows: [
        { so_number: 'SO-1', sales_value: '100.00' },
        { so_number: 'SO-2', sales_value: '69.60' },
      ],
      totals: { sales_value: '169.60' },
    },
    summary: DEALER,
    blocks: [
      { key: 'dealer', title: 'SORENTO - DEALER', summary: DEALER },
      { key: 'project', title: 'SORENTO - PROJECT TEAM', summary: PROJECT },
    ],
  },
};

function render(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return rtlRender(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchReportMeta.mockReset().mockResolvedValue(META);
  fetchReportViews.mockReset().mockResolvedValue({ mine: [], shared: [] });
  runReport.mockReset().mockResolvedValue(RESULT);
  exportReport.mockReset();
});

describe('Yearly comparison on the report page', () => {
  it('opens on the summary with both blocks, their tables, the basis line and a chart per block with sales', async () => {
    render(
      <ReportPage
        reportKey="sales_yearly"
        breadcrumb={[{ label: 'Sales' }, { label: 'Yearly comparison' }]}
      />,
    );
    expect(await screen.findByText('SORENTO - DEALER')).toBeTruthy();
    expect(screen.getByText('SORENTO - PROJECT TEAM')).toBeTruthy();
    expect(screen.getByTestId('report-note').textContent).toBe(RESULT.note);
    expect(screen.getAllByTestId('report-pivot-chart')).toHaveLength(1);
    expect(screen.getAllByTestId('variance-row')).toHaveLength(1);
  });

  it('AC-S1-15: a block with no sales keeps its table and says so', async () => {
    render(
      <ReportPage reportKey="sales_yearly" breadcrumb={[{ label: 'Sales' }]} />,
    );
    await screen.findByText('SORENTO - PROJECT TEAM');
    const project = screen.getByRole('region', {
      name: 'SORENTO - PROJECT TEAM',
    });
    expect(project.textContent).toContain('No sales in this period');
    expect(project.querySelector('table')).toBeTruthy();
  });

  it('AC-R2-17: whole ringgit on screen and the negative variance in brackets', async () => {
    render(
      <ReportPage reportKey="sales_yearly" breadcrumb={[{ label: 'Sales' }]} />,
    );
    const variance = (await screen.findAllByTestId('variance-row'))[0];
    expect(variance.textContent).toContain('VARIANCE');
    expect(variance.textContent).toContain('(30)');
    const dealer = screen.getByRole('region', { name: 'SORENTO - DEALER' });
    expect(dealer.textContent).toContain('100');
    expect(dealer.textContent).not.toContain('100.00');
    // no column-totals row: years are not added to years
    expect(dealer.querySelector('tfoot')?.textContent).not.toMatch(/^Total/);
  });

  it('AC-R3-3: Basis is on the filter bar, required, Delivered by default', async () => {
    render(
      <ReportPage reportKey="sales_yearly" breadcrumb={[{ label: 'Sales' }]} />,
    );
    await screen.findByText('SORENTO - DEALER');
    expect(screen.getByText('Basis')).toBeTruthy();
    const call = runReport.mock.calls[0];
    expect(call[1].basis).toEqual(['delivered']);
  });
});

describe('the filter bar on a one-basis report', () => {
  it('shows no Date basis select when there is only one basis to pick', async () => {
    render(
      <ReportPage reportKey="sales_yearly" breadcrumb={[{ label: 'Sales' }]} />,
    );
    await screen.findByText('SORENTO - DEALER');
    expect(screen.queryByText('Date basis')).toBeNull();
    expect(runReport.mock.calls[0][1].date_basis).toBe('order_date');
  });
});

describe('a shared default view saved on a company the caller cannot pick', () => {
  it('opens on the caller own company instead of running a view that can only answer 403', async () => {
    fetchReportViews.mockReset().mockResolvedValue({
      mine: [],
      shared: [
        {
          id: 'v-1',
          name: 'Mocha dealer',
          is_shared: true,
          is_default: true,
          owner_name: 'Admin',
          view: {
            ...META.default_view,
            params: { ...META.default_view.params, company: ['c-mocha'] },
          },
        },
      ],
    });
    render(
      <ReportPage reportKey="sales_yearly" breadcrumb={[{ label: 'Sales' }]} />,
    );
    await screen.findByText('SORENTO - DEALER');
    expect(runReport.mock.calls[0][1].company).toEqual(['c-1']);
  });
});
