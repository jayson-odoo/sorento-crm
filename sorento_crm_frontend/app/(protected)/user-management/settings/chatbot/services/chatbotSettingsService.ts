import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Chatbot settings (AC-809, AC-810, issue #679).
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT
 * ---------------------------------------------------------------------------
 *
 * READ   GET /api/v1/user-management/settings
 *   The existing settings blob. Its hand-written response dict carries the four
 *   chatbot switch/domain keys below (plus `chatbot_tier_order` / `chatbot_memory`,
 *   read separately below); a column added to the model but not to that dict never
 *   reaches this page.
 *
 * WRITE  POST /api/v1/user-management/settings/general
 *   `user_management.settings.edit`. Partial: only the keys a caller sends are
 *   applied by the existing setattr path, so the Switches card's save and the
 *   Memory/Tier-order cards' saves are independent writes to the same row.
 *
 * `chatbot_tier_order` (`string[]`, dealer/office/end_user) and `chatbot_memory`
 * (one JSONB: `recall_default`, `episode_retention_days`, `profile_fields`,
 * `focus_reset_events`) are the chatbot turn re-architecture's own two additions
 * (S5, AC-1560/AC-1561) - same route, same partial-setattr path, but NOT part of
 * `ChatbotSettings`: they are their own cards with their own read/save pair,
 * kept out of the Switches card's payload (test contract: `ChatbotSettings` is
 * exactly the four switch/domain keys).
 *
 * `chatbot_stock_low_threshold_pct` (dealer stock verdict S0, D7) IS part of
 * `ChatbotSettings` - it rides the same draft/save as the switches, through the
 * `StockLowThresholdCard` on the page (no card of its own query/mutation/Save).
 */

export interface ChatbotSettings {
  chatbot_stock_denial_enabled: boolean;
  /** The business lane may RUN. Independent of it being allowed to answer. */
  chatbot_business_lane_enabled: boolean;
  /** S7 mode: the CRM orders turns per contact and owns the tail. */
  chatbot_ordering_enabled: boolean;
  chatbot_unsupported_domains: string[];
  /**
   * Dealer stock verdict S0 (D7), integer 1 to 100. Optional here on purpose: a real
   * GET always supplies it (`pickChatbotSettings` below), but the page's own tests
   * build `ChatbotSettings` objects by hand, and most of those predate this field -
   * making it required would force every one of those literals to carry a value they
   * were never meant to assert on.
   */
  chatbot_stock_low_threshold_pct?: number;
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
  chatbot_stock_denial_enabled: false,
  chatbot_business_lane_enabled: false,
  chatbot_ordering_enabled: false,
  chatbot_unsupported_domains: [],
  chatbot_stock_low_threshold_pct: 50,
};

function pickChatbotSettings(row: Record<string, unknown> | null | undefined): ChatbotSettings {
  return {
    chatbot_stock_denial_enabled: Boolean(row?.chatbot_stock_denial_enabled),
    chatbot_business_lane_enabled: Boolean(row?.chatbot_business_lane_enabled),
    chatbot_ordering_enabled: Boolean(row?.chatbot_ordering_enabled),
    chatbot_unsupported_domains: Array.isArray(row?.chatbot_unsupported_domains)
      ? (row.chatbot_unsupported_domains as string[])
      : FALLBACKS.chatbot_unsupported_domains,
    chatbot_stock_low_threshold_pct:
      typeof row?.chatbot_stock_low_threshold_pct === 'number'
        ? row.chatbot_stock_low_threshold_pct
        : FALLBACKS.chatbot_stock_low_threshold_pct,
  };
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

/** Settings > Chatbot > Memory card (chatbot turn re-architecture, AC-1513, AC-1561). */
export interface ChatbotMemorySettings {
  recall_default: boolean;
  episode_retention_days: number;
  profile_fields: string[];
  focus_reset_events: string[];
}

const MEMORY_FALLBACK: ChatbotMemorySettings = {
  recall_default: false,
  episode_retention_days: 180,
  profile_fields: ['tier', 'language', 'default_ledgers'],
  focus_reset_events: ['topic_switch'],
};

function pickChatbotMemory(row: Record<string, unknown> | null | undefined): ChatbotMemorySettings {
  const memory = row?.chatbot_memory as Partial<ChatbotMemorySettings> | null | undefined;
  if (!memory) return MEMORY_FALLBACK;
  return {
    recall_default: Boolean(memory.recall_default),
    episode_retention_days:
      typeof memory.episode_retention_days === 'number'
        ? memory.episode_retention_days
        : MEMORY_FALLBACK.episode_retention_days,
    profile_fields: Array.isArray(memory.profile_fields)
      ? memory.profile_fields
      : MEMORY_FALLBACK.profile_fields,
    focus_reset_events: Array.isArray(memory.focus_reset_events)
      ? memory.focus_reset_events
      : MEMORY_FALLBACK.focus_reset_events,
  };
}

export async function getChatbotMemorySettings(): Promise<ChatbotMemorySettings> {
  const response = await apiFetch('/api/user-management/settings');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load settings'));
  }
  const data = await response.json();
  return pickChatbotMemory(data?.settings);
}

export async function saveChatbotMemorySettings(
  input: ChatbotMemorySettings,
): Promise<ChatbotMemorySettings> {
  const response = await apiFetch('/api/user-management/settings/general', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chatbot_memory: input }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save memory settings'));
  }
  const data = await response.json();
  return pickChatbotMemory(data?.data);
}

/** Office / Dealer / End user, orderable (AC-1502's tier axis; replaces the three
 * `TIER_ORDER` code copies AC-1594 deletes). */
const TIER_ORDER_FALLBACK: string[] = ['dealer', 'office', 'end_user'];

export async function getChatbotTierOrder(): Promise<string[]> {
  const response = await apiFetch('/api/user-management/settings');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load settings'));
  }
  const data = await response.json();
  const row = data?.settings as Record<string, unknown> | null | undefined;
  return Array.isArray(row?.chatbot_tier_order)
    ? (row!.chatbot_tier_order as string[])
    : TIER_ORDER_FALLBACK;
}

export async function saveChatbotTierOrder(order: string[]): Promise<string[]> {
  const response = await apiFetch('/api/user-management/settings/general', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chatbot_tier_order: order }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save tier order'));
  }
  const data = await response.json();
  const row = data?.data as Record<string, unknown> | null | undefined;
  return Array.isArray(row?.chatbot_tier_order)
    ? (row!.chatbot_tier_order as string[])
    : TIER_ORDER_FALLBACK;
}
