/**
 * FILTER-MULTISELECT PR6 (owner Q1 (a)): the Divergences list's State filter takes several values (OR) and
 * its "Any" no longer exists as a sentinel: nothing chosen asks for every state, because the backend
 * defaulted a missing state to "open" and "Any" therefore never showed the reconciled ones.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/divergences',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
const listDivergences = vi.hoisted(() => vi.fn());
vi.mock('../../_shared/services/soDivergenceService', () => ({
  listDivergences: (...args: unknown[]) => listDivergences(...args),
  getDivergence: vi.fn(), ingestSalesOrderFile: vi.fn(), resolveDivergenceRow: vi.fn(), downloadCorrectiveImportFile: vi.fn(),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { DivergenceListClient } from './DivergenceListClient';

const ROW = {
  id: 'd1', project_sales_order_id: 'so-1', project_id: 'p1', project_title: 'ZZT Tuju Residences', sales_order_ref: 'SO397450',
  provisional_ref: 'PSO-000123', autocount_doc_no: 'SO397450', status: 'open', compared_count: 52, agreeing_count: 48,
  differing_count: 4, unresolved_count: 4, corrective_publish_required: false, detected_at: '2026-08-01T02:00:00',
  resolved_at: null, age_days: 2,
};
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => listDivergences.mock.calls[listDivergences.mock.calls.length - 1][0] as Record<string, unknown>;
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
}

async function render_() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DivergenceListClient />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT Tuju Residences');
  openFilters();
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  listDivergences.mockResolvedValue({ data: [ROW], total: 1, page: 1, limit: 25 });
});
afterEach(() => cleanup());

describe('Divergences - multi State filter', () => {
  it('opens on what is still to reconcile', async () => {
    await render_();
    expect(setOf(lastParams().status)).toEqual(['open']);
  });

  it('State is a multi control', async () => {
    await render_();
    expect((await box('resolved')).hasAttribute('multiple')).toBe(true);
  });

  it('both states reach the service as a set of two', async () => {
    const user = userEvent.setup();
    await render_();
    await user.selectOptions(await box('resolved'), ['open', 'resolved']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['open', 'resolved']));
  });

  it('unticking every state asks for every state: no status at all, never an "all" value', async () => {
    const user = userEvent.setup();
    await render_();
    await user.deselectOptions(await box('resolved'), ['open']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual([]));
    for (const [params] of listDivergences.mock.calls) {
      expect(setOf((params as Record<string, unknown>).status)).not.toContain('all');
    }
  });
});
