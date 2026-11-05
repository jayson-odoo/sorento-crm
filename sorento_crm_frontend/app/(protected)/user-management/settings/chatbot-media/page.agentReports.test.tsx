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

const mockQuery = vi.fn();
const mockMutation = vi.fn();
vi.mock('./hooks/useChatbotMediaSettings', () => ({
  useChatbotMediaSettings: () => mockQuery(),
  useSaveChatbotMediaSettings: () => mockMutation(),
}));
vi.mock('@/hooks/useProviderModels', () => ({
  useProviderModels: () => ({ data: { provider: 'gemini', source: 'live', message: null, models: [] } }),
  useTestProviderModel: () => ({ mutate: vi.fn(), isPending: false, reset: vi.fn(), data: undefined }),
}));

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

function mount(overrides: Record<string, unknown> = {}) {
  const mutate = vi.fn();
  mockMutation.mockReturnValue({ isPending: false, mutate });
  mockQuery.mockReturnValue({ data: { ...BASE, ...overrides }, isLoading: false, isError: false });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChatbotMediaSettingsPage />
    </QueryClientProvider>,
  );
  return mutate;
}

const toggle = () => screen.getByRole('switch', { name: 'Report asks go to the agent' });
const save = () => fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

afterEach(() => cleanup());

describe('ChatbotMediaSettingsPage - agent reports switch', () => {
  it('is off when the row has no value (a row from before the column)', () => {
    mount();
    expect(toggle().getAttribute('aria-checked')).toBe('false');
  });

  it('seeds from the settings', () => {
    mount({ chatbot_agent_reports_enabled: true });
    expect(toggle().getAttribute('aria-checked')).toBe('true');
  });

  it('a click turns it on and the save carries it', () => {
    const mutate = mount();
    fireEvent.click(toggle());
    save();
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ chatbot_agent_reports_enabled: true }),
      expect.anything(),
    );
  });

  it('an unedited save keeps it off', () => {
    const mutate = mount();
    save();
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ chatbot_agent_reports_enabled: false }),
      expect.anything(),
    );
  });
});
