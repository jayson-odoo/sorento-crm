/**
 * FILTER-MULTISELECT PR4b: the GRN list's Status filter takes several statuses (OR within the filter),
 * comma-joined to the data hook and in the page URL. An older link holding one status reads back as a
 * one-value filter.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
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

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/grn',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/upload-activity', () => ({ useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }) }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
const useGRNsMock = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useGRN', () => ({
  useGRNs: (...args: unknown[]) => useGRNsMock(...args),
  useBulkDeleteGRNs: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateGRN: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useDeleteGRN: () => ({ mutateAsync: vi.fn(), isPending: false }),
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

import GRNList from './GRNList';

const ROWS = [{ id: 'grn-1', picking_number: 'ZZT-GR-001', spo_number: 'ZZT-SPO-1', picking_date: '2026-06-22', picking_status: 'approved', items_count: 9 }];
const lastParams = () => useGRNsMock.mock.calls[useGRNsMock.mock.calls.length - 1][0] as Record<string, unknown>;
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
const selected = (el: HTMLSelectElement) => Array.from(el.selectedOptions, (o) => o.value).sort();
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GRNList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-GR-001');
  await user.click(filtersButton());
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  useGRNsMock.mockReturnValue({
    data: { data: ROWS, pagination: { total: ROWS.length, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('GRN list - multi Status filter', () => {
  it('Status is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('draft')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('draft'), ['draft', 'approved']);
    await waitFor(() => expect(setOf(lastParams().picking_status)).toEqual(['approved', 'draft']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('the All statuses sentinel is never sent', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await box('draft');
    expect(setOf(lastParams().picking_status)).toEqual([]);
  });

  it('Clear filters drops the status filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('draft'), ['draft', 'rejected']);
    await waitFor(() => expect(setOf(lastParams().picking_status)).toEqual(['draft', 'rejected']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(setOf(lastParams().picking_status)).toEqual([]));
  });

  it('a link with several statuses restores the control and the request', async () => {
    url.search = 'picking_status=draft%2Capproved';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(setOf(lastParams().picking_status)).toEqual(['approved', 'draft']));
    expect(selected(await box('draft'))).toEqual(['approved', 'draft']);
  });

  it('an older link with one status reads back as a one-value filter', async () => {
    url.search = 'picking_status=rejected';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(setOf(lastParams().picking_status)).toEqual(['rejected']));
    expect(selected(await box('draft'))).toEqual(['rejected']);
  });
});
