/**
 * FILTER-MULTISELECT PR4b: the Cost price uploads list's Supplier filter takes several suppliers (OR),
 * comma-joined (or listed) to the data hook. Status is already multi: a guard that it stays so and that
 * the two AND. Not URL-persisted. The screen renders each filter twice (table and 375px card layouts).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
  usePathname: () => '/procurement-management/cost-price-uploads',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('../../suppliers/services/supplierService', () => ({
  searchSuppliersForSelect: vi.fn(async () => [
    { value: 'sup-1', label: 'ZZT Supplier One' },
    { value: 'sup-2', label: 'ZZT Supplier Two' },
    { value: 'sup-3', label: 'ZZT Supplier Three' },
  ]),
}));
vi.mock('./UploadPriceListDialog', () => ({ UploadPriceListDialog: () => null }));
const useSets = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useCostPriceChangeSets', () => ({ useCostPriceChangeSets: (params: unknown) => useSets(params) }));
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

import CostPriceUploadsList from './CostPriceUploadsList';

const ROW = {
  id: 'cp-1', code: 'ZZT-CP-001', status: 'draft', supplier: { id: 'sup-1', supplier_code: 'S1', supplier_name: 'ZZT Supplier One' },
  channel: 'staff_upload', file_name: 'zzt.xlsx', currency: 'MYR', start_date: null, end_date: null, lines_changed: 1,
  uploaded_by_name: 'ZZT', created_at: '2026-01-01T00:00:00', applied_at: null, verified: null, verified_by_name: null,
};
const lastParams = () => useSets.mock.calls[useSets.mock.calls.length - 1][0] as Record<string, unknown>;
const suppliers = () => setOf(lastParams().supplier_id ?? lastParams().supplier_ids);
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
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

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CostPriceUploadsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  useSets.mockReturnValue({
    data: { data: [ROW], total: 1, page: 1, limit: 50, pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, isPlaceholderData: false, isError: false, error: null,
  });
});
afterEach(() => cleanup());

describe('Cost price uploads - multi Supplier filter', () => {
  it('Supplier is a multi control', async () => {
    renderList();
    expect((await box('sup-1')).hasAttribute('multiple')).toBe(true);
  });

  it('two suppliers reach the hook as a set of two', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('sup-1'), ['sup-1', 'sup-2']);
    await waitFor(() => expect(suppliers()).toEqual(['sup-1', 'sup-2']));
  });

  it('suppliers AND with the (already multi) status filter', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('sup-1'), ['sup-2', 'sup-3']);
    await user.selectOptions(await box('applied'), ['draft', 'applied']);
    await waitFor(() => {
      expect(suppliers()).toEqual(['sup-2', 'sup-3']);
      expect(setOf(lastParams().status)).toEqual(['applied', 'draft']);
    });
  });

  it('unticking every supplier drops the filter', async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(await box('sup-1'), ['sup-1', 'sup-2']);
    await waitFor(() => expect(suppliers()).toEqual(['sup-1', 'sup-2']));
    await user.deselectOptions(await box('sup-1'), ['sup-1', 'sup-2']);
    await waitFor(() => expect(suppliers()).toEqual([]));
  });
});
