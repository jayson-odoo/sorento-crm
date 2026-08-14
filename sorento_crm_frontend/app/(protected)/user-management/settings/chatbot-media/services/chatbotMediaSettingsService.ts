/**
 * Chatbot media settings (PLAN-chatbot-media-endpoint, slice S1, UAC S1-04 / S1-08).
 *
 * Every number the media endpoint enforces is an operator-editable column on the
 * `system_settings` singleton, not a constant in code. That was the captain's
 * requirement, and it is why this surface exists at all.
 *
 * ---------------------------------------------------------------------------
 * EXPECTED API CONTRACT - written in Phase 1, built to in Phase 2
 * ---------------------------------------------------------------------------
 *
 * READ   GET /api/v1/user-management/settings
 *   The existing settings endpoint. Phase 2 adds the fifteen `media_*` keys below to
 *   the hand-written response dict in `get_settings`. A column added to the model but
 *   not to that dict never reaches this page (UAC S1-08, and a documented repeat
 *   failure in this repo).
 *   200 -> { "settings": { ...existing..., "media_image_monthly_limit": 50, ... } }
 *
 * WRITE  POST /api/v1/user-management/settings/general
 *   The existing general-settings setattr path, which applies any provided snake_case
 *   column. Phase 2 adds the same fifteen keys to `SystemSettingUpdate` - BOTH manual
 *   builders, or the value saves and never comes back.
 *   body: the full `ChatbotMediaSettings` object below.
 *   200 -> the updated settings row.
 *
 * `apiFetch('/api/user-management/...')` maps straight to FastAPI `/api/v1/user-management/...`
 * and bypasses any Next.js route.ts proxy, so no proxy route is added for this.
 *
 * Nullable columns and what NULL means:
 *   media_image_provider / media_image_model  NULL -> fall back to the AIAssistantConfig row
 *   media_image_degraded_model                NULL -> degradation is impossible, so the
 *                                             monthly quota becomes a hard refusal instead
 *                                             of an accepted-but-degraded extraction
 *
 * ---------------------------------------------------------------------------
 * PHASE 1: both functions below resolve against `../__mocks__/chatbotMediaSettings`.
 * Phase 2 swaps each body for the `apiFetch` call sketched in its comment and deletes
 * the mock module. Nothing above the service boundary changes.
 */

import {
  mockGetChatbotMediaSettings,
  mockSaveChatbotMediaSettings,
} from '../__mocks__/chatbotMediaSettings';

export type MediaLanguageMode = 'pinned' | 'hints' | 'auto';

export interface ChatbotMediaSettings {
  /** Items per contact per calendar month, image modality. */
  media_image_monthly_limit: number;
  /** Items per contact per calendar month, voice modality. */
  media_voice_monthly_limit: number;
  /** A longer clip is refused before any transcription is attempted. */
  media_voice_max_seconds: number;
  /** Items allowed inside one burst window before pacing kicks in. */
  media_burst_limit: number;
  media_burst_window_seconds: number;
  /** Percentage of the monthly allowance at which the contact is warned once. */
  media_warn_threshold_percent: number;
  /** null = inherit the AI assistant provider. */
  media_image_provider: string | null;
  /** null = inherit the AI assistant model. */
  media_image_model: string | null;
  /** null = no degradation possible; the monthly quota becomes a hard stop. */
  media_image_degraded_model: string | null;
  media_transcribe_model: string;
  media_language_mode: MediaLanguageMode;
  /** Used in `pinned` mode. */
  media_language_pinned: string;
  /** CSV, used in `hints` mode. */
  media_language_hints: string;
  /** Hard ceiling on the queued extraction, well inside the dispatcher's 120s lock TTL. */
  media_extraction_timeout_seconds: number;
  /** Entities emitted per image before the result is truncated and says so. */
  media_max_entities: number;
}

export async function getChatbotMediaSettings(): Promise<ChatbotMediaSettings> {
  // Phase 2:
  //   const response = await apiFetch('/api/user-management/settings');
  //   if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load settings'));
  //   const data = await response.json();
  //   return pickMediaSettings(data.settings);
  return mockGetChatbotMediaSettings();
}

export async function saveChatbotMediaSettings(
  input: ChatbotMediaSettings,
): Promise<ChatbotMediaSettings> {
  // Phase 2:
  //   const response = await apiFetch('/api/user-management/settings/general', {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json' },
  //     body: JSON.stringify(input),
  //   });
  //   if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save settings'));
  //   return pickMediaSettings((await response.json()).settings);
  return mockSaveChatbotMediaSettings(input);
}
