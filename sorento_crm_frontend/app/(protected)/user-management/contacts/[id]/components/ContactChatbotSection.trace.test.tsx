/**
 * TRACE-SIDEBAR (owner, 11 Nov 2026): clicking a Conversations row on the contact's Chatbot
 * section opens that conversation's first turn in the shared turn trace drawer, over the
 * contact page. It no longer navigates away to Chat History.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactChatbotSection from './ContactChatbotSection';
import type { ContactChatbotMemory } from '../services/contactChatbotService';

const push = vi.fn();
const getChatbotTurn = vi.fn();

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contacts/c1',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/app/(protected)/system-management/chat-history/services/chatbotTurnService', () => ({
  getChatbotTurn: (...args: unknown[]) => getChatbotTurn(...args),
}));

const useContactChatbotMemory = vi.fn();
vi.mock('../hooks/useContactChatbot', () => ({
  useContactChatbotProfile: () => ({
    data: {
      chatbot_memory_level: null,
      tier: null,
      default_ledgers: [],
      stock_allowed: true,
      notify_salesman: false,
      packing_list_allowed: false,
    },
    isLoading: false,
    isError: false,
  }),
  useSaveContactChatbotProfile: () => ({ mutate: vi.fn(), isPending: false }),
  useSaveContactEscalation: () => ({ mutate: vi.fn(), isPending: false }),
  useSaveContactChatbotAllowed: () => ({ mutate: vi.fn(), isPending: false }),
  useContactChatbotMemory: (...a: unknown[]) => useContactChatbotMemory(...a),
  useSaveContactFact: () => ({ mutate: vi.fn(), isPending: false }),
  contactChatbotMemoryQueryKey: (contactId: string) => ['contact-chatbot-memory', contactId],
}));

const TURN_ID = 'beef5678-0000-4000-8000-000000000002';

const memory: ContactChatbotMemory = {
  level: { own: null, effective: 'full', system_default: 'full' },
  facts: [],
  vocabulary: [],
  episodes: {
    kept: 1,
    limit: 20,
    current: null,
    rows: [
      {
        id: 'f1',
        date: '2026-11-10T03:02:17',
        domains: ['inventory'],
        topic: 'Stock',
        summary: 'Asked about stock and got an answer.',
        turn_count: 2,
        close_reason: 'topic_switch',
        first_turn_id: TURN_ID,
      },
    ],
  },
  open_orders: { customer_name: null, rows: [] },
};

beforeEach(() => {
  push.mockReset();
  getChatbotTurn.mockReset();
  getChatbotTurn.mockReturnValue(new Promise(() => {}));
  useContactChatbotMemory.mockReturnValue({ data: memory, isLoading: false, isError: false });
});
afterEach(() => cleanup());

describe('Contact Conversations row opens the turn trace drawer in place (TRACE-SIDEBAR)', () => {
  it('row click opens the drawer and does not navigate', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ContactChatbotSection contactId="c1" />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByText('Asked about stock and got an answer.'));

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('Turn #beef')).toBeTruthy();
    expect(getChatbotTurn).toHaveBeenCalledWith(TURN_ID);
    expect(push).not.toHaveBeenCalled();
    expect(document.querySelector('a[href*="chat-history"]')).toBeNull();
  });
});
