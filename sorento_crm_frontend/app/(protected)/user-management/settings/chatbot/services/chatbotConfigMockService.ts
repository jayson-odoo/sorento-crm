/**
 * ============================================================================
 * Settings > Chatbot - the three new cards - MOCK service (S1, AC-1513)
 * ============================================================================
 * Layering: UI -> hooks (useChatbotConfigMock) -> THIS service -> (Phase 2: lib/api-client).
 *
 * PHASE 1 - MOCKED. The existing `chatbotSettingsService.ts` on this same page stays
 * wired to the REAL `/api/v1/user-management/settings` blob (Lanes, Switches cards);
 * this file is separate because its two fields do not exist on that model yet. Swapped
 * for the real contract in S5 (PLAN "Phase 1" note):
 *
 *   Memory card    -> settings gain `chatbot_memory` JSONB
 *     { recall_default, episode_retention_days, profile_fields, focus_reset_events }
 *   Tier order card -> settings gain `chatbot_tier_order: string[]`
 *     (replaces the three `TIER_ORDER` code copies AC-1594 deletes)
 *   Cross-domain ladder card -> the default (stock) ladder read from the "inventory"
 *     `chatbot_domains` row's own `ladder` column (same field the domain modal's
 *     Ladder tab edits) - this card is a shortcut onto that one row, not a second
 *     field. Mocked here as its own array for Phase 1; S5 wires it through
 *     `chatbotDomainService` instead of duplicating the column.
 */

const NETWORK_DELAY_MS = 150;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), NETWORK_DELAY_MS));
}

export interface ChatbotMemorySettings {
  recall_default: boolean;
  episode_retention_days: number;
  profile_fields: string[];
  focus_reset_events: string[];
}

let MEMORY_SETTINGS: ChatbotMemorySettings = {
  recall_default: false,
  episode_retention_days: 365,
  profile_fields: ['tier', 'language', 'ledgers'],
  focus_reset_events: ['topic switch', 'conversation close'],
};

let TIER_ORDER: string[] = ['Dealer', 'Office', 'End user'];

let DEFAULT_LADDER: string[] = ['incoming', 'purchase_order', 'spo_allocation'];

export async function getChatbotMemorySettings(): Promise<ChatbotMemorySettings> {
  return delay({ ...MEMORY_SETTINGS });
}

export async function saveChatbotMemorySettings(
  input: ChatbotMemorySettings,
): Promise<ChatbotMemorySettings> {
  MEMORY_SETTINGS = { ...input };
  return delay({ ...MEMORY_SETTINGS });
}

export async function getChatbotTierOrder(): Promise<string[]> {
  return delay([...TIER_ORDER]);
}

export async function saveChatbotTierOrder(order: string[]): Promise<string[]> {
  TIER_ORDER = [...order];
  return delay([...TIER_ORDER]);
}

export async function getChatbotDefaultLadder(): Promise<string[]> {
  return delay([...DEFAULT_LADDER]);
}

export async function saveChatbotDefaultLadder(order: string[]): Promise<string[]> {
  DEFAULT_LADDER = [...order];
  return delay([...DEFAULT_LADDER]);
}
