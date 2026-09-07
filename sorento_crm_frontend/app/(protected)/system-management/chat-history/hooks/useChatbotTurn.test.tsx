/**
 * `getChatbotTurn` / `useChatbotTurn` (chatbot growth r1, Slice D2 review fix).
 *
 * Mocks `apiFetch` (the api-client boundary), the same pattern
 * `ContactFieldRevealsSection.test.tsx` uses, so the hook -> service -> fetch
 * chain is exercised for real and only the network is stubbed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { useChatbotTurn } from './useChatbotTurns';
import { getChatbotTurn } from '../services/chatbotTurnService';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'ZZT-turn-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.1',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-09-07T00:00:00Z',
    finished_at: '2026-09-07T00:00:02Z',
    trace: [],
    response: null,
    trace_detail: {
      stages: [],
      parse: null,
      decay: [],
      open_question: null,
      focus: [],
      tool: null,
      crossdomain: [],
      reveals: { restricted_fields_seen: [], granted: [], dropped: [] },
      session: { before: {}, after: {}, diff: [] },
    },
    ...over,
  };
}

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'Wrapper';
  return Wrapper;
}

beforeEach(() => {
  apiFetch.mockReset();
});

afterEach(() => cleanup());

describe('getChatbotTurn', () => {
  it('calls GET /api/v1/system/chatbot/turns/{id} and returns the body', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => detail() });

    const result = await getChatbotTurn('ZZT-turn-1');

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/system/chatbot/turns/ZZT-turn-1');
    expect(result.id).toBe('ZZT-turn-1');
    expect(result.trace_detail.stages).toEqual([]);
  });

  it('throws the extracted error message on a non-ok response', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Turn not found.' }),
    });

    await expect(getChatbotTurn('ZZT-turn-missing')).rejects.toThrow();
  });
});

describe('useChatbotTurn', () => {
  it('fetches the turn once a turnId is given', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => detail() });

    const { result } = renderHook(() => useChatbotTurn('ZZT-turn-1'), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.id).toBe('ZZT-turn-1');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/system/chatbot/turns/ZZT-turn-1');
  });

  it('does not fetch when turnId is null', () => {
    renderHook(() => useChatbotTurn(null), { wrapper: wrapper() });
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
