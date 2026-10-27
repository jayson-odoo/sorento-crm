/**
 * FILTER-MULTISELECT PR2: the Integration logs list's Status, Channel and Table filters take several
 * values (OR within a filter, AND across), comma-joined to the data hook. The filters are seeded from
 * the URL, so a comma-joined link and an older single-value link both read back, The "All" placeholders are never values. Harness mirrors
 * IntegrationLogsList.test.tsx.
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
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 50 } },
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

describe('Integration logs - multi Status, Channel and Table filters', () => {
  it('are three multi controls, Status then Channel then Table', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(3);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two statuses go to the hook comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const [status] = await screen.findAllByRole('listbox');
    await user.selectOptions(status, ['failed', 'pending']);
    await waitFor(() => expect(lastArgs().status).toBe('failed,pending'));
    expect(String(lastArgs().status)).not.toContain('all');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two channels and two tables go to the hook comma-joined', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[1], ['n8n', 'sla_management']);
    await user.selectOptions(boxes[2], ['attachments', 'conversation_sla_tracking']);
    await waitFor(() =>
      expect(lastArgs()).toMatchObject({
        integration_channel: 'n8n,sla_management',
        business_table: 'attachments,conversation_sla_tracking',
      }),
    );
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[0], ['failed', 'pending']);
    await user.selectOptions(boxes[1], ['n8n']);
    await waitFor(() => expect(lastArgs()).toMatchObject({ status: 'failed,pending', integration_channel: 'n8n' }));
  });

  it('a comma-joined link reads back into the filters (guard)', async () => {
    url.search = 'status=failed%2Cpending&integration_channel=n8n%2Csla_management&business_table=attachments%2Cconversation_sla_tracking';
    renderIt();
    await waitFor(() =>
      expect(lastArgs()).toMatchObject({
        status: 'failed,pending',
        integration_channel: 'n8n,sla_management',
        business_table: 'attachments,conversation_sla_tracking',
      }),
    );
  });

  it('an older link with one value of each reads back as one-value filters (guard)', async () => {
    url.search = 'status=failed&integration_channel=n8n&business_table=attachments';
    renderIt();
    await waitFor(() =>
      expect(lastArgs()).toMatchObject({ status: 'failed', integration_channel: 'n8n', business_table: 'attachments' }),
    );
  });
});
