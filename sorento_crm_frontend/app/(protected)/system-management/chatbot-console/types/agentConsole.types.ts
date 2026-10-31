/** The console's Agent tab (AGENTIC-P1, writes AGENTIC-P3). Nothing reaches WhatsApp; a write
 * runs only after the user confirms its proposal. */

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
  /** The call in plain words (what it was for, with what, how it ended); absent on an older turn. */
  detail?: string;
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
  steps?: AgentSteps;
  pending_action?: AgentPendingAction | null;
}

/** Changes a turn proposed, waiting for Confirm or Cancel. `lines` are built by the server. */
export interface AgentPendingAction {
  id: string;
  lines: string[];
  expires_at: string;
  /** The turn that proposed it; absent on an older response. */
  turn_id?: string;
}

/** One field of one record, before and after, in words. */
export interface AgentChange {
  record: string;
  field: string;
  before: string;
  after: string;
}

/** A done step whose form action waits out its grace window: when it applies. */
export interface AgentStepWaiting {
  commit_at: string | null;
  window_seconds: number | null;
}

export interface AgentActionStep {
  summary: string | null;
  status: 'done' | 'failed' | 'skipped' | 'proposed' | 'withdrawn' | string;
  error: string | null;
  changes?: AgentChange[];
  waiting?: AgentStepWaiting | null;
}

/** A proposal made in a turn, as it stands now: kept across reloads. */
export interface AgentConversationAction {
  id: string;
  status: 'proposed' | 'executed' | 'partial' | 'rejected' | 'cancelled' | 'expired' | string;
  decided_at: string | null;
  decided_by_name: string | null;
  steps: AgentActionStep[];
}

export interface AgentActionResponse {
  action_id: string;
  status: 'executed' | 'partial' | 'rejected' | 'cancelled' | string;
  reply_text: string;
  steps: AgentActionStep[];
}

/** The model's reasoning for one round, as the provider summarised it (console only). */
export interface AgentReasoning {
  round: number;
  text: string;
  /** The forced final answer's thinking: shown after the round's tool calls. */
  final?: boolean;
}

/** What a turn did, from its stored trace; the console shows it under the reply. */
export interface AgentSteps {
  rounds: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  /** `round` is absent on a turn stored before reasoning was kept. */
  tool_calls: { name: string; status: string; ms: number; detail?: string; round?: number }[];
  /** Absent or empty when the provider returned no reasoning. */
  reasoning?: AgentReasoning[];
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
  steps?: AgentSteps;
  /** The actions this turn proposed, with what they changed. */
  actions?: AgentConversationAction[];
}

export interface AgentConversationResponse {
  /** Null until the first turn: reading a conversation never creates one. */
  conversation_id: string | null;
  turns: AgentConversationTurn[];
  /** The contact's proposal still waiting for a decision, if any. */
  pending_action?: AgentPendingAction | null;
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

export const ACTION_REFUSAL_MESSAGES: Record<string, string> = {
  not_found: 'This proposal was not found.',
  not_newest: 'A newer proposal replaced this one.',
  expired: 'This proposal expired. Ask again to get a fresh one.',
  not_proposed: 'This proposal was already decided.',
  entry_refused: 'The agent can no longer act for this contact.',
  changed: 'The record changed since this was proposed.',
  same_turn: 'This proposal cannot be confirmed yet.',
  applied: 'That change already applied, so it can no longer be withdrawn.',
  not_waiting: 'That change is not waiting to apply.',
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
  crm_customer_asks_list: 'Customer asks',
  crm_customer_ask_update: 'Update customer ask',
  crm_agent_actions_recent: 'Recent changes',
  crm_opportunities_list: 'Opportunities',
  crm_opportunity_meta: 'Opportunity stages',
  crm_opportunity_create: 'Create opportunity',
  crm_opportunity_update: 'Update opportunity',
  crm_contacts_find: 'Find contacts',
  crm_contact_access_update: 'Update contact access',
  crm_purchase_requests_list: 'Purchase requests',
  crm_purchase_request_decide: 'Decide purchase request',
  crm_purchase_request_action_undo: 'Undo purchase request action',
  crm_idea_create: 'Log idea',
  crm_idea_update: 'Change idea',
  crm_ideas_list: 'Your ideas',
  confirm_action: 'Confirm',
  cancel_action: 'Cancel',
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
