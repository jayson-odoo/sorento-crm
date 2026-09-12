import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Chatbot settings (AC-809, AC-810, issue #679).
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT
 * ---------------------------------------------------------------------------
 *
 * READ   GET /api/v1/user-management/settings/chatbot-lanes
 *   `user_management.settings.view`. The branch-kind vocabulary the CRM build can
 *   complete, straight off `contracts.CRM_COMPLETED_BRANCH_KINDS`, each with the
 *   `built` flag the screen needs: the three business arms only run once
 *   `chatbot_business_lane_enabled` is on, so a checkbox for one of them is
 *   disabled until then rather than saving and doing nothing.
 *   200 -> [{ "kind": "low_signal", "built": true }, ...]
 *
 * READ   GET /api/v1/user-management/settings
 *   The existing settings blob. Its hand-written response dict carries the five
 *   chatbot keys below; a column added to the model but not to that dict never
 *   reaches this page.
 *
 * WRITE  POST /api/v1/user-management/settings/general
 *   `user_management.settings.edit`. The same five keys, snake_case, applied by the
 *   existing setattr path.
 *   422 when `chatbot_completed_lanes` names a lane this build cannot complete; the
 *   message names it. The screen offers exactly the vocabulary above, so that 422 is
 *   the backstop for a direct call rather than how an operator finds out.
 *
 * ---------------------------------------------------------------------------
 * `chatbot_parser_shadow_version` (L1-S0, AC-1027 / AC-1028) - LIVE
 * ---------------------------------------------------------------------------
 *
 *   GET  /api/v1/user-management/settings
 *     `settings.chatbot_parser_shadow_version`: string | null
 *
 *   POST /api/v1/user-management/settings/general
 *     `chatbot_parser_shadow_version`: string | null   (null clears it)
 *
 * The VALUE is `"<prompt key>@<version>"` - `chatbot_semantic_parser@18` - built from the
 * versions `GET /api/v1/system/chatbot/console/prompt-versions` returns (newest first).
 * NOT the version's uuid: the value is read back on the settings screen and again on every
 * shadow turn's trace, and a name plus a number says which prompt and which version of it
 * without a lookup. The select renders "v18 - full - production".
 *
 * Null means no shadow parse runs at all. Set, every real turn ALSO runs that version and
 * writes a second `chatbot.turns` row with `ingress = "shadow"`; a shadow failure never
 * fails the live turn.
 *
 * Both dict builders owe it (`GET /settings`'s hand-written response dict and
 * `SystemSettingUpdate`), or it never reaches this page.
 */

export interface ChatbotLane {
  /** A `branch_kind` from the engine's own vocabulary. */
  kind: string;
  /** False when a lane this build ships cannot run under the current switches. */
  built: boolean;
}

export interface ChatbotSettings {
  /** Which lanes the CRM may FINISH. Everything else delegates to n8n. */
  chatbot_completed_lanes: string[];
  chatbot_stock_denial_enabled: boolean;
  /** The business lane may RUN. Independent of it being allowed to answer. */
  chatbot_business_lane_enabled: boolean;
  /** S7 mode: the CRM orders turns per contact and owns the tail. */
  chatbot_ordering_enabled: boolean;
  chatbot_unsupported_domains: string[];
  /**
   * AC-1027. The `chatbot_semantic_parser` version every real turn ALSO runs, in the
   * background, so the owner can watch a new parser's answers beside the live one before
   * promoting it. `"<prompt key>@<version>"`, or null for no shadow parse at all.
   */
  chatbot_parser_shadow_version: string | null;
}

/**
 * What a settings row that predates these columns reads as.
 *
 * `chatbot_unsupported_domains` is deliberately EMPTY here rather than a copy of the
 * backend's shipped default (AC-931). It used to read `['goods_receive', 'spo_allocation']`
 * and went stale the day A6 unblocked `spo_allocation`, which is the fourth copy of one
 * default drifting - the backend now derives it once, from `DOMAIN_SPEC`, and a mirror
 * here could only ever be a fifth.
 *
 * Nothing is lost by dropping it. The column is NOT NULL with its own server default, and
 * `GET /settings` emits the whole `settings` object as `null` only when there is no
 * settings row at all - the one case this fallback can fire. In that state
 * `POST /settings/general` answers 404 ("Settings not found"), so the screen cannot save
 * an empty list over anything either.
 */
const FALLBACKS: ChatbotSettings = {
  chatbot_completed_lanes: [],
  chatbot_stock_denial_enabled: false,
  chatbot_business_lane_enabled: false,
  chatbot_ordering_enabled: false,
  chatbot_unsupported_domains: [],
  chatbot_parser_shadow_version: null,
};


function pickChatbotSettings(row: Record<string, unknown> | null | undefined): ChatbotSettings {
  return {
    chatbot_completed_lanes: Array.isArray(row?.chatbot_completed_lanes)
      ? (row.chatbot_completed_lanes as string[])
      : FALLBACKS.chatbot_completed_lanes,
    chatbot_stock_denial_enabled: Boolean(row?.chatbot_stock_denial_enabled),
    chatbot_business_lane_enabled: Boolean(row?.chatbot_business_lane_enabled),
    chatbot_ordering_enabled: Boolean(row?.chatbot_ordering_enabled),
    chatbot_unsupported_domains: Array.isArray(row?.chatbot_unsupported_domains)
      ? (row.chatbot_unsupported_domains as string[])
      : FALLBACKS.chatbot_unsupported_domains,
    chatbot_parser_shadow_version:
      (row?.chatbot_parser_shadow_version as string | null | undefined) ?? null,
  };
}

export async function getChatbotLanes(): Promise<ChatbotLane[]> {
  const response = await apiFetch('/api/user-management/settings/chatbot-lanes');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load chatbot lanes'));
  }
  const data = await response.json();
  return Array.isArray(data) ? (data as ChatbotLane[]) : [];
}

export async function getChatbotSettings(): Promise<ChatbotSettings> {
  const response = await apiFetch('/api/user-management/settings');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load settings'));
  }
  const data = await response.json();
  return pickChatbotSettings(data?.settings);
}

export async function saveChatbotSettings(input: ChatbotSettings): Promise<ChatbotSettings> {
  const response = await apiFetch('/api/user-management/settings/general', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save settings'));
  }
  const data = await response.json();
  return pickChatbotSettings(data?.data);
}
