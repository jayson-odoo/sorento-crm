/**
 * FILTER-MULTISELECT PR3: the Customers list's Group filter takes several groups (OR within the
 * filter), comma-joined to the data hook as `customer_group_id`. Status stays a single Active /
 * Inactive / All control. Harness mirrors CustomersList.group.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/order-management/customers',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/upload-activity', () => ({ useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }) }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('../services/customerImportService', () => ({ importCustomers: vi.fn(), validateCustomerImport: vi.fn() }));
vi.mock('../../customer-groups/services/customerGroupService', () => ({
  searchCustomerGroupsSelect: vi.fn().mockResolvedValue([
    { id: 'grp-1', name: 'ZZT Group One', ledger_count: 6 },
    { id: 'grp-2', name: 'ZZT Group Two', ledger_count: 2 },
  ]),
  getCustomerGroups: vi.fn(),
  getCustomerGroup: vi.fn(),
  getCustomerGroupCustomers: vi.fn(),
}));
const ROWS = [{
  id: 'c-1', customer_code: 'ZZT-C1', customer_name: 'ZZT Customer', email: null, phone_number: null, is_active: true,
  created_at: new Date('2026-01-01T00:00:00Z'), customer_group_id: 'grp-1', customer_group_name: 'ZZT Group One',
}];
const useCustomersSpy = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useCustomers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useCustomers')>()),
  useCustomers: (params: unknown) => {
    useCustomersSpy(params);
    return {
      data: { data: ROWS, pagination: { page: 1, limit: 50, total: ROWS.length } },
      isLoading: false, isPlaceholderData: false, isFetching: false, refetch: vi.fn(),
    };
  },
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

import CustomersList from './CustomersList';

const lastParams = () => {
  const calls = useCustomersSpy.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  useCustomersSpy.mockReset();
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <CustomersList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT Customer');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}

describe('Customers - multi Group filter', () => {
  it('Group is a multi control and Status is not', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(1);
    expect(boxes[0].hasAttribute('multiple')).toBe(true);
    await waitFor(() => expect((boxes[0] as HTMLSelectElement).options.length).toBe(2));
  });

  it('two groups go to the hook comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    await waitFor(() => expect((box as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(box, ['grp-1', 'grp-2']);
    await waitFor(() => expect(lastParams().customer_group_id).toBe('grp-1,grp-2'));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(screen.getByRole('button', { name: /^filters/i })).getByText('1')).toBeInTheDocument());
  });

  it('Clear filters drops the group filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    await waitFor(() => expect((box as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(box, ['grp-1', 'grp-2']);
    await waitFor(() => expect(lastParams().customer_group_id).toBe('grp-1,grp-2'));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(lastParams().customer_group_id).toBeUndefined());
  });
});
