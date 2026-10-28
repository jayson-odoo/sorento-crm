/**
 * FILTER-MULTISELECT PR2: the Conversation SLA list's Assignee filter takes several people (OR within
 * the filter), sent comma-joined as `assigned_to`. Harness mirrors
 * ConversationSLATrackingList.assignee.test.tsx, with a real query client for the user lookup.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ConversationSLATrackingList from './ConversationSLATrackingList';

const useConversationSLATracking = vi.fn();

vi.mock('../hooks/useConversationSLATracking', () => ({
  useConversationSLATracking: (...a: unknown[]) => useConversationSLATracking(...a),
  useSyncAssigneeFromRespond: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteConversationSLATracking: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ann', respond_user_id: 'resp-ann', name: 'Ann Lee', email: 'ann@e.com' },
    { id: 'u-ben', respond_user_id: 'resp-ben', name: 'Ben Lim', email: 'ben@e.com' },
    { id: 'u-cat', respond_user_id: null, name: 'Cat Tan', email: 'cat@e.com' },
  ]),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => '/sla-management/conversation-sla-tracking',
}));
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
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

const row = {
  id: 'tr-1', policy_id: 'pol-1', current_tier: 1, initiated_at: '2026-08-12T02:00:00',
  current_tier_started_at: '2026-08-12T02:00:00', due_at: '2026-08-12T03:00:00', is_responded: false,
  is_resolved: false, contact_phone: '+60 12-000 0553', contact_name: 'Aisyah Rahman',
  policy_name: 'Conversation SLA - Standard', assigned_user_name: 'Ben Lim',
};

const lastArgs = () => {
  const calls = useConversationSLATracking.mock.calls;
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
});
beforeEach(() => {
  useConversationSLATracking.mockReset();
  useConversationSLATracking.mockReturnValue({
    data: { data: [row], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false,
    isFetching: false,
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConversationSLATrackingList />
    </QueryClientProvider>,
  );
  await screen.findByText('Aisyah Rahman');
  await user.click(filtersButton());
}

describe('Conversation SLA list - multi Assignee filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two assignees go to the hook comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    // option values are the Respond id when there is one, else the user id (as today)
    await waitFor(() => expect((box as HTMLSelectElement).options.length).toBe(3));
    await user.selectOptions(box, ['resp-ann', 'u-cat']);
    await waitFor(() => expect(lastArgs().assigned_to).toBe('resp-ann,u-cat'));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('never sends the all-assignees placeholder as a value', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    await waitFor(() => expect((box as HTMLSelectElement).options.length).toBeGreaterThan(0));
    await user.selectOptions(box, ['resp-ben']);
    await waitFor(() => expect(lastArgs().assigned_to).toBe('resp-ben'));
    expect(String(lastArgs().assigned_to)).not.toContain('__all__');
  });

  it('Clear Filters drops the whole filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    await waitFor(() => expect((box as HTMLSelectElement).options.length).toBe(3));
    await user.selectOptions(box, ['resp-ann', 'resp-ben']);
    await waitFor(() => expect(lastArgs().assigned_to).toBe('resp-ann,resp-ben'));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(lastArgs().assigned_to).toBeUndefined());
  });
});
