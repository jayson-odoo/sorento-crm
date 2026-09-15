/**
 * ============================================================================
 * Contact > Access > Chatbot card - MOCK service (chatbot turn re-architecture,
 * S1, AC-1515)
 * ============================================================================
 * Layering: UI -> hooks (useContactChatbotProfile) -> THIS service -> (Phase 2:
 * lib/api-client).
 *
 * PHASE 1 - MOCKED. Swapped for the real contract in S5 (PLAN "Phase 1" note):
 *
 *   GET /api/v1/user-management/contacts/{id}/chatbot
 *   PUT /api/v1/user-management/contacts/{id}/chatbot
 *     { recall_enabled, tier, language }
 *     `tier` is READ-ONLY here once a pick has set it (`tier_set_by_pick`): the
 *     Profile shelf's writer is "explicit picks" (PLAN "Design > State"), and this
 *     card is one of those writers, but a value the CONTACT already picked in a
 *     conversation is not overwritten from here without the picture of what that
 *     changes downstream - AC-1515 asks for read-only in that case, not a second
 *     writer race.
 */

import type { NarrowingPolicy } from '@/app/(protected)/system-management/chatbot-domains/types/chatbotDomain.types';

export interface ContactChatbotProfile {
  recall_enabled: boolean;
  tier: string | null;
  /** True once a WhatsApp pick set this contact's tier - the field renders read-only. */
  tier_set_by_pick: boolean;
  tier_set_at: string | null;
  language: string | null;
  /** Read-only summary - the default ledger scope for this contact's family. */
  ledgers_summary: string;
}

const NETWORK_DELAY_MS = 150;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), NETWORK_DELAY_MS));
}

// One row per contact id, in-memory. A contact never seen before reads as the
// same defaults every fresh conversation starts from.
const PROFILES = new Map<string, ContactChatbotProfile>();

function defaults(): ContactChatbotProfile {
  return {
    recall_enabled: false,
    tier: null,
    tier_set_by_pick: false,
    tier_set_at: null,
    language: 'en',
    ledgers_summary: 'All ledgers in this contact’s family.',
  };
}

export async function getContactChatbotProfile(contactId: string): Promise<ContactChatbotProfile> {
  const row = PROFILES.get(contactId) ?? defaults();
  return delay({ ...row });
}

export async function saveContactChatbotProfile(
  contactId: string,
  input: { recall_enabled: boolean; language: string | null },
): Promise<ContactChatbotProfile> {
  const existing = PROFILES.get(contactId) ?? defaults();
  const next: ContactChatbotProfile = { ...existing, ...input };
  PROFILES.set(contactId, next);
  return delay({ ...next });
}

// Narrowing policy re-exported only so the card's docblock can point at the one
// enum the "tier" field is validated against on the real route - not used yet.
export type { NarrowingPolicy };
