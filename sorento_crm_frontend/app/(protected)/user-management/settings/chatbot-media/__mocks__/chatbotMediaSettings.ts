/**
 * PHASE 1 MOCK - delete in Phase 2 (PLAN-chatbot-media-endpoint, slice S1).
 *
 * Holds one in-memory copy of the `media_*` columns of the `system_settings`
 * singleton, seeded with the plan's defaults. The contract it stands in for is
 * documented in `../services/chatbotMediaSettingsService.ts`.
 *
 * The defaults are not arbitrary: `media_transcribe_model = whisper-1` with
 * `media_language_mode = pinned` / `media_language_pinned = en` reproduces
 * today's live behaviour exactly, so a fresh install changes nothing until an
 * operator chooses to.
 *
 * `media_image_degraded_model` starts NULL on purpose. No degraded model means
 * degradation is impossible and the monthly quota becomes a hard stop, which the
 * settings page has to say out loud rather than leave to be discovered.
 */

import type { ChatbotMediaSettings } from '../services/chatbotMediaSettingsService';

const MOCK_LATENCY_MS = 240;

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

let current: ChatbotMediaSettings = {
  media_image_monthly_limit: 50,
  media_voice_monthly_limit: 100,
  media_voice_max_seconds: 120,
  media_burst_limit: 5,
  media_burst_window_seconds: 60,
  media_warn_threshold_percent: 80,
  media_image_provider: null,
  media_image_model: null,
  media_image_degraded_model: null,
  media_transcribe_model: 'whisper-1',
  media_language_mode: 'pinned',
  media_language_pinned: 'en',
  media_language_hints: 'en,ms,zh',
  media_extraction_timeout_seconds: 45,
  media_max_entities: 10,
};

export async function mockGetChatbotMediaSettings(): Promise<ChatbotMediaSettings> {
  await sleep(MOCK_LATENCY_MS);
  return { ...current };
}

export async function mockSaveChatbotMediaSettings(
  input: ChatbotMediaSettings,
): Promise<ChatbotMediaSettings> {
  await sleep(MOCK_LATENCY_MS);
  current = { ...input };
  return { ...current };
}
