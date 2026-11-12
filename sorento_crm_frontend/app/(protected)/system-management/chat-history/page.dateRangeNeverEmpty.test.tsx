/**
 * DATE-PICKER-UNIFY slice A: Chat history never sends an empty date range. Emptying the
 * Date range field puts both ends back to the load default (yesterday - today, Malaysia);
 * a half range still sends one bound only.
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
  // Only Date is faked so userEvent and react-query timers keep running.
  vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-12T04:00:00Z') });
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
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChatHistoryPage />
    </QueryClientProvider>,
  );
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
  return (await screen.findByLabelText('Date range')) as HTMLInputElement;
}

describe('Chat history - date range never empty', () => {
  it('emptying the field restores yesterday - today and sends both bounds', async () => {
    const user = userEvent.setup({ advanceTimers: () => {} });
    const field = await openFilters(user);
    expect(field.value).toBe('11/11/2026 - 12/11/2026');
    await user.clear(field);
    await user.keyboard('{Enter}');
    await waitFor(() => expect(field.value).toBe('11/11/2026 - 12/11/2026'));
    await waitFor(() => {
      expect(lastFilters().date_from).toBe('2026-11-10T16:00:00.000Z');
      expect(lastFilters().date_to).toBe('2026-11-12T15:59:59.999Z');
    });
  });

  it('control: a half range sends date_from only', async () => {
    const user = userEvent.setup({ advanceTimers: () => {} });
    const field = await openFilters(user);
    await user.clear(field);
    await user.type(field, '05/11/2026 -{Enter}');
    await waitFor(() => expect(lastFilters().date_from).toBe('2026-11-04T16:00:00.000Z'));
    expect(lastFilters().date_to).toBeUndefined();
  });
});
