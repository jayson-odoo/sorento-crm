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
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { CHATBOT_TURNS_KEY, useRetryChatbotTurn } from './useChatbotTurns';

const retryChatbotTurn = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();

vi.mock('../services/chatbotTurnService', () => ({
  retryChatbotTurn: (...args: unknown[]) => retryChatbotTurn(...args),
}));

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
