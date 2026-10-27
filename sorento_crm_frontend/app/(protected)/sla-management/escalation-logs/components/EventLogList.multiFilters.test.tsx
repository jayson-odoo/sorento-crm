/**
 * FILTER-MULTISELECT PR2: the Escalation logs list's Event type and Assigned to filters take several
 * values (OR within a filter, AND across), comma-joined as `event_type` and `assigned_to`.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
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
const filtersButton = () => screen.getByRole('button', { name: /filters/i });

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

describe('Escalation logs - multi Event type and Assigned to filters', () => {
  it('are two multi controls, Event type then Assigned to', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two event types go to the hook comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const [eventType] = await screen.findAllByRole('listbox');
    await user.selectOptions(eventType, ['escalation', 'reassignment']);
    await waitFor(() => expect(lastParams().event_type).toBe('escalation,reassignment'));
    expect(String(lastParams().event_type)).not.toContain('__all__');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two assignees go to the hook comma-joined', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[1] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[1], ['resp-ann', 'resp-ben']);
    await waitFor(() => expect(lastParams().assigned_to).toBe('resp-ann,resp-ben'));
  });

  it('the filters AND across each other and Clear advanced filters drops both', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[1] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[0], ['escalation', 'response']);
    await user.selectOptions(boxes[1], ['resp-ben']);
    await waitFor(() =>
      expect(lastParams()).toMatchObject({ event_type: 'escalation,response', assigned_to: 'resp-ben' }),
    );
    await user.click(screen.getByRole('button', { name: /clear advanced filters/i }));
    await waitFor(() => expect(lastParams().event_type).toBeUndefined());
    expect(lastParams().assigned_to).toBeUndefined();
  });
});
