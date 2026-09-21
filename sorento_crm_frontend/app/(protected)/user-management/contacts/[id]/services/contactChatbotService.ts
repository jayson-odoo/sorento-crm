/**
 * ============================================================================
 * Contact > Access > Chatbot card (chatbot turn re-architecture, S5, AC-1560/AC-1561)
 * ============================================================================
 * Layering: UI -> hooks (useContactChatbotProfile) -> THIS service -> lib/api -> backend.
 *
 *   GET /api/v1/user-management/contacts/{id}          the contact record already
 *     carries `chatbot_profile` / `chatbot_recall_enabled` (AC-1503, both dict
 *     builders) - no dedicated GET route exists for the card alone.
 *   PUT /api/v1/user-management/contacts/{id}/chatbot
 *     { chatbot_profile?, chatbot_recall_enabled?, chatbot_stock_allowed? }
 *     Absent means "leave it alone", never "clear it" - a recall toggle must not
 *     switch off as a side effect of saving a language.
 *
 * The mocked S1 shape (`tier_set_by_pick`, `tier_set_at`, `ledgers_summary`) does not
 * exist on the real contact - the backend has no signal distinguishing a value a pick
 * set from one typed here, so `tier` is edited directly like `language`, same as every
 * other profile field on this card.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { getContact } from './contactService';

export interface ContactChatbotProfile {
  recall_enabled: boolean;
  tier: string | null;
  language: string | null;
  default_ledgers: string[];
  /** Not edited on this card - carried through unchanged so a save from here never
   * clears it (the PUT route replaces the whole `chatbot_profile` dict, not a merge). */
  always_full_report: boolean;
  /** S6: stock checks allowed for this contact (`chatbot_stock_allowed`), default on. */
  stock_allowed: boolean;
}

function fromContact(contact: {
  chatbot_profile?: {
    tier?: string | null;
    language?: string | null;
    default_ledgers?: string[] | null;
    always_full_report?: boolean | null;
  } | null;
  chatbot_recall_enabled?: boolean;
  chatbot_stock_allowed?: boolean;
}): ContactChatbotProfile {
  const profile = contact.chatbot_profile ?? null;
  return {
    recall_enabled: Boolean(contact.chatbot_recall_enabled),
    tier: profile?.tier ?? null,
    language: profile?.language ?? null,
    default_ledgers: profile?.default_ledgers ?? [],
    always_full_report: Boolean(profile?.always_full_report),
    stock_allowed: contact.chatbot_stock_allowed !== false,
  };
}

export async function getContactChatbotProfile(contactId: string): Promise<ContactChatbotProfile> {
  const contact = await getContact(contactId);
  return fromContact(contact);
}

export type ContactChatbotSaveInput = ContactChatbotProfile;

export async function saveContactChatbotProfile(
  contactId: string,
  input: ContactChatbotSaveInput,
): Promise<ContactChatbotProfile> {
  const response = await apiFetch(`/api/v1/user-management/contacts/${contactId}/chatbot`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      // The route replaces the whole `chatbot_profile` dict (never a merge), so every
      // field the contact already had is sent back, not just the one edited here.
      chatbot_profile: {
        tier: input.tier,
        language: input.language,
        default_ledgers: input.default_ledgers,
        always_full_report: input.always_full_report,
      },
      chatbot_recall_enabled: input.recall_enabled,
      chatbot_stock_allowed: input.stock_allowed,
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save chatbot settings'));
  }
  return fromContact(await response.json());
}
