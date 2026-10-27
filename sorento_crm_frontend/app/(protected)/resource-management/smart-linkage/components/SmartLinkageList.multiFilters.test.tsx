/**
 * FILTER-MULTISELECT PR2: Smart linkage's Status and Channel filters take several values (OR within a
 * filter, AND across), comma-joined to the data hook. The list stays scoped to attachments. The "All"
 * placeholders are never values.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import SmartLinkageList from './SmartLinkageList';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/resource-management/smart-linkage',
  useSearchParams: () => new URLSearchParams(''),
}));
const useIntegrationLogs = vi.fn();
vi.mock('@/app/(protected)/integration-management/integration-logs/hooks/useIntegrationLogs', () => ({
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
  useIntegrationLogs.mockReset();
  useIntegrationLogs.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false, isFetching: false, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SmartLinkageList />
    </QueryClientProvider>,
  );
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Smart linkage - multi Status and Channel filters', () => {
  it('are two multi controls, Status then Channel', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two statuses go to the hook comma-joined, still scoped to attachments', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const [status] = await screen.findAllByRole('listbox');
    await user.selectOptions(status, ['failed', 'pending']);
    await waitFor(() => expect(sortedValues(lastArgs().status)).toEqual(['failed', 'pending']));
    expect(lastArgs().business_table).toBe('attachments');
    expect(String(lastArgs().status)).not.toContain('all');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[0], ['failed', 'success']);
    await user.selectOptions(boxes[1], ['n8n']);
    await waitFor(() => expect(lastArgs()).toMatchObject({ status: 'failed,success', integration_channel: 'n8n' }));
  });
});
