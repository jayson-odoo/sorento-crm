/**
 * Chat History page - the Shadow toggle (AC-1029, AC-1030).
 *
 * The shadow grid, the summary line and the empty state, driven by mocking the
 * SERVICES the page's own `useQuery` / `useShadowTurnList` call rather than a
 * mockable hook wrapper - `getChatMessages` feeds the default message grid directly,
 * and `getChatbotTurns` (via `useShadowTurnList`) feeds the shadow one.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

Element.prototype.scrollIntoView = vi.fn();
(Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const mockGetChatMessages = vi.fn();
const mockGetChatbotTurns = vi.fn();

vi.mock('./services/chatHistoryService', () => ({
  getChatMessages: (...args: unknown[]) => mockGetChatMessages(...args),
}));

vi.mock('./services/chatbotTurnService', () => ({
  getChatbotTurns: (...args: unknown[]) => mockGetChatbotTurns(...args),
  getFailedChatbotContacts: vi.fn().mockResolvedValue({ items: [] }),
  getChatbotTurn: vi.fn(),
  retryChatbotTurn: vi.fn(),
  indexTurnsByMessageId: (turns: { message_id: string | null }[]) => {
    const map = new Map();
    for (const t of turns) if (t.message_id) map.set(t.message_id, t);
    return map;
  },
}));

vi.mock('./hooks/useChatHistory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./hooks/useChatHistory')>()),
  useExportChatHistory: () => ({ mutate: vi.fn(), isPending: false }),
}));

// Container pulls SettingsProvider context this test does not need - same precedent as
// `warehouses/[id]/page.test.tsx`.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import ChatHistoryPage from './page';

afterEach(() => {
  cleanup();
  mockGetChatMessages.mockReset();
  mockGetChatbotTurns.mockReset();
});

function renderPage() {
  mockGetChatMessages.mockResolvedValue({ items: [], next_cursor: null, pagination: { total: 0 } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatHistoryPage />
    </QueryClientProvider>,
  );
}

const shadowToggle = () => screen.getByRole('button', { name: /^shadow$/i });

describe('ChatHistoryPage - Shadow toggle', () => {
  it('the summary line and the shadow grid are absent until Shadow is turned on', () => {
    renderPage();

    expect(screen.queryByTestId('shadow-summary')).toBeNull();
  });

  it('turning Shadow on swaps the grid and shows the summary line once the window resolves', async () => {
    mockGetChatbotTurns.mockResolvedValue({
      items: [
        {
          id: 'shadow-1',
          contact_respond_id: 'c1',
          message_id: null,
          status: 'done',
          stage: null,
          branch_kind: 'business_query',
          attempt: 1,
          is_test: false,
          created_at: '2026-09-13T00:00:00Z',
          finished_at: '2026-09-13T00:00:01Z',
          trace: [],
          response: null,
          shadow_of: 'live-1',
          domains: ['inventory'],
          contact_display: 'Ann (+60111)',
          message: 'stock check',
          live: { id: 'live-1', branch_kind: 'business_query', domains: ['inventory'] },
        },
      ],
      next_cursor: null,
      summary: { count: 5, branch_parity: 0.8, asks_parity: 0.6 },
    });
    renderPage();

    fireEvent.click(shadowToggle());

    await waitFor(() =>
      expect(screen.getByTestId('shadow-summary')).toHaveTextContent('5 shadow turns'),
    );
    expect(screen.getByTestId('shadow-summary')).toHaveTextContent('branch parity 80%');
  });

  it('an empty shadow window shows the empty-state message, not a blank grid', async () => {
    mockGetChatbotTurns.mockResolvedValue({
      items: [],
      next_cursor: null,
      summary: { count: 0, branch_parity: null, asks_parity: null },
    });
    renderPage();

    fireEvent.click(shadowToggle());

    await waitFor(() =>
      expect(screen.getByTestId('shadow-summary')).toHaveTextContent(/no shadow turns in this range/i),
    );
    // count 0 -> shadowSummaryLine is null -> the summary line falls back to the SAME
    // empty-state sentence rather than a "0 shadow turns" line (shadowDrift.test.ts pins
    // the null-on-zero rule directly; this is the page reading it correctly).
    expect(screen.getByTestId('shadow-summary')).toHaveTextContent(/no shadow turns/i);
  });
});
