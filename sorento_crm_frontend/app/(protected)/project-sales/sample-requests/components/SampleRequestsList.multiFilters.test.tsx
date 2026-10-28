/**
 * FILTER-MULTISELECT PR6: the Sample requests list's Status and Salesperson filters take several values (OR);
 * one comma-joined set reaches the query hook, clearing Salesperson sends nothing (no "__all__" sentinel), and
 * an old single-value link still reads as a one-value filter.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
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

let searchParamsValue = '';
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/sample-requests',
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'zzt-u1', name: 'ZZT Sales One' },
    { id: 'zzt-u2', name: 'ZZT Sales Two' },
  ]),
}));
const useSampleRequestsQuery = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return { ...actual, useSampleRequestsQuery: (...args: unknown[]) => useSampleRequestsQuery(...args) };
});
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


import SampleRequestsList from './SampleRequestsList';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => useSampleRequestsQuery.mock.calls.at(-1)?.[0] as Record<string, unknown>;
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
function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  searchParamsValue = '';
  useSampleRequestsQuery.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 25 } }, isLoading: false, isPlaceholderData: false,
    refetch: vi.fn(), isFetching: false, error: null,
  });
});
afterEach(() => cleanup());

describe('Sample requests - multi Status and Salesperson', () => {
  it('Status is a multi control', async () => {
    renderList();
    openFilters();
    expect((await box('draft')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses reach the hook as one set', async () => {
    const user = userEvent.setup();
    renderList();
    openFilters();
    await user.selectOptions(await box('draft'), ['draft', 'submitted']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['draft', 'submitted']));
  });

  it('Salesperson is a multi control', async () => {
    renderList();
    openFilters();
    expect((await box('zzt-u1')).hasAttribute('multiple')).toBe(true);
  });

  it('two salespeople reach the hook as one set, and clearing sends none', async () => {
    const user = userEvent.setup();
    renderList();
    openFilters();
    await user.selectOptions(await box('zzt-u1'), ['zzt-u1', 'zzt-u2']);
    await waitFor(() => expect(setOf(lastParams().salespersonId)).toEqual(['zzt-u1', 'zzt-u2']));
    openFilters();
    await user.deselectOptions(await box('zzt-u1'), ['zzt-u1', 'zzt-u2']);
    await waitFor(() => expect(setOf(lastParams().salespersonId)).toEqual([]));
    for (const [params] of useSampleRequestsQuery.mock.calls) {
      expect(setOf((params as Record<string, unknown>).salespersonId)).not.toContain('__all__');
    }
  });

  it('an old link with one value reads as a one-value filter, a joined one as a set', async () => {
    searchParamsValue = 'status=draft&salesperson_id=zzt-u1,zzt-u2';
    renderList();
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['draft']));
    expect(setOf(lastParams().salespersonId)).toEqual(['zzt-u1', 'zzt-u2']);
  });
});
