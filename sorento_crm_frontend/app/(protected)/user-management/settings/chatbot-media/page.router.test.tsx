/**
 * AGENTIC-P2-ROUTE K2: the Agent budgets card gains the router minimum score and the
 * agent turns per contact per day. Red first.
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

const score = () => screen.getByLabelText('Router minimum score') as HTMLInputElement;
const daily = () => screen.getByLabelText('Agent turns per contact per day') as HTMLInputElement;
const save = () => fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

afterEach(() => cleanup());

describe('ChatbotMediaSettingsPage - router fields (K2)', () => {
  it('seeds both fields from the settings', () => {
    mount({ chatbot_router_min_score: 0.8, chatbot_agent_daily_turns: 12 });
    expect(score().value).toBe('0.8');
    expect(daily().value).toBe('12');
  });

  it('both go in the save payload as numbers', () => {
    const mutate = mount();
    fireEvent.change(score(), { target: { value: '0.85' } });
    fireEvent.change(daily(), { target: { value: '0' } });
    save();
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ chatbot_router_min_score: 0.85, chatbot_agent_daily_turns: 0 }),
      expect.anything(),
    );
  });

  it('an unedited save still carries the defaults', () => {
    const mutate = mount();
    save();
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ chatbot_router_min_score: 0.7, chatbot_agent_daily_turns: 50 }),
      expect.anything(),
    );
  });

  it.each(['0.4', '0.96'])('refuses a score of %s outside 0.5 to 0.95', (value) => {
    const mutate = mount();
    fireEvent.change(score(), { target: { value } });
    save();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('refuses a negative daily cap', () => {
    const mutate = mount();
    fireEvent.change(daily(), { target: { value: '-1' } });
    save();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('the score input carries min 0.5, max 0.95 and step 0.05', () => {
    mount();
    expect(score()).toHaveAttribute('min', '0.5');
    expect(score()).toHaveAttribute('max', '0.95');
    expect(score()).toHaveAttribute('step', '0.05');
  });
});
