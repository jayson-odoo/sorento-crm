/**
 * FILTER-MULTISELECT PR3: the Branches list's Book filter takes several books (OR within the filter),
 * comma-joined to the branches service. Harness mirrors BranchesList.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/order-management/branches',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
const getBranches = vi.fn();
vi.mock('../services/branchService', () => ({
  getBranches: (...a: unknown[]) => getBranches(...a),
  getBranchBooks: vi.fn(async () => ['SRT', 'MOC', 'TPE']),
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

import BranchesList from './BranchesList';

const lastArgs = () => {
  const calls = getBranches.mock.calls;
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
  getBranches.mockReset();
  getBranches.mockResolvedValue({
    data: [{ id: 'b1', source_book: 'SRT', acc_no: 'A', branch_code: 'KL01', branch_name: 'ZZT Branch', last_synced_at: null, customer_id: null, customer_name: null }],
    pagination: { page: 1, limit: 50, total: 1 },
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <BranchesList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT Branch');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}

describe('Branches - multi Book filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two books go to the service comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    await waitFor(() => expect((box as HTMLSelectElement).options.length).toBe(3));
    await user.selectOptions(box, ['SRT', 'MOC']);
    await waitFor(() => expect(lastArgs().book).toBe('SRT,MOC'));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(screen.getByRole('button', { name: /^filters/i })).getByText('1')).toBeInTheDocument());
  });
});
