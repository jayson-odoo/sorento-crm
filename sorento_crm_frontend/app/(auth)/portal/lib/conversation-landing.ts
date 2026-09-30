/**
 * The Conversation kind's adapter onto the landing's shared toolbar (lane SALES-CONVO): the
 * field table `LandingToolbar` filters and sorts by, the summary shape it reads, and the
 * remembered sort's default. Same idea as `stock-asks-todo.ts` for Customer asks.
 */
import type { LandingField, LandingSort } from './landing-fields';
import type { PortalSubmissionSummary } from './portal-client';
import type { PortalConversation } from './conversations-service';

export type ConversationSummary = PortalSubmissionSummary & {
  contact_name: string | null;
  contact_phone: string | null;
  last_message_at: string | null;
  /** "Customer" when the customer wrote last, "Us" otherwise: the Filter's third field. */
  last_from: string | null;
};

/** Filter and Sort share it; the date field's label is the word the Sort button prints. */
export const CONVERSATION_LANDING_FIELDS: LandingField[] = [
  { key: 'customer_name', label: 'Customer', type: 'text' },
  { key: 'contact_name', label: 'Contact', type: 'text' },
  { key: 'last_from', label: 'Last message from', type: 'text' },
  { key: 'last_message_at', label: 'Last message', type: 'date' },
];

/** Owner ruling 30 Sep (Q2): latest message first. */
export const DEFAULT_CONVERSATION_SORT: LandingSort = {
  key: 'last_message_at',
  dir: 'desc',
};

export function lastMessageFrom(
  row: Pick<PortalConversation, 'last_message_direction'>,
): string | null {
  if (row.last_message_direction === 'incoming') return 'Customer';
  if (row.last_message_direction === 'outgoing') return 'Us';
  return null;
}

export function conversationToSummary(
  row: PortalConversation,
): ConversationSummary {
  return {
    id: row.contact_id,
    kind: 'conversation',
    title: row.customer_name ?? row.contact_name ?? '',
    reference: null,
    status: '',
    is_editable: false,
    is_draft: false,
    created_at: row.last_message_at,
    customer_name: row.customer_name,
    contact_name: row.contact_name,
    contact_phone: row.contact_phone,
    last_message_at: row.last_message_at,
    last_from: lastMessageFrom(row),
  };
}

/** A stored sort that names no field of this kind reads as the default. */
export function normalizeConversationSort(sort: unknown): LandingSort {
  const key = (sort as { key?: unknown } | null)?.key;
  if (
    typeof key !== 'string' ||
    !CONVERSATION_LANDING_FIELDS.some((f) => f.key === key)
  ) {
    return DEFAULT_CONVERSATION_SORT;
  }
  return {
    key,
    dir: (sort as { dir?: unknown }).dir === 'asc' ? 'asc' : 'desc',
  };
}
