/**
 * FILTER-MULTISELECT PR2: the Chat history Direction filter takes both values (owner Q3 (a): a
 * two-value filter is multi too), comma-joined to the list service. Both picked means both
 * directions; nothing picked sends no direction.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getChatMessages = vi.fn();
vi.mock('./services/chatHistoryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./services/chatHistoryService')>();
  return { ...actual, getChatMessages: (...a: unknown[]) => getChatMessages(...a) };
});
vi.mock('./hooks/useChatHistory', () => ({
  useExportChatHistory: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('./hooks/useChatbotTurns', () => ({
  useFailedChatbotContacts: () => ({ data: undefined, isLoading: false, isSuccess: false }),
}));
vi.mock('./components/ChatThreadDrawer', () => ({ ChatThreadDrawer: () => null }));
vi.mock('./components/TurnDetailDrawer', () => ({ TurnDetailDrawer: () => null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/system-management/chat-history',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
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

import ChatHistoryPage from './page';

const lastFilters = () => {
  const calls = getChatMessages.mock.calls;
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
  getChatMessages.mockReset();
  getChatMessages.mockResolvedValue({ data: [], pagination: { total: 0, page: 1 }, empty: true });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChatHistoryPage />
    </QueryClientProvider>,
  );
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Chat history - multi Direction filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('both directions go to the service comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), ['incoming', 'outgoing']);
    await waitFor(() => expect(lastFilters().direction).toBe('incoming,outgoing'));
    await user.keyboard('{Escape}');
    await waitFor(() =>
      expect(within(screen.getByRole('button', { name: /^filters/i })).getByText('1')).toBeInTheDocument(),
    );
  });

  it('one direction still goes alone', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), ['outgoing']);
    await waitFor(() => expect(lastFilters().direction).toBe('outgoing'));
  });
});
