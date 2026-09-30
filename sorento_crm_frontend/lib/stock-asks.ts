/**
 * Chatbot stock ask v2 (S5 CRM Asks tab, S6 portal Customer asks): the shared words for an
 * ask's branch, notification outcome and state, so the office and the sales agent read the
 * same labels.
 */

/**
 * `incoming_eta` and `referred` (REFER-SALESMAN, 30 Sep 2026): a dealer's incoming ETA reply and
 * every other reply that refers the dealer to their salesman. Neither carries a quantity.
 */
export type StockAskBranch = 'too_big' | 'in_stock' | 'incoming' | 'no_incoming' | 'incoming_eta' | 'referred';
export type StockAskState = 'open' | 'done';

export interface StockAsk {
  id: string;
  customer_name: string | null;
  contact_name: string | null;
  /** The contact's phone number, for the opened card's header. */
  contact_phone?: string | null;
  product_code: string;
  product_name: string | null;
  /** null on an `incoming_eta` / `referred` row: the ask named no quantity. */
  quantity: number | null;
  branch: StockAskBranch | string;
  answer_summary: string;
  notified_agent: boolean;
  notify_skip_reason: string | null;
  state: StockAskState | string;
  /** `console`: written by a chat console hand test (owner ruling 28 Sep 2026), not a dealer. */
  source?: 'live' | 'console' | string;
  note: string | null;
  created_at: string;
  updated_at: string | null;
  /** Sales-asks-todo S1: when `state` last became done (naive UTC), null while open. */
  done_at?: string | null;
  /** Sales-asks-todo S1: the name of who marked it done (a portal contact or a CRM user). */
  done_by?: string | null;
  /**
   * The owning agent's code, only sent by the CRM to-do when the caller asked for
   * `agent_id=all`, so the manager view can name the agent on line 1 of each row.
   */
  agent_code?: string | null;
}

export interface StockAskPage {
  data: StockAsk[];
  pagination: { total: number; page: number; limit: number };
}

export type StockAskPatch = { state?: StockAskState; note?: string };

export const BRANCH_LABEL: Record<string, string> = {
  too_big: 'Too big',
  in_stock: 'In stock',
  incoming: 'Incoming',
  no_incoming: 'No stock, no incoming',
  incoming_eta: 'Incoming ETA',
  referred: 'Referred',
};

export const BRANCH_VARIANT: Record<string, 'success' | 'warning' | 'info' | 'destructive' | 'secondary'> = {
  too_big: 'warning',
  in_stock: 'success',
  incoming: 'info',
  no_incoming: 'destructive',
  incoming_eta: 'info',
  referred: 'secondary',
};

export const SKIP_REASON_LABEL: Record<string, string> = {
  toggle_off: 'Notify salesman is off for this contact',
  not_notified_branch: 'This kind of answer does not notify the salesman',
  no_customer: 'The contact is not linked to one customer',
  no_sales_agent: 'The customer has no sales agent',
  agent_has_no_contact: 'The sales agent has no contact',
  agent_contact_has_no_respond_id: 'The sales agent contact is not on WhatsApp',
  send_failed: 'The WhatsApp message failed to send',
  enqueue_failed: 'The WhatsApp message could not be queued',
};

export const STATE_OPTIONS: { value: StockAskState; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'done', label: 'Done' },
];

export function stateLabel(state: string): string {
  return STATE_OPTIONS.find((o) => o.value === state)?.label ?? state;
}

/** "Sent", "Pending" (the job has not reported yet) or "Not sent", with the reason. */
export function notifiedLabel(ask: Pick<StockAsk, 'notified_agent' | 'notify_skip_reason'>): {
  label: string;
  title: string;
  variant: 'success' | 'secondary' | 'outline';
} {
  if (ask.notified_agent) return { label: 'Sent', title: 'The salesman was notified', variant: 'success' };
  if (!ask.notify_skip_reason) {
    return { label: 'Pending', title: 'The salesman notification is on its way', variant: 'outline' };
  }
  return {
    label: 'Not sent',
    title: SKIP_REASON_LABEL[ask.notify_skip_reason] ?? ask.notify_skip_reason,
    variant: 'secondary',
  };
}
