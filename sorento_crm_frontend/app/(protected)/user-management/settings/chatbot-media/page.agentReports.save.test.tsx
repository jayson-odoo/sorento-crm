/**
 * AGENT-REPORTS: the Agent budgets card carries the switch that sends sales and outstanding
 * report asks to the agent. Off by default; one switch for panel, console and WhatsApp.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
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

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) } }));
const getSettings = vi.fn();
const saveSettings = vi.fn();
vi.mock('./services/chatbotMediaSettingsService', async (orig) => ({
  ...(await orig<typeof import('./services/chatbotMediaSettingsService')>()),
  getChatbotMediaSettings: () => getSettings(),
  saveChatbotMediaSettings: (input: unknown) => saveSettings(input),
}));
vi.mock('@/hooks/useProviderModels', () => ({
  useProviderModels: () => ({ data: { provider: 'gemini', source: 'live', message: null, models: [] } }),
  useTestProviderModel: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn(), data: undefined }),
}));

import { waitFor } from '@testing-library/react';
import ChatbotMediaSettingsPage from './page';

const BASE = {
  media_image_monthly_limit: 50,
  media_voice_monthly_limit: 100,
  media_voice_max_seconds: 120,
  media_burst_limit: 5,
  media_burst_window_seconds: 60,
  media_warn_threshold_percent: 80,
  media_image_provider: null,
  media_image_model: null,
  media_image_degraded_model: null,
  document_ai_provider: 'gemini',
  document_ai_model: 'gemini-3.5-flash',
  media_transcribe_model: 'whisper-1',
  media_voice_degraded_model: null,
  media_language_mode: 'pinned',
  media_language_pinned: 'en',
  media_language_hints: 'en,ms,zh',
  media_sync_wait_seconds: 30,
  media_extraction_timeout_seconds: 45,
  media_max_entities: 10,
  low_stock_sync_wait_seconds: 40,
  report_ask_rate_limit: 10,
  report_ask_rate_window_minutes: 10,
  chatbot_agent_max_rounds: 8,
  chatbot_agent_max_seconds: 45,
  chatbot_agent_max_input_tokens: 150000,
  chatbot_agent_compact_tokens: 40000,
  chatbot_router_min_score: 0.7,
  chatbot_agent_daily_turns: 50,
};

function mountReal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChatbotMediaSettingsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ChatbotMediaSettingsPage - agent reports switch, real save hook', () => {
  it('Save sends the switch, shows the success toast, and the switch stays on (re-seeded from the echo)', async () => {
    getSettings.mockResolvedValue({ ...BASE, chatbot_agent_reports_enabled: false });
    // The backend echoes the stored row; the page re-seeds the form from it.
    saveSettings.mockImplementation(async (input: Record<string, unknown>) => ({ ...BASE, ...input }));
    mountReal();
    const toggle = await screen.findByRole('switch', { name: 'Report asks go to the agent' });
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Chatbot media settings saved'));
    expect(saveSettings).toHaveBeenCalledWith(expect.objectContaining({ chatbot_agent_reports_enabled: true }));
    expect(toastError).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Report asks go to the agent' }).getAttribute('aria-checked')).toBe('true'),
    );
  });

  it('a failed save shows the error toast and no success', async () => {
    getSettings.mockResolvedValue({ ...BASE });
    saveSettings.mockRejectedValue(new Error('Settings could not be saved'));
    mountReal();
    fireEvent.click(await screen.findByRole('switch', { name: 'Report asks go to the agent' }));
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Settings could not be saved'));
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
