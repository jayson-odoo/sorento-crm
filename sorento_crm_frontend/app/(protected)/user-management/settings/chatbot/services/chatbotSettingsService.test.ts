/**
 * CHAT-RELEASE-1021: the two release switches are read off the settings row and sent
 * back on save. A value the row does not hold (an older backend) reads as the inert
 * default: closed lists `block`, reply composer off.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockApiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => mockApiFetch(...args) }));

import { getChatbotSettings, saveChatbotSettings } from './chatbotSettingsService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

describe('chatbotSettingsService - release switches', () => {
  beforeEach(() => mockApiFetch.mockReset());

  it('reads the closed lists mode and the composer switch off the settings row', async () => {
    mockApiFetch.mockResolvedValue(
      ok({ settings: { chatbot_closed_lists_mode: 'index', chatbot_composer_enabled: true } }),
    );
    const got = await getChatbotSettings();
    expect(got.chatbot_closed_lists_mode).toBe('index');
    expect(got.chatbot_composer_enabled).toBe(true);
  });

  it('reads a row without them as block and off', async () => {
    mockApiFetch.mockResolvedValue(ok({ settings: { chatbot_closed_lists_mode: 'weird' } }));
    const got = await getChatbotSettings();
    expect(got.chatbot_closed_lists_mode).toBe('block');
    expect(got.chatbot_composer_enabled).toBe(false);
  });

  it('sends both switches in the save body', async () => {
    mockApiFetch.mockResolvedValue(ok({ data: {} }));
    const draft = {
      chatbot_stock_denial_enabled: false,
      chatbot_business_lane_enabled: false,
      chatbot_ordering_enabled: false,
      chatbot_unsupported_domains: [],
      chatbot_direct_ingress_mode: 'off' as const,
      chatbot_direct_ingress_contacts: null,
      chatbot_closed_lists_mode: 'index' as const,
      chatbot_composer_enabled: true,
    };
    await saveChatbotSettings(draft);
    const [, init] = mockApiFetch.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.chatbot_closed_lists_mode).toBe('index');
    expect(body.chatbot_composer_enabled).toBe(true);
  });
});
