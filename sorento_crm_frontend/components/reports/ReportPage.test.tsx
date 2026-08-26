/**
 * ReportPage - the one screen every report is rendered by (AC-C6).
 *
 * The four states a run can be in are what this covers: waiting, nothing to show, refused
 * because the sync cap was hit, and data. The capped one matters most: it is a 422 that is
 * an ANSWER (narrow it, or export instead), so it must read as a warning with an Export
 * button, never as "something went wrong".
 *
 * The page is driven entirely by `GET /reports/{key}` + `POST /run`, so nothing here names
 * a sponsorship column: report #2 renders through the same file.
 */
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
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
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
    <select aria-label={placeholder} value={value} onChange={(e) => onChange?.(e.target.value)}>
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

import { ReportCappedError, type ReportMeta, type ReportResult } from '@/services/reportService';
import { ReportPage } from './ReportPage';

const DEFAULT_VIEW = {
  params: {
    date_basis: 'approved_at',
    period: { kind: 'year' as const, year: 2026 },
    status: ['approved'],
  },
  detail: { columns: ['request_number', 'sales_agent', 'project_value'], order: [] },
  pivot: { rows: 'sales_agent', cols: 'month', measures: ['project_value'] },
};

const META: ReportMeta = {
  key: 'sponsorship',
  title: 'Sponsorship report',
  permission: 'procurement.sponsorship_forms.report',
  params: [
    {
      kind: 'date_basis',
      key: 'date_basis',
      label: 'Date basis',
      default: 'approved_at',
      options: [
        { value: 'approved_at', label: 'Approved' },
        { value: 'request_date', label: 'Form date' },
      ],
    },
    { kind: 'period', key: 'period', label: 'Period', default: { kind: 'year', year: 2026 }, years: [2026, 2025] },
    {
      kind: 'select',
      key: 'status',
      label: 'Status',
      multi: true,
      clearable: true,
      default: ['approved'],
      options: [
        { value: 'approved', label: 'Approved' },
        { value: 'submitted', label: 'Submitted' },
      ],
    },
  ],
  catalog: [
    { key: 'request_number', label: 'PS No', type: 'text', tag: 'dimension' },
    { key: 'sales_agent', label: 'Sales agent', type: 'text', tag: 'dimension' },
    { key: 'month', label: 'Month', type: 'text', tag: 'dimension' },
    { key: 'project_value', label: 'Project value', type: 'money', tag: 'measure' },
  ],
  default_view: DEFAULT_VIEW,
  can_publish: true,
};

const RESULT: ReportResult = {
  key: 'sponsorship',
  period_label: "Jan'26 to Dec'26",
  row_count: 2,
  capped: false,
  layouts: {
    detail: {
      key: 'detail',
      title: 'Sponsorships',
      columns: [
        { key: 'request_number', label: 'PS No', type: 'text' },
        { key: 'sales_agent', label: 'Sales agent', type: 'text' },
        { key: 'project_value', label: 'Project value', type: 'money' },
      ],
      column_groups: [],
      rows: [
        { request_number: 'PSSF26-0310', sales_agent: 'Eric Ng', project_value: '1166830.70' },
        // No value at all: the cell must show "-", never 0.00.
        { request_number: 'PSSF26-0313', sales_agent: 'Amirul', project_value: null },
      ],
      totals: { project_value: '1166830.70' },
    },
    summary: {
      key: 'summary',
      title: 'Summary by salesman',
      row_dim: { key: 'sales_agent', label: 'Sales agent' },
      col_dim: { key: 'month', label: 'Month', values: ['2026-01'], value_labels: { '2026-01': "Jan'26" } },
      measures: [{ key: 'project_value', label: 'Project value', type: 'money' }],
      row_values: ['Eric Ng'],
      cells: { 'Eric Ng': { '2026-01': { project_value: '1166830.70' } } },
      row_totals: { 'Eric Ng': { project_value: '1166830.70' } },
      col_totals: { '2026-01': { project_value: '1166830.70' } },
      grand_total: { project_value: '1166830.70' },
    },
  },
};

const EMPTY: ReportResult = {
  ...RESULT,
  row_count: 0,
  layouts: {
    detail: { ...RESULT.layouts.detail, rows: [], totals: {} },
    summary: { ...RESULT.layouts.summary, row_values: [], cells: {}, row_totals: {}, col_totals: {}, grand_total: {} },
  },
};

function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <ReportPage reportKey="sponsorship" breadcrumb={[{ label: 'Sponsorship Forms' }, { label: 'Report' }]} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchReportMeta.mockResolvedValue(META);
  runReport.mockResolvedValue(RESULT);
  fetchReportViews.mockResolvedValue({ mine: [], shared: [] });
  exportReport.mockResolvedValue({ download_id: 'd1', filename: 'Sponsorship report-2026.xlsx' });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('ReportPage', () => {
  it('waits on skeletons rather than an empty screen while the meta loads', () => {
    fetchReportMeta.mockReturnValue(new Promise(() => {}));
    const { container } = render();

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders the detail rows, the money and the blank cell', async () => {
    render();

    expect(await screen.findByText('PSSF26-0310')).toBeInTheDocument();
    expect(screen.getByText('Eric Ng')).toBeInTheDocument();
    // Once in the row, once in the totals footer.
    expect(screen.getAllByText('1,166,830.70').length).toBe(2);
    // The second row has no project value: a dash, never a zero.
    expect(screen.queryByText('0.00')).not.toBeInTheDocument();
  });

  it('names both tabs, with the row count on the detail one', async () => {
    render();

    expect(await screen.findByRole('tab', { name: /Sponsorships \(2\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Summary by salesman' })).toBeInTheDocument();
  });

  it('shows the summary pivot with its month header and grand total', async () => {
    render();

    // Radix Tabs selects on mousedown, not on click.
    fireEvent.mouseDown(await screen.findByRole('tab', { name: 'Summary by salesman' }), { button: 0 });

    expect(await screen.findByText("Jan'26")).toBeInTheDocument();
    expect(screen.getAllByText('1,166,830.70').length).toBeGreaterThan(0);
  });

  it('says the period is empty rather than showing an empty grid', async () => {
    runReport.mockResolvedValue(EMPTY);
    render();

    expect(await screen.findByText(/No sponsorships in Jan'26 to Dec'26/)).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Sponsorships/ })).not.toBeInTheDocument();
  });

  it('treats a capped run as an answer: the cap message plus an Export button', async () => {
    runReport.mockRejectedValue(
      new ReportCappedError('This run returns more than 5,000 rows. Narrow the period or export to Excel instead.'),
    );
    render();

    expect(await screen.findByText(/more than 5,000 rows/)).toBeInTheDocument();
    const buttons = screen.getAllByRole('button', { name: /Export to Excel/ });
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(exportReport).toHaveBeenCalled());
  });

  it('offers a retry when the run fails outright', async () => {
    runReport.mockRejectedValue(new Error('Server error. Try again or contact support.'));
    render();

    expect(await screen.findByText('Server error. Try again or contact support.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('re-runs against the backend when the date basis changes', async () => {
    render();
    await screen.findByText('PSSF26-0310');

    fireEvent.change(screen.getByLabelText('Date basis'), { target: { value: 'request_date' } });

    await waitFor(() =>
      expect(
        runReport.mock.calls.some((call) => (call[1] as { date_basis: string }).date_basis === 'request_date'),
      ).toBe(true),
    );
  });

  it('exports the view as it stands on screen', async () => {
    render();
    await screen.findByText('PSSF26-0310');

    fireEvent.click(screen.getByRole('button', { name: /Export to Excel/ }));

    await waitFor(() => expect(exportReport).toHaveBeenCalled());
    const [, , view] = exportReport.mock.calls[0] as [string, unknown, { detail: { columns: string[] } }];
    // The visible columns, in the visible order (AC-C5) - not the whole catalog.
    expect(view.detail.columns).toEqual(['request_number', 'sales_agent', 'project_value']);
  });

  it('asks the backend for the whole catalog and hides client-side', async () => {
    render();
    await screen.findByText('PSSF26-0310');

    const [, , view] = runReport.mock.calls[0] as [string, unknown, { detail: { columns: string[] } }];
    expect(view.detail.columns).toEqual([]);
  });
});
