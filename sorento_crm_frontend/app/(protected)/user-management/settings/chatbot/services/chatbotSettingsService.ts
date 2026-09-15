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
 *   The existing settings blob. Its hand-written response dict carries the seven
 *   chatbot keys below; a column added to the model but not to that dict never
 *   reaches this page.
 *
 * WRITE  POST /api/v1/user-management/settings/general
 *   `user_management.settings.edit`. The same seven keys, snake_case, applied by the
 *   existing setattr path.
 *   422 when `chatbot_completed_lanes` names a lane this build cannot complete; the
 *   message names it. The screen offers exactly the vocabulary above, so that 422 is
 *   the backstop for a direct call rather than how an operator finds out.
 *
 * `chatbot_tier_order` (`string[]`, dealer/office/end_user) and `chatbot_memory`
 * (one JSONB: `recall_default`, `episode_retention_days`, `profile_fields`,
 * `focus_reset_events`) are the chatbot turn re-architecture's own two additions
 * (S5, AC-1560/AC-1561) - same route, same setattr path, no card of their own.
 */

export interface ChatbotLane {
  /** A `branch_kind` from the engine's own vocabulary. */
  kind: string;
  /** False when a lane this build ships cannot run under the current switches. */
  built: boolean;
}

/** Settings > Chatbot > Memory card (chatbot turn re-architecture, AC-1513, AC-1561). */
export interface ChatbotMemorySettings {
  recall_default: boolean;
  episode_retention_days: number;
  profile_fields: string[];
  focus_reset_events: string[];
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
  /** Office / Dealer / End user, orderable (AC-1502's tier axis; replaces the three
   * `TIER_ORDER` code copies). */
  chatbot_tier_order: string[];
  chatbot_memory: ChatbotMemorySettings;
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
  // Mirrors `lane_vocabulary.default_tier_order()` / `default_chatbot_memory()` - only
  // reached when there is no settings row at all (see the note above), same as every
  // other fallback here.
  chatbot_tier_order: ['dealer', 'office', 'end_user'],
  chatbot_memory: {
    recall_default: false,
    episode_retention_days: 180,
    profile_fields: ['tier', 'language', 'default_ledgers'],
    focus_reset_events: ['topic_switch'],
  },
};

function pickChatbotSettings(row: Record<string, unknown> | null | undefined): ChatbotSettings {
  const memory = row?.chatbot_memory as Partial<ChatbotMemorySettings> | null | undefined;
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
    chatbot_tier_order: Array.isArray(row?.chatbot_tier_order)
      ? (row.chatbot_tier_order as string[])
      : FALLBACKS.chatbot_tier_order,
    chatbot_memory: memory
      ? {
          recall_default: Boolean(memory.recall_default),
          episode_retention_days:
            typeof memory.episode_retention_days === 'number'
              ? memory.episode_retention_days
              : FALLBACKS.chatbot_memory.episode_retention_days,
          profile_fields: Array.isArray(memory.profile_fields)
            ? memory.profile_fields
            : FALLBACKS.chatbot_memory.profile_fields,
          focus_reset_events: Array.isArray(memory.focus_reset_events)
            ? memory.focus_reset_events
            : FALLBACKS.chatbot_memory.focus_reset_events,
        }
      : FALLBACKS.chatbot_memory,
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
