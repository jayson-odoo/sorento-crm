/**
 * TRACE-SIDEBAR (owner, 11 Nov 2026): a `?turn=<id>` link still opens that turn's trace drawer
 * on Chat History. Closing it drops `turn` from the address (other params kept), so the same
 * link followed again opens the drawer again instead of doing nothing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const replace = vi.fn();
vi.mock('./services/chatHistoryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./services/chatHistoryService')>();
  return {
    ...actual,
    getChatMessages: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0, page: 1 }, empty: true }),
  };
});
vi.mock('./hooks/useChatHistory', () => ({
  useExportChatHistory: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('./hooks/useChatbotTurns', () => ({
  useFailedChatbotContacts: () => ({ data: undefined, isLoading: false, isSuccess: false }),
}));
vi.mock('./components/ChatThreadDrawer', () => ({ ChatThreadDrawer: () => null }));
vi.mock('./components/TurnDetailDrawer', () => ({
  TurnDetailDrawer: ({ turnId, onOpenChange }: { turnId: string | null; onOpenChange: (o: boolean) => void }) =>
    turnId ? (
      <div data-testid="turn-drawer-stub" data-turn={turnId}>
        <button type="button" onClick={() => onOpenChange(false)}>
          close drawer
        </button>
      </div>
    ) : null,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  usePathname: () => '/system-management/chat-history',
  useSearchParams: () => new URLSearchParams('turn=turn-42&q=abc'),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import ChatHistoryPage from './page';

beforeEach(() => {
  replace.mockReset();
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
});
afterEach(() => cleanup());

describe('Chat History ?turn= deep link (TRACE-SIDEBAR)', () => {
  it('opens the linked turn in the drawer, and closing drops turn from the address', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ChatHistoryPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId('turn-drawer-stub').getAttribute('data-turn')).toBe('turn-42');

    fireEvent.click(screen.getByText('close drawer'));
    expect(screen.queryByTestId('turn-drawer-stub')).toBeNull();
    expect(replace).toHaveBeenCalledWith('/system-management/chat-history?q=abc', { scroll: false });
  });
});
