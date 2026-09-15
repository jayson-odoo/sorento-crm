/**
 * ============================================================================
 * Chatbot Domains - MOCK service (chatbot turn re-architecture, S1, AC-1510/1511)
 * ============================================================================
 * Layering: UI -> hooks (useChatbotDomains) -> THIS service -> (Phase 2: lib/api-client).
 *
 * PHASE 1 - MOCKED. No backend route exists yet; every export below resolves
 * against an in-memory array. Swapped for real `fetch` calls against the API
 * contract in S5 (AC-1560), which is:
 *
 *   GET    /api/v1/system/chatbot/domains            list, `system.chat_history.view`
 *   GET    /api/v1/system/chatbot/domains/{id}        one row
 *   POST   /api/v1/system/chatbot/domains             create, `system.chatbot_config.manage`
 *   PUT    /api/v1/system/chatbot/domains/{id}         update, `system.chatbot_config.manage`
 *   DELETE /api/v1/system/chatbot/domains/{id}         deferred (D7): parks a pending action,
 *                                                       the generic `/api/v1/pending-actions`
 *                                                       contract with `action_key`
 *                                                       "chatbot_domain.delete" (AC-1561).
 *
 * The deferred-delete countdown below is a CLIENT-ONLY simulation of that contract's
 * shape (`{ id, commit_at, window_seconds }`, same as `services/pendingActionService`)
 * so the real `DeferredCountdown` presentational component can render it unchanged.
 * It does not survive a reload - the real park/cancel/commit lives on the server from
 * S5 onward, via the shared `useDeferredRowAction` hook other lists already use.
 */

import type { ChatbotDomain, ChatbotDomainInput } from '../types/chatbotDomain.types';

const NETWORK_DELAY_MS = 150;
/** D7's hard-delete grace window (10s), mirrored here since Phase 1 has no
 * System Settings row to read `record_action_window_seconds` from yet. */
export const DELETE_WINDOW_SECONDS = 10;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), NETWORK_DELAY_MS));
}

function seed(): ChatbotDomain[] {
  const now = new Date().toISOString();
  const row = (partial: Omit<ChatbotDomain, 'id' | 'updated_at'>): ChatbotDomain => ({
    id: `dom-${partial.name}`,
    updated_at: now,
    ...partial,
  });
  return [
    row({
      name: 'inventory',
      label: 'Stock',
      intents: ['check_stock'],
      tools: ['crm_inventory_stock_balance_list', 'crm_inventory_warehouses_list'],
      primary_tool: 'crm_inventory_stock_balance_list',
      escalation_team_code: 'warehouse',
      switch_words: ['stock', 'stok'],
      narrowing: { product: 'list_all', warehouse: 'optional_filter' },
      takes_date_filter: false,
      reveal_key: null,
      supported: true,
      ladder: ['incoming', 'purchase_order', 'spo_allocation'],
    }),
    row({
      name: 'incoming',
      label: 'Incoming',
      intents: ['check_incoming', 'check_eta'],
      tools: [
        'crm_incoming_stock_list',
        'crm_incoming_stock_by_product',
        'crm_incoming_stock_shipments',
      ],
      primary_tool: 'crm_incoming_stock_list',
      escalation_team_code: 'purchasing',
      switch_words: ['incoming', 'eta', 'container', 'masuk'],
      narrowing: {
        product: 'narrow_to_code',
        warehouse: 'optional_filter',
        transporter: 'optional_filter',
        customer: 'not_applicable',
      },
      takes_date_filter: true,
      reveal_key: null,
      supported: true,
      ladder: [],
    }),
    row({
      name: 'purchase_order',
      label: 'Outstanding PO',
      intents: ['check_po'],
      tools: ['crm_po_placed_list'],
      primary_tool: 'crm_po_placed_list',
      escalation_team_code: 'purchasing',
      switch_words: ['po'],
      narrowing: { product: 'narrow_to_code' },
      takes_date_filter: true,
      reveal_key: null,
      supported: true,
      ladder: [],
    }),
    row({
      name: 'purchase_cost',
      label: 'Last purchase cost',
      intents: ['check_last_cost'],
      tools: ['crm_po_last_cost_list'],
      primary_tool: 'crm_po_last_cost_list',
      escalation_team_code: 'purchasing',
      switch_words: [],
      narrowing: { product: 'narrow_to_code' },
      takes_date_filter: true,
      reveal_key: 'last_purchase_cost',
      supported: true,
      ladder: [],
    }),
    row({
      name: 'spo_allocation',
      label: 'Last in',
      intents: ['check_last_in'],
      tools: ['crm_spo_allocations_last_receipt_list'],
      primary_tool: 'crm_spo_allocations_last_receipt_list',
      escalation_team_code: 'purchasing',
      switch_words: ['spo', 'last in'],
      narrowing: { product: 'narrow_to_code' },
      takes_date_filter: true,
      reveal_key: null,
      supported: true,
      ladder: [],
    }),
    row({
      name: 'master_products',
      label: 'Product info',
      intents: ['check_product_info'],
      tools: ['crm_master_products_list', 'crm_brands_list', 'crm_categories_list', 'crm_uom_list'],
      primary_tool: 'crm_master_products_list',
      escalation_team_code: 'marketing_product',
      switch_words: ['price', 'spec', 'discontinued'],
      narrowing: { product: 'list_all' },
      takes_date_filter: false,
      reveal_key: null,
      supported: true,
      ladder: [],
    }),
    row({
      name: 'product_attachment',
      label: 'Photos and files',
      intents: ['check_attachments'],
      tools: ['crm_product_attachments_list', 'crm_certificates_list'],
      primary_tool: 'crm_product_attachments_list',
      escalation_team_code: 'marketing_product',
      switch_words: ['photo', 'drawing', 'manual', 'cert'],
      narrowing: { product: 'list_all', attachment_type: 'narrow_by_type' },
      takes_date_filter: false,
      reveal_key: null,
      supported: true,
      ladder: [],
    }),
    row({
      name: 'promotion',
      label: 'Promotions',
      intents: ['check_promotions'],
      tools: ['crm_promotions_list', 'crm_promotion_attachments', 'crm_promotion_products'],
      primary_tool: 'crm_promotions_list',
      escalation_team_code: 'marketing_promotion',
      switch_words: ['promo', 'promosi'],
      narrowing: { tier: 'narrow_by_tier' },
      takes_date_filter: true,
      reveal_key: null,
      supported: true,
      ladder: [],
    }),
    row({
      name: 'order',
      label: 'Orders and DO',
      intents: ['check_order', 'check_delivery'],
      tools: [
        'crm_outstanding_report',
        'crm_orders_list',
        'crm_orders_by_product',
        'crm_customers_list',
      ],
      primary_tool: 'crm_outstanding_report',
      escalation_team_code: 'customer_service',
      switch_words: ['order', 'outstanding', 'delivery', 'hantar'],
      narrowing: { customer: 'must_narrow_one', product: 'list_all' },
      takes_date_filter: true,
      reveal_key: null,
      supported: true,
      ladder: [],
    }),
    row({
      name: 'goods_receive',
      label: 'Goods receive',
      intents: [],
      tools: [],
      primary_tool: null,
      escalation_team_code: 'warehouse',
      switch_words: ['grn'],
      narrowing: {},
      takes_date_filter: false,
      reveal_key: null,
      supported: false,
      ladder: [],
    }),
  ];
}

let DOMAINS: ChatbotDomain[] = seed();

/** Shape-compatible with `services/pendingActionService`'s `PendingAction`, mocked. */
export interface MockPendingAction {
  id: string;
  action_key: string;
  entity_type: string;
  entity_id: string;
  commit_at: string;
  window_seconds: number;
}

const pendingDeletes = new Map<string, MockPendingAction>();

export function getPendingChatbotDomainDelete(domainId: string): MockPendingAction | null {
  return pendingDeletes.get(domainId) ?? null;
}

export async function listChatbotDomains(): Promise<ChatbotDomain[]> {
  return delay([...DOMAINS]);
}

export async function getChatbotDomain(id: string): Promise<ChatbotDomain | undefined> {
  return delay(DOMAINS.find((d) => d.id === id));
}

export async function createChatbotDomain(input: ChatbotDomainInput): Promise<ChatbotDomain> {
  const row: ChatbotDomain = {
    ...input,
    id: `dom-${input.name || Math.random().toString(36).slice(2, 8)}`,
    updated_at: new Date().toISOString(),
  };
  DOMAINS = [...DOMAINS, row];
  return delay(row);
}

export async function updateChatbotDomain(
  id: string,
  input: ChatbotDomainInput,
): Promise<ChatbotDomain> {
  const row: ChatbotDomain = { ...input, id, updated_at: new Date().toISOString() };
  DOMAINS = DOMAINS.map((d) => (d.id === id ? row : d));
  return delay(row);
}

/**
 * Park a delete for `DELETE_WINDOW_SECONDS` (D7's 10s hard-delete window). The row is
 * only actually removed once the window lapses - cancel before then and nothing changes.
 */
export async function parkChatbotDomainDelete(id: string): Promise<MockPendingAction> {
  const existing = pendingDeletes.get(id);
  if (existing) return delay(existing);

  const commitAt = new Date(Date.now() + DELETE_WINDOW_SECONDS * 1000);
  const action: MockPendingAction = {
    id: `pending-${id}`,
    action_key: 'chatbot_domain.delete',
    entity_type: 'chatbot_domain',
    entity_id: id,
    commit_at: commitAt.toISOString(),
    window_seconds: DELETE_WINDOW_SECONDS,
  };
  pendingDeletes.set(id, action);
  // The lapse itself is the caller's job (`useChatbotDomainDeletion` times it against
  // this same window and then refetches) - this mock only needs to stop offering the
  // row back to `getChatbotDomain`/`listChatbotDomains` once the window is over.
  setTimeout(() => {
    if (pendingDeletes.get(id)?.id !== action.id) return; // cancelled and re-parked since
    DOMAINS = DOMAINS.filter((d) => d.id !== id);
    pendingDeletes.delete(id);
  }, DELETE_WINDOW_SECONDS * 1000);
  return delay(action);
}

export async function cancelChatbotDomainDelete(id: string): Promise<void> {
  pendingDeletes.delete(id);
  return delay(undefined);
}
