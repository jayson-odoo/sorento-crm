/**
 * Settings > Chatbot - `useSaveChatbotSettings`, the toasts (R-S1, reviewer round 1).
 *
 * The failed-save toast belongs to the HOOK and to nothing else. The page's Save used to
 * pass an `onError` of its own beside it, so one failed save toasted the same message
 * twice; that call-site handler is gone and this file is where the behaviour is pinned,
 * at the layer that owns it (`hooks/useChatbotSettings.ts`, the layering rule: UI ->
 * hook -> service -> api-client).
 *
 * RED before the fix in the sense that matters: with the call-site handler still in
 * place, `page.test.tsx` and this file BOTH asserted a toast for one failure, which is
 * exactly the duplication - `expect(toast.error).toHaveBeenCalledTimes(1)` below is what
 * a second handler cannot satisfy once both run in the same render.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('../services/chatbotSettingsService', () => ({
  getChatbotSettings: vi.fn(),
  saveChatbotSettings: vi.fn(),
}));

import { toast } from '@/lib/toast';
import { saveChatbotSettings } from '../services/chatbotSettingsService';
import { useSaveChatbotSettings } from './useChatbotSettings';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const draft = { chatbot_stock_low_threshold_pct: 40 } as never;

describe('useSaveChatbotSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('a failed save toasts the extracted message, exactly once', async () => {
    vi.mocked(saveChatbotSettings).mockRejectedValue(
      new Error('Threshold must be between 1 and 100'),
    );

    const { result } = renderHook(() => useSaveChatbotSettings(), { wrapper });
    result.current.mutate(draft);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining('Threshold must be between 1 and 100'),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('a failure with no message of its own still says something', async () => {
    vi.mocked(saveChatbotSettings).mockRejectedValue(new Error(''));

    const { result } = renderHook(() => useSaveChatbotSettings(), { wrapper });
    result.current.mutate(draft);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to save settings'));
  });

  it('a successful save toasts once and never as an error', async () => {
    vi.mocked(saveChatbotSettings).mockResolvedValue({
      chatbot_stock_low_threshold_pct: 40,
    } as never);

    const { result } = renderHook(() => useSaveChatbotSettings(), { wrapper });
    result.current.mutate(draft);

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Chatbot settings saved'));
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });
});
