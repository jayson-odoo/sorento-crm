/** The console's Agent tab (AGENTIC-P1). Reads only; nothing reaches WhatsApp. */

export interface AgentUsage {
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  calls: number;
}

export interface AgentToolCall {
  name: string;
  status: string;
  ms: number;
}

export interface AgentTurnResponse {
  turn_id: string;
  conversation_id: string;
  reply_text: string;
  status: 'answered' | 'limited' | 'failed';
  limit_hit: 'rounds' | 'seconds' | 'input_tokens' | 'error' | null;
  rounds: number;
  usage: AgentUsage;
  tool_calls: AgentToolCall[];
}

export interface AgentConversationTurn {
  turn_id: string;
  text: string;
  reply_text: string;
  status: string;
  created_at: string;
  /** Absent on a turn stored before rounds were kept. */
  rounds?: number | null;
  limit_hit?: AgentTurnResponse['limit_hit'];
  tool_calls?: { name: string; status: string }[];
}

export interface AgentConversationResponse {
  /** Null until the first turn: reading a conversation never creates one. */
  conversation_id: string | null;
  turns: AgentConversationTurn[];
}

/** What a finished turn shows under its reply. Only turns run in this visit carry it. */
export interface AgentReplyMeta {
  rounds: number | null;
  tool_calls: { name: string; status: string }[];
  limit_hit: AgentTurnResponse['limit_hit'];
}

export type AgentRefusalReason =
  | 'contact_not_found'
  | 'ai_replies_off'
  | 'switch_off'
  | 'no_linked_user';

export const AGENT_REFUSAL_MESSAGES: Record<string, string> = {
  switch_off: 'Agent mode is off for this contact (Contact Details > Chatbot).',
  no_linked_user: 'This contact has no linked active user.',
  ai_replies_off: 'AI replies are off for this contact.',
  contact_not_found: 'This contact was not found.',
  agent_busy: 'The agent is still working on another message for this contact.',
};

export const AGENT_TOOL_LABELS: Record<string, string> = {
  crm_report_ask: 'Sales report',
  crm_inventory_stock_balance_list: 'Stock balance',
  crm_incoming_stock_by_product: 'Incoming stock by product',
  crm_incoming_stock_shipments: 'Incoming shipments',
  crm_procurement_grn_summary: 'Goods received',
  crm_procurement_po_last_cost_list: 'Last cost',
  crm_procurement_po_placed_list: 'Purchase orders placed',
  crm_procurement_spo_allocations_last_receipt_list: 'Last receipt',
  crm_order_management_orders_by_product_list: 'Orders by product',
  crm_resolve: 'Find names and codes',
  crm_products_find: 'Find products',
};

export const AGENT_LIMIT_LABELS: Record<string, string> = {
  rounds: 'rounds limit',
  seconds: 'time limit',
  input_tokens: 'token limit',
  error: 'an error',
};

/** The tools that plan and end a turn: not lookups, so they get no chip. */
export const AGENT_HIDDEN_TOOLS = new Set(['answer', 'plan']);

export function agentToolLabel(name: string): string {
  return AGENT_TOOL_LABELS[name] ?? name.replace(/^crm_/, '').replace(/_/g, ' ');
}
