/**
 * N8N-RETIRE-A (crew pass on 2f8feb3e): one state, one word. The Chat History list's
 * last-failed badge must read exactly what the turn itself reads (turnHeadline):
 * a send the CRM could not confirm is "Not confirmed", never "failed at not confirmed".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const replace = vi.fn();
const { row } = vi.hoisted(() => ({
  row: (id: number, contact: string, display: string) => ({
    id, channel: 'whatsapp', contact_id: contact, contact_display: display, phone_number: '',
    type: 'incoming', message: 'hello', sent_at: '2026-11-12T01:00:00Z', respond_ts: null,
    delivery_status: null, turn_id: null, message_id: null, latency_seconds: null,
    webhook_lag_seconds: null,
  }),
}));
vi.mock('./services/chatHistoryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./services/chatHistoryService')>();
  return {
    ...actual,
    getChatMessages: vi.fn().mockResolvedValue({
      data: [row(1, 'c-unconfirmed', 'Contact Alpha'), row(2, 'c-sent', 'Contact Beta')],
      pagination: { total: 2, page: 1 },
      empty: false,
    }),
  };
});
vi.mock('./hooks/useChatHistory', () => ({
  useExportChatHistory: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('./hooks/useChatbotTurns', () => ({
  useFailedChatbotContacts: () => ({
    byContactId: new Map([
      ['c-unconfirmed', { contact_respond_id: 'c-unconfirmed', last_failed_stage: 'send_unconfirmed', last_failed_at: null, count: 1 }],
      ['c-sent', { contact_respond_id: 'c-sent', last_failed_stage: 'sent', last_failed_at: null, count: 2 }],
    ]),
    contactIds: [],
    isLoading: false,
    isSuccess: true,
  }),
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
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import ChatHistoryPage from './page';
import { turnHeadline } from './turnPresentation';
import type { ChatbotTurn } from './types/chatbotTurn.types';

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

const failedAt = (stage: string) =>
  turnHeadline({ status: 'failed', stage } as unknown as ChatbotTurn).word;

describe('Chat History failed badge uses the turn\'s own words (N8N-RETIRE-A)', () => {
  it('reads Not confirmed for a send the CRM could not confirm, same as the turn', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ChatHistoryPage />
      </QueryClientProvider>,
    );
    await screen.findByText('Contact Alpha');
    expect(screen.getByText('Not confirmed')).toBeTruthy();
    expect(screen.queryByText(/failed at not confirmed/i)).toBeNull();
    expect(failedAt('send_unconfirmed')).toBe('Not confirmed');
  });

  it('reads Failed at Sent (with the count) for a refused send, same words as the turn', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ChatHistoryPage />
      </QueryClientProvider>,
    );
    await screen.findByText('Contact Beta');
    expect(failedAt('sent')).toBe('Failed at Sent');
    expect(screen.getByText('Failed at Sent (2)')).toBeTruthy();
  });
});
