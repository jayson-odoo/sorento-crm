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

const mockTurnDetailDrawer = vi.fn();
vi.mock('./components/TurnDetailDrawer', () => ({
  TurnDetailDrawer: (props: { turnId: string | null; shadowTurnId: string | null }) => {
    mockTurnDetailDrawer(props);
    return null;
  },
}));

import ChatHistoryPage from './page';

afterEach(() => {
  cleanup();
  mockGetChatMessages.mockReset();
  mockGetChatbotTurns.mockReset();
  mockTurnDetailDrawer.mockReset();
});

function shadowRow(i: number, over: Record<string, unknown> = {}) {
  return {
    id: `shadow-${i}`,
    contact_respond_id: `c${i}`,
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
    shadow_of: `live-${i}`,
    domains: ['inventory'],
    contact_display: `Contact ${i}`,
    message: 'stock check',
    live: { id: `live-${i}`, branch_kind: 'business_query', domains: ['inventory'] },
    ...over,
  };
}

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

  it('shows "Newest 200 shown" when the shadow window is capped at 200 rows', async () => {
    mockGetChatbotTurns.mockResolvedValue({
      items: Array.from({ length: 200 }, (_, i) => shadowRow(i)),
      next_cursor: 'cursor-past-200',
      summary: { count: 250, branch_parity: 0.9, asks_parity: 0.8 },
    });
    renderPage();

    fireEvent.click(shadowToggle());

    await waitFor(() => expect(screen.getByTestId('shadow-truncated')).toBeInTheDocument());
    expect(screen.getByTestId('shadow-truncated')).toHaveTextContent(/newest 200 shown/i);
  });

  it('does NOT show the truncation notice at 199 rows (no next_cursor)', async () => {
    mockGetChatbotTurns.mockResolvedValue({
      items: Array.from({ length: 199 }, (_, i) => shadowRow(i)),
      next_cursor: null,
      summary: { count: 199, branch_parity: 0.9, asks_parity: 0.8 },
    });
    renderPage();

    fireEvent.click(shadowToggle());

    await waitFor(() =>
      expect(screen.getByTestId('shadow-summary')).toHaveTextContent('199 shadow turns'),
    );
    expect(screen.queryByTestId('shadow-truncated')).toBeNull();
  });

  it('a shadow row with no live turn shows the "no live turn" badge and is not clickable', async () => {
    mockGetChatbotTurns.mockResolvedValue({
      items: [shadowRow(1, { live: null })],
      next_cursor: null,
      summary: { count: 1, branch_parity: null, asks_parity: null },
    });
    renderPage();

    fireEvent.click(shadowToggle());

    await waitFor(() => expect(screen.getByText(/no live turn/i)).toBeInTheDocument());

    fireEvent.click(screen.getByText(/no live turn/i).closest('tr')!);

    // No onRowClick handler is ever attached to a row `isRowClickable` refuses
    // (`data-grid-table.tsx`'s own `opensOnClick` gate), so the drawer never opens -
    // neither prop the drawer reads becomes non-null.
    const lastCall = mockTurnDetailDrawer.mock.calls.at(-1)?.[0];
    expect(lastCall?.turnId ?? null).toBeNull();
    expect(lastCall?.shadowTurnId ?? null).toBeNull();
  });

  it('the summary line reads "first 5000" when the response says the window itself was truncated', async () => {
    mockGetChatbotTurns.mockResolvedValue({
      items: [shadowRow(1)],
      next_cursor: null,
      summary: { count: 5000, branch_parity: 0.7, asks_parity: 0.6, truncated: true },
    });
    renderPage();

    fireEvent.click(shadowToggle());

    await waitFor(() =>
      expect(screen.getByTestId('shadow-summary')).toHaveTextContent(/first 5000/i),
    );
  });
});
