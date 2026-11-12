/**
 * INTLOG-SPEED-2 (crew pass on 086a3235): a search or filter change while on page 2 must send the
 * list back to page 1, or the new, smaller result reads "51 - 69 of 69" (or an empty page). Opening
 * the list on page 2 from its own URL (Back from a record) must still land on page 2. Harness
 * mirrors IntegrationLogsList.multiFilters.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import IntegrationLogsList from './IntegrationLogsList';

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/integration-management/integration-logs',
  useSearchParams: () => new URLSearchParams(url.search),
}));
const useIntegrationLogs = vi.fn();
vi.mock('../hooks/useIntegrationLogs', () => ({
  useIntegrationLogs: (...a: unknown[]) => useIntegrationLogs(...a),
  useRetryIntegrationLog: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
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

const ROW = {
  id: 'log-1', integration_channel: 'n8n', business_table: 'attachments', business_id: 'b-1',
  direction: 'outbound', endpoint: '/x', http_method: 'POST', status: 'failed', retry_count: 0,
  max_retry_allowed: 3, created_at: '2026-06-01T09:00:00', updated_at: '2026-06-01T09:00:00',
};
const lastArgs = () => {
  const calls = useIntegrationLogs.mock.calls;
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
  url.search = '';
  useIntegrationLogs.mockReset();
  useIntegrationLogs.mockReturnValue({
    data: { data: [ROW], pagination: { total: 3731, page: 2, limit: 50 } },
    isLoading: false, isFetching: false, isRefetching: false, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IntegrationLogsList />
    </QueryClientProvider>,
  );
}
async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderIt();
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Integration logs - a search or filter change goes back to page 1', () => {
  it('opening the list from its URL on page 2 stays on page 2', async () => {
    url.search = 'page=2';
    renderIt();
    await waitFor(() => expect(lastArgs().pageIndex).toBe(1));
  });

  it('typing a search term on page 2 asks the server for page 1', async () => {
    url.search = 'page=2';
    const user = userEvent.setup();
    renderIt();
    await waitFor(() => expect(lastArgs().pageIndex).toBe(1));
    await user.type(screen.getByPlaceholderText('Search logs...'), 'timeout');
    await waitFor(() => expect(lastArgs().searchQuery).toBe('timeout'));
    expect(lastArgs().pageIndex).toBe(0);
  });

  it('picking a filter on page 2 asks the server for page 1', async () => {
    url.search = 'page=2';
    const user = userEvent.setup();
    renderIt();
    await waitFor(() => expect(lastArgs().pageIndex).toBe(1));
    await user.click(await screen.findByRole('button', { name: /^filters/i }));
    const [status] = await screen.findAllByRole('listbox');
    await user.selectOptions(status, ['failed']);
    await waitFor(() => expect(lastArgs().status).toBe('failed'));
    expect(lastArgs().pageIndex).toBe(0);
  });
});
