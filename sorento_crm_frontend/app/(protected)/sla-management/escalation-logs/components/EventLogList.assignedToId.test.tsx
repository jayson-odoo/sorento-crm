/**
 * FILTER-MULTISELECT PR2 review: the Escalation logs "Assigned to" filter sends the picked users'
 * `users.id` values as `assigned_to_id` (the param the event log table already uses), never `assigned_to`,
 * which holds a display label on the stored rows and so never matched a resolved one.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import EventLogList from './EventLogList';

const useEventLogs = vi.fn();

vi.mock('../hooks/useEventLogs', () => ({ useEventLogs: (...a: unknown[]) => useEventLogs(...a) }));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ann', respond_user_id: 'resp-ann', name: 'Ann Lee', email: 'ann@e.com' },
    { id: 'u-ben', respond_user_id: 'resp-ben', name: 'Ben Lim', email: 'ben@e.com' },
  ]),
}));
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

const lastParams = () => {
  const calls = useEventLogs.mock.calls;
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
});
beforeEach(() => {
  useEventLogs.mockReset();
  useEventLogs.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false,
    isPlaceholderData: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <EventLogList />
    </QueryClientProvider>,
  );
  await user.click(await screen.findByRole('button', { name: /filters/i }));
}

describe('Escalation logs - Assigned to sends user ids', () => {
  it('two assignees go as assigned_to_id (the ids, not the Respond ids) and never as assigned_to', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[1] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[1], ['u-ann', 'u-ben']);
    await waitFor(() => {
      const sent = String(lastParams().assigned_to_id ?? '').split(',').sort();
      expect(sent).toEqual(['u-ann', 'u-ben']);
    });
    expect(lastParams().assigned_to).toBeUndefined();
  });
});
