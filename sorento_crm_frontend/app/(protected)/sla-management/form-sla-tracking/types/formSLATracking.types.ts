import type { ConversationSLATracking } from '../../conversation-sla-tracking/types/conversationSLATracking.types';

/** A form-SLA stage row. Shares the conversation tracking table, discriminated by
 *  source_entity_type (stock_inquiry | purchase_request | sponsorship_form |
 *  complaint | ticket). reference/next_action are resolved server-side so the UI
 *  never shows UUIDs. */
export interface FormSLATracking extends ConversationSLATracking {
  source_entity_type?: string | null;
  source_entity_id?: string | null;
  /** Human-readable entity number (complaint/inquiry/request/ticket). */
  reference?: string | null;
  /** Stage-derived next action label (e.g. "Send for approval"). */
  next_action?: string | null;
}
