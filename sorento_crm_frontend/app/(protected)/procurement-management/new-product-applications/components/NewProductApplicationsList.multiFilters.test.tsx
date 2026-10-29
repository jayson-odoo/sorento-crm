/**
 * FILTER-MULTISELECT PR4b: the New product applications list's Status and Applicant filters take
 * several values (OR within a filter, AND across), comma-joined to the data hook and in the page URL.
 * An older link holding one value reads back as a one-value filter.
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
  usePathname: () => '/procurement-management/new-product-applications',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn().mockResolvedValue([
    { id: 'u-1', name: 'ZZT Alice' },
    { id: 'u-2', name: 'ZZT Bob' },
    { id: 'u-3', name: 'ZZT Cara' },
  ]),
}));
const useQ = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useNewProductApplications', () => ({
  useNewProductApplicationListingKey: () => 'procurement.new_product_applications.view',
  useNewProductApplicationsQuery: (params: unknown) => useQ(params),
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

import NewProductApplicationsList from './NewProductApplicationsList';

const ROW = {
  id: 'npa-1', application_no: 'ZZT-NPA-001', status: 'draft', status_label: 'Draft', source: 'staff', applicant_id: 'u-1',
  applicant_name: 'ZZT Alice', stock_inquiry_id: null, stock_inquiry_number: null, customer_name: 'ZZT Customer',
  project_name: null, first_line: 'ZZT item', lines_total: 1, lines_done: 0, opened_codes: [], needed_by: null,
  submitted_at: null, created_at: '2026-01-01T00:00:00',
};
const lastParams = () => useQ.mock.calls[useQ.mock.calls.length - 1][0] as Record<string, unknown>;
const applicants = () => setOf(lastParams().applicantId ?? lastParams().applicant_id);
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
      <NewProductApplicationsList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-NPA-001');
  await user.click(filtersButton());
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  useQ.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 25 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('New product applications - multi Status and Applicant filters', () => {
  it('Status and Applicant are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('submitted')).hasAttribute('multiple')).toBe(true);
    expect((await box('u-1')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('submitted'), ['draft', 'submitted']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['draft', 'submitted']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two applicants reach the hook as a set of two, ANDed with the status', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('submitted'), ['approved']);
    await user.selectOptions(await box('u-1'), ['u-1', 'u-3']);
    await waitFor(() => {
      expect(setOf(lastParams().status)).toEqual(['approved']);
      expect(applicants()).toEqual(['u-1', 'u-3']);
    });
  });

  it('the All statuses / All applicants sentinels are never sent', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await box('submitted');
    expect(setOf(lastParams().status)).toEqual([]);
    expect(applicants()).toEqual([]);
  });

  it('Clear filters drops both multi filters', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('submitted'), ['draft', 'submitted']);
    await user.selectOptions(await box('u-1'), ['u-1', 'u-2']);
    await waitFor(() => expect(applicants()).toEqual(['u-1', 'u-2']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      expect(setOf(lastParams().status)).toEqual([]);
      expect(applicants()).toEqual([]);
    });
  });

  it('a link with several values restores both controls and the request', async () => {
    url.search = 'status=draft%2Csubmitted&applicant_id=u-1%2Cu-2';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(setOf(lastParams().status)).toEqual(['draft', 'submitted']);
      expect(applicants()).toEqual(['u-1', 'u-2']);
    });
    expect(selected(await box('submitted'))).toEqual(['draft', 'submitted']);
    expect(selected(await box('u-1'))).toEqual(['u-1', 'u-2']);
  });

  it('an older link with one status and one applicant reads back as one-value filters', async () => {
    url.search = 'status=approved&applicant_id=u-3';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(setOf(lastParams().status)).toEqual(['approved']);
      expect(applicants()).toEqual(['u-3']);
    });
    expect(selected(await box('submitted'))).toEqual(['approved']);
  });
});
