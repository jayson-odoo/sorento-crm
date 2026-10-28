/**
 * FILTER-MULTISELECT PR2: the Conversation SLA detail Event Log's Event Type and Assigned To filters
 * take several values (OR within a filter, AND across), comma-joined as `event_type` and
 * `assigned_to_id`. The "All" placeholder is never a value.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import EventLogTable from './EventLogTable';

const useConversationSLAEventLogs = vi.fn();

vi.mock('../hooks/useConversationSLATracking', () => ({
  useConversationSLAEventLogs: (...a: unknown[]) => useConversationSLAEventLogs(...a),
  useDeleteConversationSLAEventLog: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ann', name: 'Ann Lee', email: 'ann@e.com' },
    { id: 'u-ben', name: 'Ben Lim', email: 'ben@e.com' },
  ]),
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({ ok: true, json: async () => ({ role: 'user' }) })),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
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
  const calls = useConversationSLAEventLogs.mock.calls;
  return calls[calls.length - 1][1] as Record<string, unknown>;
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
  useConversationSLAEventLogs.mockReset();
  useConversationSLAEventLogs.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false,
    isPlaceholderData: false,
    error: null,
    refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <EventLogTable trackingId="11111111-1111-4111-8111-111111111111" />
    </QueryClientProvider>,
  );
  await user.click(await screen.findByRole('button', { name: /filters/i }));
}

describe('Conversation SLA Event Log - multi Event Type and Assigned To filters', () => {
  it('are two multi controls, Event Type then Assigned To', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two event types go to the hook comma-joined, never with the All placeholder', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const [eventType] = await screen.findAllByRole('listbox');
    await user.selectOptions(eventType, ['escalation', 'response']);
    await waitFor(() => expect(lastParams().event_type).toBe('escalation,response'));
    expect(String(lastParams().event_type)).not.toContain('__all__');
  });

  it('two assignees go to the hook comma-joined', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[1] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[1], ['u-ann', 'u-ben']);
    await waitFor(() => expect(lastParams().assigned_to_id).toBe('u-ann,u-ben'));
  });

  it('the filters AND across each other and Clear Filters drops both', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[1] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[0], ['escalation', 'resolution']);
    await user.selectOptions(boxes[1], ['u-ann']);
    await waitFor(() =>
      expect(lastParams()).toMatchObject({ event_type: 'escalation,resolution', assigned_to_id: 'u-ann' }),
    );
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(lastParams().event_type).toBeUndefined());
    expect(lastParams().assigned_to_id).toBeUndefined();
  });
});
