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
 *
 * ---- PHASE 1 MOCK - notify_salesman / packing_list_allowed -----------------------
 * (PLAN-chatbot-stock-ask-v2-24sep.md S2, R7). Backend contract, not built yet:
 *   respond_contacts.notify_salesman        boolean NOT NULL DEFAULT false
 *   respond_contacts.packing_list_allowed   boolean NOT NULL DEFAULT false
 * Both are plain siblings of `chatbot_stock_allowed` (not nested in
 * `chatbot_profile`) and ride the same GET contact / PUT .../chatbot payload once
 * S2 lands. Until then the real contact carries neither field, so this file
 * overlays them in memory, keyed by contact id, on top of the real response -
 * enough for the two new switches to be exercised end to end. Phase 2 deletes
 * this overlay once the fields ride the real payload.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { getContact } from './contactService';

interface ContactChatbotTogglesMock {
  notify_salesman: boolean;
  packing_list_allowed: boolean;
}
const contactChatbotTogglesMock = new Map<string, ContactChatbotTogglesMock>();

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
  /** R7: the customer's sales agent gets one WhatsApp line per answered ask. Default off. */
  notify_salesman: boolean;
  /** R7: the shipment's packing list is attached on a B3 answer. Default off. */
  packing_list_allowed: boolean;
}

function fromContact(
  contact: {
    id?: string;
    chatbot_profile?: {
      tier?: string | null;
      language?: string | null;
      default_ledgers?: string[] | null;
      always_full_report?: boolean | null;
    } | null;
    chatbot_recall_enabled?: boolean;
    chatbot_stock_allowed?: boolean;
    notify_salesman?: boolean;
    packing_list_allowed?: boolean;
  },
  contactId: string,
): ContactChatbotProfile {
  const profile = contact.chatbot_profile ?? null;
  const mock = contactChatbotTogglesMock.get(contactId);
  return {
    recall_enabled: Boolean(contact.chatbot_recall_enabled),
    tier: profile?.tier ?? null,
    language: profile?.language ?? null,
    default_ledgers: profile?.default_ledgers ?? [],
    always_full_report: Boolean(profile?.always_full_report),
    stock_allowed: contact.chatbot_stock_allowed !== false,
    notify_salesman: mock?.notify_salesman ?? Boolean(contact.notify_salesman),
    packing_list_allowed: mock?.packing_list_allowed ?? Boolean(contact.packing_list_allowed),
  };
}

export async function getContactChatbotProfile(contactId: string): Promise<ContactChatbotProfile> {
  const contact = await getContact(contactId);
  return fromContact(contact, contactId);
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
      // Not read by the real route yet (Phase 1 mock, see file header).
      notify_salesman: input.notify_salesman,
      packing_list_allowed: input.packing_list_allowed,
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save chatbot settings'));
  }
  contactChatbotTogglesMock.set(contactId, {
    notify_salesman: input.notify_salesman,
    packing_list_allowed: input.packing_list_allowed,
  });
  return fromContact(await response.json(), contactId);
}
