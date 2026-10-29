/**
 * FILTER-MULTISELECT PR2: the Email outbox Status filter takes several values (OR within the filter),
 * comma-joined to the data hook. The "All statuses" placeholder is never a value.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import EmailOutboxList from './EmailOutboxList';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/system-management/email-outbox',
  useSearchParams: () => new URLSearchParams(''),
}));
const useEmailOutbox = vi.fn();
vi.mock('../hooks/useEmailOutbox', () => ({
  useEmailOutbox: (...a: unknown[]) => useEmailOutbox(...a),
  useEmailOutboxRow: () => ({ data: undefined, isLoading: false }),
  useRetryEmailOutboxRow: () => ({ mutate: vi.fn(), isPending: false }),
  useCancelEmailOutboxRow: () => ({ mutate: vi.fn(), isPending: false }),
  useBulkRetryEmailOutbox: () => ({ mutate: vi.fn(), isPending: false }),
  useBulkCancelEmailOutbox: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

const lastArgs = () => {
  const calls = useEmailOutbox.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};

/** The picked values in any order: the multi control joins them in option order. */
const sortedValues = (v: unknown) => String(v ?? '').split(',').sort();
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

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
  useEmailOutbox.mockReset();
  useEmailOutbox.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <EmailOutboxList />
    </QueryClientProvider>,
  );
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Email outbox - multi Status filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses go to the hook comma-joined, never with the All placeholder, and the badge counts one', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), ['failed', 'pending']);
    await waitFor(() => expect(sortedValues(lastArgs().status)).toEqual(['failed', 'pending']));
    expect(String(lastArgs().status)).not.toContain('__all__');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('Clear filters drops the whole filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), ['failed', 'pending']);
    await waitFor(() => expect(sortedValues(lastArgs().status)).toEqual(['failed', 'pending']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(lastArgs().status).toBeUndefined());
  });
});
