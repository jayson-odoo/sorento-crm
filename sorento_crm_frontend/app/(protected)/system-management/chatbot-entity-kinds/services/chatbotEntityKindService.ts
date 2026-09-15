/**
 * ============================================================================
 * Chatbot Entity kinds - MOCK service (chatbot turn re-architecture, S1, AC-1512)
 * ============================================================================
 * Layering: UI -> hooks (useChatbotEntityKinds) -> THIS service -> (Phase 2: lib/api-client).
 *
 * PHASE 1 - MOCKED. Swapped for the real API contract in S5 (AC-1560):
 *
 *   GET  /api/v1/system/chatbot/entity-kinds            list, `system.chat_history.view`
 *   POST /api/v1/system/chatbot/entity-kinds             create, `system.chatbot_config.manage`
 *   PUT  /api/v1/system/chatbot/entity-kinds/{code}       update, `system.chatbot_config.manage`
 *
 * No delete route in this contract: an entity kind is code, not data an operator adds
 * and removes day to day (UAC AC-1512 does not ask for one, unlike domains' AC-1511).
 */

import type { ChatbotEntityKind, ChatbotEntityKindInput } from '../types/chatbotEntityKind.types';

const NETWORK_DELAY_MS = 150;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), NETWORK_DELAY_MS));
}

function seed(): ChatbotEntityKind[] {
  const now = new Date().toISOString();
  const row = (partial: ChatbotEntityKindInput): ChatbotEntityKind => ({ ...partial, updated_at: now });
  return [
    row({
      code: 'product',
      label: 'Product',
      resolved_against: 'Master products (code, name, set members)',
      did_you_mean: true,
      default_narrowing: 'list_all',
      family_grouping: 'by base code',
      base_property_words: [
        'price',
        'list price',
        'harga',
        'cost',
        'dimensions',
        'size',
        'description',
        'name',
        'discontinued',
        'brand',
      ],
    }),
    row({
      code: 'customer',
      label: 'Customer',
      resolved_against: 'Customers (name, debtor code, ledgers)',
      did_you_mean: true,
      default_narrowing: 'must_narrow_one',
      family_grouping: 'by ledger family',
      base_property_words: [],
    }),
    row({
      code: 'warehouse',
      label: 'Warehouse',
      resolved_against: 'Warehouses and locations',
      did_you_mean: true,
      default_narrowing: 'optional_filter',
      family_grouping: null,
      base_property_words: [],
    }),
    row({
      code: 'transporter',
      label: 'Transporter',
      resolved_against: 'Transporters',
      did_you_mean: true,
      default_narrowing: 'optional_filter',
      family_grouping: null,
      base_property_words: [],
    }),
    row({
      code: 'attachment_type',
      label: 'Attachment type',
      resolved_against: 'Attachment types',
      did_you_mean: true,
      default_narrowing: 'narrow_by_type',
      family_grouping: null,
      base_property_words: [],
    }),
    row({
      code: 'brand',
      label: 'Brand',
      resolved_against: 'Brands',
      did_you_mean: true,
      default_narrowing: 'optional_filter',
      family_grouping: null,
      base_property_words: [],
    }),
    row({
      code: 'tier',
      label: 'Tier',
      resolved_against: 'Office / Dealer / End user (order on Settings > Chatbot)',
      did_you_mean: false,
      default_narrowing: 'narrow_by_tier',
      family_grouping: null,
      base_property_words: [],
    }),
  ];
}

let ENTITY_KINDS: ChatbotEntityKind[] = seed();

export async function listChatbotEntityKinds(): Promise<ChatbotEntityKind[]> {
  return delay([...ENTITY_KINDS]);
}

export async function getChatbotEntityKind(code: string): Promise<ChatbotEntityKind | undefined> {
  return delay(ENTITY_KINDS.find((k) => k.code === code));
}

export async function createChatbotEntityKind(
  input: ChatbotEntityKindInput,
): Promise<ChatbotEntityKind> {
  const row: ChatbotEntityKind = { ...input, updated_at: new Date().toISOString() };
  ENTITY_KINDS = [...ENTITY_KINDS, row];
  return delay(row);
}

export async function updateChatbotEntityKind(
  code: string,
  input: ChatbotEntityKindInput,
): Promise<ChatbotEntityKind> {
  const row: ChatbotEntityKind = { ...input, code, updated_at: new Date().toISOString() };
  ENTITY_KINDS = ENTITY_KINDS.map((k) => (k.code === code ? row : k));
  return delay(row);
}
