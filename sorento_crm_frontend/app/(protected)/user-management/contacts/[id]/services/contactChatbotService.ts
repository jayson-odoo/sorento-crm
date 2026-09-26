/**
 * ============================================================================
 * Contact > Chatbot (chatbot memory lane A, round 3 mockup)
 * ============================================================================
 * Layering: UI -> hooks (`useContactChatbot.ts`) -> THIS service -> lib/api -> backend.
 *
 * Mockup: `documentation/plans/chatbot/chatbot-memory-27sep-mockup-contact.html`.
 * Contract: `documentation/plans/chatbot/chatbot-memory-lane-a-contract.md` sections
 * 4 (profile facts) and 5 (HTTP contract).
 *
 * ---------------------------------------------------------------------------
 * THE CONTRACT (Phase 2 wires this exactly - see the PHASE-1 MOCK markers below)
 * ---------------------------------------------------------------------------
 *
 * GET  /api/v1/user-management/contacts/{id}                       -> RespondContact
 * PUT  /api/v1/user-management/contacts/{id}/chatbot
 *   { chatbot_profile?: { tier, default_ledgers }, chatbot_memory_level?: ChatbotMemoryLevel
 *     | null, chatbot_stock_allowed?, notify_salesman?, packing_list_allowed? }
 *   Both gain `chatbot_memory_level` and drop `chatbot_recall_enabled`; `chatbot_profile`
 *   in the body never touches `facts`. Absent means "leave it alone", never "clear it".
 *
 * GET    /api/v1/user-management/contacts/{id}/chatbot/memory  (`...contacts.view`)
 *   -> ContactChatbotMemory (below), the exact shape contract section 5 documents.
 * PUT    /api/v1/user-management/contacts/{id}/chatbot/facts/{key}  (`...contacts.edit`)
 *   body `{ value: string | string[] }` -> sets a staff fact, returns the memory GET body.
 * DELETE /api/v1/user-management/contacts/{id}/chatbot/facts/{key}  (`...contacts.edit`)
 *   Hard delete through the deferred-action path (the FE fires it when the countdown
 *   lapses, same mechanism every other delete uses) -> 204.
 */

import { getProductsForLineSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import { getBrands } from '@/app/(protected)/master-data-management/brands/services/brandService';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import type { SearchableMultiSelectOption } from '@/components/common/SearchableMultiSelect';

export type ChatbotMemoryLevel = 'off' | 'conversation' | 'past' | 'full';

export interface ContactChatbotProfile {
  /** null = follow the system default (contract section 2). */
  chatbot_memory_level: ChatbotMemoryLevel | null;
  tier: string | null;
  /** Not edited on this card - carried through unchanged so a save never clears it. */
  default_ledgers: string[];
  /** S6: stock checks allowed for this contact (`chatbot_stock_allowed`), default on. */
  stock_allowed: boolean;
  /** R7: the customer's sales agent gets one WhatsApp line per answered ask. Default off. */
  notify_salesman: boolean;
  /** R7: the shipment's packing list is attached on a B3 answer. Default off. */
  packing_list_allowed: boolean;
}

export type ChatbotFactSource = 'crm' | 'tallied' | 'stated' | 'staff';

export interface ContactChatbotFact {
  key: string;
  label: string;
  value: string | null;
  source: ChatbotFactSource;
  /** ISO date, or null for a fact read live from the CRM (contract section 5). */
  last_seen: string | null;
  editable: boolean;
  /** Set only on a CRM fact whose source record has its own page (e.g. `customer`). */
  link?: string | null;
}

export type ChatbotVocabularyKind = 'choice' | 'multi' | 'text';

export interface ContactChatbotVocabularyEntry {
  key: string;
  label: string;
  kind: ChatbotVocabularyKind;
  options: { value: string; label: string }[] | null;
  max_length: number | null;
}

export interface ContactChatbotEpisodeCurrent {
  turn_count: number;
  first_turn_id: string;
  started_at: string;
  summary: string;
  domains: string[];
}

export interface ContactChatbotEpisodeRow {
  id: string;
  date: string;
  domains: string[];
  summary: string;
  turn_count: number;
  close_reason: string;
  first_turn_id: string;
}

export interface ContactChatbotOpenOrderRow {
  document: string;
  kind: string;
  status: string;
  summary: string;
  date: string;
  href: string;
}

export interface ContactChatbotMemory {
  level: {
    own: ChatbotMemoryLevel | null;
    effective: ChatbotMemoryLevel;
    system_default: ChatbotMemoryLevel;
  };
  facts: ContactChatbotFact[];
  vocabulary: ContactChatbotVocabularyEntry[];
  episodes: {
    kept: number;
    limit: number;
    current: ContactChatbotEpisodeCurrent | null;
    rows: ContactChatbotEpisodeRow[];
  };
  open_orders: {
    customer_name: string | null;
    rows: ContactChatbotOpenOrderRow[];
  };
}

/* ============================================================================
 * PHASE-1 MOCK: swap for apiFetch in Phase 2, once the S0 migration lands
 * `chatbot_memory_level`, `chatbot_profile.facts`, `conversation_frames.is_test` and the
 * memory/facts routes (contract section 5). One in-memory record per contact id, seeded
 * with the round 3 mockup's sample (Tan Wei Liang / Chin Chun Trading, CC001) - the
 * settings card and the memory read share the SAME record, so editing the level in one
 * place is reflected in the other, exactly as the real GET/PUT and GET .../memory will
 * once they read the same `respond_contacts` row.
 * ========================================================================== */

interface MockFactEntry {
  value: string | string[];
  source: ChatbotFactSource;
  lastSeen: string | null;
}

type FactKind = 'readonly' | ChatbotVocabularyKind;

interface FactCatalogEntry {
  key: string;
  label: string;
  kind: FactKind;
  options?: { value: string; label: string }[];
  maxLength?: number | null;
}

/** Contract section 4's field table, minus `customer` and `salesperson` (read-only, no
 * staff input - excluded from `vocabulary`, added to `facts` directly from the mock's
 * CRM-side sample). */
const FACT_CATALOG: FactCatalogEntry[] = [
  {
    key: 'segment',
    label: 'Segment',
    kind: 'choice',
    options: [
      { value: 'dealer', label: 'Dealer' },
      { value: 'project', label: 'Project' },
      { value: 'end_user', label: 'End user' },
    ],
  },
  {
    key: 'language',
    label: 'Language',
    kind: 'choice',
    options: [
      { value: 'en', label: 'English' },
      { value: 'ms', label: 'Malay' },
      { value: 'zh', label: 'Chinese' },
    ],
  },
  {
    key: 'role',
    label: 'Role',
    kind: 'choice',
    options: [
      { value: 'purchaser', label: 'Purchaser' },
      { value: 'owner', label: 'Owner' },
      { value: 'sales', label: 'Sales' },
      { value: 'site_supervisor', label: 'Site supervisor' },
      { value: 'other', label: 'Other' },
    ],
  },
  { key: 'usual_products', label: 'Usual products', kind: 'multi' },
  { key: 'usual_brands', label: 'Usual brands', kind: 'multi' },
  { key: 'usual_sites', label: 'Usual sites', kind: 'multi' },
  { key: 'project', label: 'Project', kind: 'text', maxLength: 60 },
  { key: 'about', label: 'About', kind: 'text', maxLength: 200 },
  { key: 'note', label: 'Note', kind: 'text', maxLength: 200 },
];

function catalogEntry(key: string): FactCatalogEntry | undefined {
  return FACT_CATALOG.find((entry) => entry.key === key);
}

interface MockContactState {
  profile: ContactChatbotProfile;
  systemDefaultLevel: ChatbotMemoryLevel;
  customerName: string;
  customerLink: string;
  facts: Record<string, MockFactEntry>;
  episodesCurrent: ContactChatbotEpisodeCurrent | null;
  episodeRows: ContactChatbotEpisodeRow[];
  openOrders: ContactChatbotOpenOrderRow[];
}

function seedState(): MockContactState {
  return {
    profile: {
      chatbot_memory_level: 'full',
      tier: 'dealer',
      default_ledgers: [],
      stock_allowed: true,
      notify_salesman: true,
      packing_list_allowed: false,
    },
    systemDefaultLevel: 'off',
    customerName: 'Chin Chun Trading',
    customerLink: '/order-management/customers/cc001',
    facts: {
      segment: { value: 'dealer', source: 'crm', lastSeen: null },
      role: { value: 'purchaser', source: 'stated', lastSeen: '2026-09-26' },
      language: { value: 'ms', source: 'stated', lastSeen: '2026-09-26' },
      usual_products: { value: ['SRTWB1455', 'M486-75-BL'], source: 'tallied', lastSeen: '2026-09-25' },
      usual_sites: { value: ['Kuching'], source: 'tallied', lastSeen: '2026-09-25' },
      project: { value: 'Aurora Residences block B', source: 'stated', lastSeen: '2026-09-24' },
      about: { value: ['Runs 3 shops in Kuching and Sibu'], source: 'stated', lastSeen: '2026-09-22' },
      note: { value: 'Prefers PDF quotes', source: 'staff', lastSeen: '2026-09-20' },
    },
    episodesCurrent: {
      turn_count: 2,
      first_turn_id: 'ZZT-turn-current',
      started_at: '2026-09-26T02:00:00',
      summary: 'stock SRTWB1455; and in kuching?',
      domains: ['stock'],
    },
    episodeRows: [
      {
        id: 'ep-1',
        date: '2026-09-25T02:10:00',
        domains: ['stock', 'incoming'],
        summary:
          'stock SRTWB1455 (answered); incoming M486-75-BL (not found); offered Stock team, declined.',
        turn_count: 5,
        close_reason: 'topic_switch',
        first_turn_id: 'ZZT-turn-ep-1',
      },
      {
        id: 'ep-2',
        date: '2026-09-23T09:40:00',
        domains: ['orders'],
        summary: 'outstanding DO for CC001 Chin Chun Trading (answered).',
        turn_count: 3,
        close_reason: 'topic_switch',
        first_turn_id: 'ZZT-turn-ep-2',
      },
      {
        id: 'ep-3',
        date: '2026-09-19T14:05:00',
        domains: ['stock'],
        summary: 'stock M483-BL (answered); small talk.',
        turn_count: 4,
        close_reason: 'topic_switch',
        first_turn_id: 'ZZT-turn-ep-3',
      },
    ],
    openOrders: [
      {
        document: 'SO-2409-0112',
        kind: 'sales_order',
        status: 'Confirmed',
        summary: '3 lines',
        date: '2026-09-18',
        href: '/scm/sales-orders/so-2409-0112',
      },
      {
        document: 'DO-2409-0087',
        kind: 'delivery_order',
        status: 'Outstanding',
        summary: '2 lines to Kuching',
        date: '2026-09-20',
        href: '/scm/delivery-orders/do-2409-0087',
      },
    ],
  };
}

const MOCK_STATE = new Map<string, MockContactState>();

function stateFor(contactId: string): MockContactState {
  let state = MOCK_STATE.get(contactId);
  if (!state) {
    state = seedState();
    MOCK_STATE.set(contactId, state);
  }
  return state;
}

function optionLabel(entry: FactCatalogEntry, raw: string): string {
  return entry.options?.find((option) => option.value === raw)?.label ?? raw;
}

function displayValue(entry: FactCatalogEntry, raw: string | string[]): string {
  return Array.isArray(raw)
    ? raw.map((item) => optionLabel(entry, item)).join(', ')
    : optionLabel(entry, raw);
}

function buildFacts(state: MockContactState): ContactChatbotFact[] {
  const rows: ContactChatbotFact[] = [
    {
      key: 'customer',
      label: 'Customer',
      value: `${state.customerName} (CC001)`,
      source: 'crm',
      last_seen: null,
      editable: false,
      link: state.customerLink,
    },
  ];

  const segment = state.facts.segment;
  const segmentEntry = catalogEntry('segment')!;
  rows.push({
    key: 'segment',
    label: 'Segment',
    value: segment ? displayValue(segmentEntry, segment.value) : null,
    source: segment?.source ?? 'crm',
    last_seen: segment?.lastSeen ?? null,
    editable: true,
  });

  rows.push({
    key: 'salesperson',
    label: 'Salesperson',
    value: 'Aina Rahman',
    source: 'crm',
    last_seen: null,
    editable: false,
  });

  for (const entry of FACT_CATALOG) {
    if (entry.key === 'segment') continue;
    const fact = state.facts[entry.key];
    // One entry per key that actually has a value (contract section 4) - a vocabulary
    // key nobody has learned/said/set yet is offered only through "+ Add".
    if (!fact) continue;
    rows.push({
      key: entry.key,
      label: entry.label,
      value: displayValue(entry, fact.value),
      source: fact.source,
      last_seen: fact.lastSeen,
      editable: true,
    });
  }

  return rows;
}

function buildVocabulary(): ContactChatbotVocabularyEntry[] {
  return FACT_CATALOG.map((entry) => ({
    key: entry.key,
    label: entry.label,
    kind: entry.kind as ChatbotVocabularyKind,
    options: entry.options ? entry.options.map((option) => ({ ...option })) : null,
    max_length: entry.maxLength ?? null,
  }));
}

function toMemory(state: MockContactState): ContactChatbotMemory {
  const own = state.profile.chatbot_memory_level;
  return {
    level: {
      own,
      effective: own ?? state.systemDefaultLevel,
      system_default: state.systemDefaultLevel,
    },
    facts: buildFacts(state),
    vocabulary: buildVocabulary(),
    episodes: {
      kept: state.episodeRows.length,
      limit: 20,
      current: state.episodesCurrent,
      rows: state.episodeRows,
    },
    open_orders: { customer_name: state.customerName, rows: state.openOrders },
  };
}

export type ContactChatbotSaveInput = ContactChatbotProfile;

export async function getContactChatbotProfile(contactId: string): Promise<ContactChatbotProfile> {
  return { ...stateFor(contactId).profile };
}

export async function saveContactChatbotProfile(
  contactId: string,
  input: ContactChatbotSaveInput,
): Promise<ContactChatbotProfile> {
  const state = stateFor(contactId);
  state.profile = { ...input };
  return { ...state.profile };
}

export async function getContactChatbotMemory(contactId: string): Promise<ContactChatbotMemory> {
  return toMemory(stateFor(contactId));
}

/** `PUT .../chatbot/facts/{key}` - sets a staff fact; every save makes the fact Staff,
 * even one that replaces a Learned or Said value (contract section 4). */
export async function saveContactFact(
  contactId: string,
  key: string,
  value: string | string[],
): Promise<ContactChatbotMemory> {
  const entry = catalogEntry(key);
  if (!entry) {
    throw new Error(`"${key}" is not an editable fact.`);
  }
  const state = stateFor(contactId);
  state.facts[key] = {
    value,
    source: 'staff',
    lastSeen: new Date().toISOString().slice(0, 10),
  };
  return toMemory(state);
}

/**
 * Best-effort local removal once the deferred delete commits.
 *
 * The real `DELETE .../chatbot/facts/{key}` runs server-side, through the same
 * pending-action commit every other delete uses (contract section 5) - this mock has no
 * server to commit against, so `useContactChatbotMemory`'s `onCommitted` callback calls
 * this directly so the row still disappears once the countdown lapses.
 */
export function forgetContactFactMock(contactId: string, key: string): void {
  delete stateFor(contactId).facts[key];
}

/* ============================================================================
 * end PHASE-1 MOCK
 * ========================================================================== */

/**
 * Server-searched product options for the "Usual products" fact (Add fact modal).
 *
 * Real endpoint, not a mock (`/api/v1/master-data/products/select`, LESSONS-LEARNT: a
 * static option list does not scale to the product catalog) - product codes double as
 * the human-readable value the fact stores, so no id/label split is needed.
 */
export async function searchUsualProductOptions(query: string): Promise<SearchableMultiSelectOption[]> {
  const products = await getProductsForLineSelect(query);
  return products.map((product) => ({
    value: product.product_code,
    label: product.product_name
      ? `${product.product_code} - ${product.product_name}`
      : product.product_code,
  }));
}

/** Server-searched brand names for "Usual brands" - stored as the brand NAME, not an id
 * (contract section 4: "list of brand names"). */
export async function searchUsualBrandOptions(query: string): Promise<SearchableMultiSelectOption[]> {
  const result = await getBrands({ pageIndex: 0, pageSize: 20, sorting: [], searchQuery: query });
  return result.data.map((brand) => ({ value: brand.brand_name, label: brand.brand_name }));
}

/** Server-searched warehouse names for "Usual sites" - stored as the warehouse NAME
 * (contract section 4: "list of warehouse names"). */
export async function searchUsualSiteOptions(query: string): Promise<SearchableMultiSelectOption[]> {
  const result = await getWarehouses({ pageIndex: 0, pageSize: 20, sorting: [], searchQuery: query });
  return result.data
    .filter((warehouse) => warehouse.warehouse_name)
    .map((warehouse) => ({
      value: warehouse.warehouse_name as string,
      label: warehouse.warehouse_name as string,
    }));
}
