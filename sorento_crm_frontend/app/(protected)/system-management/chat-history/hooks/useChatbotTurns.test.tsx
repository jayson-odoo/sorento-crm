/**
 * S2b Phase 2 test-first (AC-258): `useRetryChatbotTurn` invalidates the turns query on
 * success and surfaces the service's error message on conflict (409). The service call
 * itself is mocked (per the tester brief: "mock the hooks, not the service internals" -
 * here the hook IS what's under test, so the layer below it, `chatbotTurnService`, is
 * the mock boundary).
 *
 * Like `TurnPanel.test.tsx`, this locks Phase 1 behaviour already shipped in
 * `useChatbotTurns.ts` - the mutation function itself still calls the MOCK service
 * (`retryChatbotTurn` returns/throws against `MOCK_TURNS`), so the object under test is
 * unchanged by Phase 2's backend wiring. The genuinely new Phase 2 surface is the real
 * `POST /api/v1/system/chatbot/turns/{id}/retry` call the service will make once the
 * mock is swapped out - covered on the backend by `tests/chatbot/test_turns_admin_api.py`.
 *
 * S2b hardening (FE 1b): `useChatbotTurns` derives `retryUnavailableReason` from the
 * SAME list payload rather than a route of its own (`hooks/useChatbotTurns.ts:41-46`) -
 * `retry_available` wins when present, `retry_unavailable_reason` is the message, and a
 * list response that omits both fields (an older cache entry, or a shape the backend has
 * not sent yet) must not read as "unavailable" by accident.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { CHATBOT_TURNS_KEY, useChatbotTurns, useRetryChatbotTurn } from './useChatbotTurns';

const retryChatbotTurn = vi.fn();
const getChatbotTurns = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();

const getFailedChatbotContacts = vi.fn();

vi.mock('../services/chatbotTurnService', async () => {
  const actual = await vi.importActual<typeof import('../services/chatbotTurnService')>(
    '../services/chatbotTurnService',
  );
  return {
    retryChatbotTurn: (...args: unknown[]) => retryChatbotTurn(...args),
    getChatbotTurns: (...args: unknown[]) => getChatbotTurns(...args),
    getFailedChatbotContacts: (...args: unknown[]) => getFailedChatbotContacts(...args),
    // The real pure function - nothing here needs it stubbed.
    indexTurnsByMessageId: actual.indexTurnsByMessageId,
  };
});

vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

function wrapper(client: QueryClient) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'Wrapper';
  return Wrapper;
}

beforeEach(() => {
  retryChatbotTurn.mockReset();
  getChatbotTurns.mockReset();
  getFailedChatbotContacts.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
});

afterEach(() => cleanup());

describe('useRetryChatbotTurn (AC-258)', () => {
  it('invalidates the turns query and toasts success with the new attempt number', async () => {
    retryChatbotTurn.mockResolvedValue({ turn_id: 'ZZT-turn-1', attempt: 2 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useRetryChatbotTurn(), { wrapper: wrapper(client) });
    result.current.mutate('ZZT-turn-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(retryChatbotTurn).toHaveBeenCalledWith('ZZT-turn-1');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: CHATBOT_TURNS_KEY });
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('2'));
  });

  it('surfaces the 409 conflict message via an error toast rather than invalidating', async () => {
    retryChatbotTurn.mockRejectedValue(new Error('Only a failed turn can be retried'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useRetryChatbotTurn(), { wrapper: wrapper(client) });
    result.current.mutate('ZZT-turn-2');

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(toastError).toHaveBeenCalledWith('Only a failed turn can be retried');
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

function renderTurns(contactId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(() => useChatbotTurns(contactId), { wrapper: wrapper(client) });
}

describe('useChatbotTurns retryUnavailableReason (S2b hardening 1b)', () => {
  it('is null when the list says retry is available', async () => {
    getChatbotTurns.mockResolvedValue({
      items: [],
      next_cursor: null,
      retry_available: true,
      retry_unavailable_reason: 'unused when available',
    });

    const { result } = renderTurns('ZZT-contact-1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.retryUnavailableReason).toBeNull();
  });

  it('is the reason string when the list says retry is unavailable', async () => {
    getChatbotTurns.mockResolvedValue({
      items: [],
      next_cursor: null,
      retry_available: false,
      retry_unavailable_reason: 'Retry is not configured in this environment.',
    });

    const { result } = renderTurns('ZZT-contact-2');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.retryUnavailableReason).toBe(
      'Retry is not configured in this environment.',
    );
  });

  it('is null (not "unavailable") when the payload omits both fields entirely', async () => {
    getChatbotTurns.mockResolvedValue({ items: [], next_cursor: null });

    const { result } = renderTurns('ZZT-contact-3');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.retryUnavailableReason).toBeNull();
  });
});
