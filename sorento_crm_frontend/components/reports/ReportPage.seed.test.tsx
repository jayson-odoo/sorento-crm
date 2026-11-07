/**
 * SALES-INSIGHTS-P2 P5-1 (tester-first RED): ReportPage given a one-shot `seed` search param (the
 * leaderboard's "Open as report") applies it ONCE instead of the default view, runs with it at once,
 * and drops it from the URL.
 *
 * Seed contract pinned here (JSON in `?seed=`):
 *   { "params": { period?: {kind:'custom',from,to}, brand?: string[], category?: string[], channel?: string[],
 *                 sales_person?: string[], customer?: string[], product?: string[] },
 *     "pivot":  { "rows": <dimension key>, "cols": "all", "measures": ["amount", "qty"] } }
 * `params` is merged over the report's defaults (params the seed omits keep their default).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const nav = vi.hoisted(() => ({ seed: null as string | null, replace: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/sales-and-outstanding',
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useSearchParams: () => ({
    get: (key: string) => (key === 'seed' ? nav.seed : null),
    toString: () => (nav.seed ? `seed=${encodeURIComponent(nav.seed)}` : ''),
  }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ id, value, onChange, options = [] }: {
    id?: string; value?: string; onChange?: (v: string) => void; options?: Array<{ value: string; label: string }>;
  }) => (
    <select aria-label={id} value={value} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => (<option key={o.value} value={o.value}>{o.label}</option>))}
    </select>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ id, value, onChange, options = [] }: {
    id?: string; value: string[]; onChange: (v: string[]) => void; options?: Array<{ value: string; label: string }>;
  }) => (
    <div data-testid={id}>
      {options.map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            aria-label={`${id}:${o.label}`}
            checked={value.includes(o.value)}
            onChange={(e) => onChange(e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value))}
          />
          {o.label}
        </label>
      ))}
    </div>
  ),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const fetchReportMeta = vi.fn();
const runReport = vi.fn();
const fetchReportViews = vi.fn();
vi.mock('@/services/reportService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/reportService')>();
  return {
    ...actual,
    fetchReportMeta: (...a: unknown[]) => fetchReportMeta(...a),
    runReport: (...a: unknown[]) => runReport(...a),
    fetchReportViews: (...a: unknown[]) => fetchReportViews(...a),
    exportReport: vi.fn(),
    createReportView: vi.fn(),
    deleteReportView: vi.fn(),
    publishReportView: vi.fn(),
    setDefaultReportView: vi.fn(),
  };
});

import type { ReportMeta, ReportResult } from '@/services/reportService';
import { ReportPage } from './ReportPage';

const PERIOD = { kind: 'year' as const, year: 2026 };
const sel = (key: string, label: string, options: string[]) => ({
  kind: 'select', key, label, multi: true, clearable: true, default: [],
  options: options.map((o) => ({ value: o, label: o })),
});
const dim = (key: string, label: string) => ({ key, label, type: 'text', tag: 'dimension', unavailable_for: [] });
const measure = (key: string, label: string) => ({ key, label, type: 'money', tag: 'measure', unavailable_for: [] });

const META = {
  key: 'zzt_sales',
  title: 'ZZT sales',
  permission: 'sales.reports.view',
  dataset_param: null,
  pivot_rows_by: null,
  params: [
    { kind: 'period', key: 'period', label: 'Period', default: PERIOD, years: [2026] },
    sel('brand', 'Brand', ['b1', 'b2']),
    sel('category', 'Category', ['c1']),
    sel('channel', 'Channel', ['dealer', 'project']),
    sel('sales_person', 'Sales person', ['LCL', 'SEAN']),
    sel('customer', 'Customer', ['c-1']),
    sel('product', 'Product', ['p-1']),
  ],
  catalog: [
    dim('customer', 'Customer'), dim('sales_person', 'Sales person'), dim('product', 'Product'),
    dim('month', 'Month'), dim('all', 'All'),
    measure('amount', 'RM'), measure('qty', 'Qty'),
  ],
  default_view: {
    params: { period: PERIOD },
    detail: { columns: [], order: [] },
    pivot: { rows: 'customer', cols: 'month', measures: ['amount'] },
  },
  can_publish: false,
} as unknown as ReportMeta;

const SEED = {
  params: {
    period: { kind: 'custom', from: '2026-10-01', to: '2026-10-31' },
    brand: ['b1'],
    sales_person: ['LCL'],
  },
  pivot: { rows: 'sales_person', cols: 'all', measures: ['amount', 'qty'] },
};

type RunArgs = [string, Record<string, unknown>, { pivot: { rows: string; cols: string; measures: string[] } }];

const result = {
  key: 'zzt_sales', period_label: 'x', row_count: 0,
  layouts: {
    detail: { key: 'detail', title: 'Detail', columns: [], column_groups: [], rows: [], totals: {} },
    summary: {
      key: 'summary', title: 'Summary', row_dim: { key: 'sales_person', label: 'Sales person' },
      col_dim: { key: 'all', label: 'All', values: [] }, measures: [], row_values: [], cells: {},
      row_totals: {}, col_totals: {}, grand_total: {},
    },
  },
} as unknown as ReportResult;

function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <ReportPage reportKey="zzt_sales" breadcrumb={[{ label: 'Sales' }, { label: 'Sales & outstanding' }]} />
    </QueryClientProvider>,
  );
}
const runs = () => runReport.mock.calls as unknown as RunArgs[];

beforeEach(() => {
  vi.clearAllMocks();
  nav.seed = null;
  fetchReportMeta.mockResolvedValue(META);
  fetchReportViews.mockResolvedValue({ mine: [], shared: [] });
  runReport.mockResolvedValue(result);
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('ReportPage seed (P5-1)', () => {
  it('without a seed the report opens on its default view', async () => {
    render();
    await waitFor(() => expect(runs().length).toBeGreaterThan(0));
    expect(runs()[0][2].pivot.rows).toBe('customer');
    expect(runs()[0][1].period).toEqual(PERIOD);
  });

  it('a seed replaces the default view: the very first run carries its params and pivot', async () => {
    nav.seed = JSON.stringify(SEED);
    render();
    await waitFor(() => expect(runs().length).toBeGreaterThan(0));
    const [, params, view] = runs()[0];
    expect(params.period).toEqual({ kind: 'custom', from: '2026-10-01', to: '2026-10-31' });
    expect(params.brand).toEqual(['b1']);
    expect(params.sales_person).toEqual(['LCL']);
    expect(view.pivot.rows).toBe('sales_person');
    expect(view.pivot.cols).toBe('all');
    expect(view.pivot.measures).toEqual(['amount', 'qty']);
    // No run ever happened on the default view first.
    expect(runs().every((r) => r[2].pivot.rows === 'sales_person')).toBe(true);
  });

  it('params the seed omits keep the report default (merged, not replaced)', async () => {
    nav.seed = JSON.stringify({ params: { brand: ['b2'] }, pivot: SEED.pivot });
    render();
    await waitFor(() => expect(runs().length).toBeGreaterThan(0));
    expect(runs()[0][1].brand).toEqual(['b2']);
    expect(runs()[0][1].period).toEqual(PERIOD);
  });

  it('drops the seed from the URL once applied', async () => {
    nav.seed = JSON.stringify(SEED);
    window.history.replaceState(null, '', `/sales/sales-and-outstanding?tab=invoiced&seed=${encodeURIComponent(nav.seed)}`);
    const historySpy = vi.spyOn(window.history, 'replaceState');
    render();
    await waitFor(() => expect(runs().length).toBeGreaterThan(0));
    await waitFor(() => {
      const viaRouter = nav.replace.mock.calls.map((c) => String(c[0]));
      const viaHistory = historySpy.mock.calls.map((c) => String(c[2] ?? ''));
      const written = [...viaRouter, ...viaHistory];
      expect(written.length).toBeGreaterThan(0);
      expect(written.some((u) => !u.includes('seed='))).toBe(true);
      // The tab survives the rewrite.
      expect(written.filter((u) => !u.includes('seed=')).some((u) => u.includes('tab=invoiced'))).toBe(true);
    });
    historySpy.mockRestore();
  });

  it('applies the seed once: a later filter change is not overwritten by it', async () => {
    nav.seed = JSON.stringify(SEED); // the mocked URL keeps returning it, as a lagging router would
    render();
    await waitFor(() => expect(runs().length).toBeGreaterThan(0));
    const before = runs().length;
    fireEvent.click(await screen.findByLabelText('report-param-brand:b2'));
    await waitFor(() => expect(runs().length).toBeGreaterThan(before));
    const last = runs()[runs().length - 1];
    expect(last[1].brand).toEqual(['b1', 'b2']);
    expect(last[2].pivot.rows).toBe('sales_person');
  });

  it('a malformed seed is ignored and the report opens on its default view', async () => {
    nav.seed = '{not json';
    render();
    await waitFor(() => expect(runs().length).toBeGreaterThan(0));
    expect(runs()[0][2].pivot.rows).toBe('customer');
  });

  it.each([
    ['measure', { rows: 'sales_person', cols: 'all', measures: ['amount', 'bogus'] }],
    ['cols', { rows: 'sales_person', cols: 'bogus', measures: ['amount'] }],
  ])('a seed with an unknown %s keeps the default pivot and still applies its params', async (_n, pivot) => {
    nav.seed = JSON.stringify({ params: SEED.params, pivot });
    render();
    await waitFor(() => expect(runs().length).toBeGreaterThan(0));
    expect(runs()[0][2].pivot.rows).toBe('customer');
    expect(runs()[0][1].brand).toEqual(['b1']);
    expect(runs()[0][1].sales_person).toEqual(['LCL']);
  });
});
