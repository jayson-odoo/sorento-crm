/**
 * FILTER-MULTISELECT PR4b: the Purchase requests list's Type, Status and Assigned to filters take several
 * values (OR within a filter, AND across), comma-joined to the data hook; Status and Assigned to also ride
 * the page URL (Type does not). "Unassigned" is a value like any other: Unassigned, A = unassigned OR A.
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
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/procurement-management/purchase-requests',
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
  ]),
}));
vi.mock('@/components/common/LookupBoundLabel', () => ({
  default: ({ value }: { value: string }) => <span>{value}</span>,
}));
const usePR = vi.hoisted(() => vi.fn());
vi.mock('../hooks/usePurchaseRequests', () => ({
  useBulkDeletePurchaseRequests: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchaseRequests: (params: unknown) => usePR(params),
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

import PurchaseRequestsList from './PurchaseRequestsList';

const ROW = {
  id: 'pr-1', request_number: 'ZZT-PR-001', request_type: 'purchase_request', approval_status: 'pending', status: 'draft',
  customer_name: 'ZZT Customer', purpose: 'ZZT purpose', requested_by: 'ZZT', submitted_at: '2026-01-01T00:00:00',
  created_at: '2026-01-01T00:00:00', revision_no: 0, assigned_to_name: null, handled_by_name: null,
};
const lastParams = () => usePR.mock.calls[usePR.mock.calls.length - 1][0] as Record<string, unknown>;
const types = () => setOf(lastParams().requestType);
const statuses = () => setOf(lastParams().approvalStatus);
const assignees = () => setOf(lastParams().assignedTo);
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
      <PurchaseRequestsList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-PR-001');
  await user.click(filtersButton());
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  url.search = '';
  usePR.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('Purchase requests - multi Type, Status and Assigned to filters', () => {
  it('Type, Status and Assigned to are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('sponsorship_form')).hasAttribute('multiple')).toBe(true);
    expect((await box('pending')).hasAttribute('multiple')).toBe(true);
    expect((await box('u-1')).hasAttribute('multiple')).toBe(true);
  });

  it('both types reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('sponsorship_form'), ['purchase_request', 'sponsorship_form']);
    await waitFor(() => expect(types()).toEqual(['purchase_request', 'sponsorship_form']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two statuses reach the hook as a set of two', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('pending'), ['draft', 'pending']);
    await waitFor(() => expect(statuses()).toEqual(['draft', 'pending']));
  });

  it('Unassigned combines with a person: Unassigned, A', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('u-1'), ['__unassigned__', 'u-1']);
    await waitFor(() => expect(assignees()).toEqual(['__unassigned__', 'u-1']));
  });

  it('filters AND across', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('pending'), ['pending', 'approved']);
    await user.selectOptions(await box('u-1'), ['u-1', 'u-2']);
    await waitFor(() => {
      expect(statuses()).toEqual(['approved', 'pending']);
      expect(assignees()).toEqual(['u-1', 'u-2']);
    });
  });

  it('the All sentinels are never sent', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await box('pending');
    expect(types()).toEqual([]);
    expect(statuses()).toEqual([]);
    expect(assignees()).toEqual([]);
  });

  it('Clear filters drops every multi filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('pending'), ['pending', 'approved']);
    await user.selectOptions(await box('sponsorship_form'), ['purchase_request', 'sponsorship_form']);
    await waitFor(() => expect(statuses()).toEqual(['approved', 'pending']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      expect(types()).toEqual([]);
      expect(statuses()).toEqual([]);
    });
  });

  it('a link with several statuses and assignees restores both controls and the request', async () => {
    url.search = 'approval_status=pending%2Capproved&assigned_to=__unassigned__%2Cu-1';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(statuses()).toEqual(['approved', 'pending']);
      expect(assignees()).toEqual(['__unassigned__', 'u-1']);
    });
    expect(selected(await box('pending'))).toEqual(['approved', 'pending']);
    expect(selected(await box('u-1'))).toEqual(['__unassigned__', 'u-1']);
  });

  it('an older link with one status and one assignee reads back as one-value filters', async () => {
    url.search = 'approval_status=rejected&assigned_to=u-2';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(statuses()).toEqual(['rejected']);
      expect(assignees()).toEqual(['u-2']);
    });
    expect(selected(await box('pending'))).toEqual(['rejected']);
  });
});
