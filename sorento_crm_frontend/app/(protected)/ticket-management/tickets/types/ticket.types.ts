/** Ticket types mirroring app/schemas/tickets.py on the backend. */

export const TICKET_STATUSES = [
  'draft',
  'submitted',
  'assigned',
  'responded',
  'resolved',
] as const;
export type TicketStatus = (typeof TICKET_STATUSES)[number];

export const TICKET_PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const;
export type TicketPriority = (typeof TICKET_PRIORITIES)[number];

export const TICKET_CATEGORIES = ['bug', 'feature', 'question', 'other'] as const;
export type TicketCategory = (typeof TICKET_CATEGORIES)[number];

export const TICKET_SOURCE_CHANNELS = [
  'manual',
  'ai_assistant',
  'whatsapp_respond',
] as const;
export type TicketSourceChannel = (typeof TICKET_SOURCE_CHANNELS)[number];

export const TICKET_RAISED_BY_KINDS = ['user', 'respond_contact'] as const;
export type TicketRaisedByKind = (typeof TICKET_RAISED_BY_KINDS)[number];

export interface TicketRaisedByActor {
  kind: TicketRaisedByKind;
  id: string;
  display_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  phone_number?: string | null;
  respond_io_id?: string | null;
}

export interface TicketUserRef {
  id: string;
  display_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
}

export interface TicketWatcherRef {
  user_id: string;
  display_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  added_at: string;
}

export interface TicketRespondContactRef {
  respond_contact_id: string;
  name?: string | null;
  phone_number?: string | null;
  respond_io_id?: string | null;
  is_primary: boolean;
}

export interface TicketAttachmentRef {
  id: string;
  attachment_id: string;
  file_name?: string | null;
  file_url?: string | null;
  file_size_bytes?: number | null;
  uploaded_at?: string | null;
}

export interface Ticket {
  id: string;
  ticket_number?: string | null;
  title: string;
  description_html?: string | null;
  description_text?: string | null;
  status: TicketStatus;
  priority: TicketPriority;
  category: TicketCategory;
  due_date?: string | null;

  raised_by?: string | null;
  raised_by_kind: TicketRaisedByKind;
  raised_by_user?: TicketUserRef | null;
  raised_by_actor?: TicketRaisedByActor | null;
  source_channel: TicketSourceChannel;
  source_conversation_id?: string | null;
  source_message_id?: string | null;
  source_space_id?: string | null;
  assigned_to?: string | null;
  assigned_to_user?: TicketUserRef | null;

  response_html?: string | null;
  response_text?: string | null;
  responded_by?: string | null;
  responded_by_user?: TicketUserRef | null;

  resolution_html?: string | null;
  resolution_text?: string | null;
  resolved_by?: string | null;
  resolved_by_user?: TicketUserRef | null;

  submitted_at?: string | null;
  assigned_at?: string | null;
  first_response_at?: string | null;
  responded_at?: string | null;
  resolved_at?: string | null;
  sla_response_due_at?: string | null;
  sla_resolution_due_at?: string | null;
  response_time_hours?: number | string | null;
  resolution_time_hours?: number | string | null;

  watchers: TicketWatcherRef[];
  respond_contacts: TicketRespondContactRef[];
  attachments: TicketAttachmentRef[];

  is_overdue_response: boolean;
  is_overdue_resolution: boolean;

  created_at: string;
  updated_at: string;
}

export interface TicketListResponse {
  data: Ticket[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}

export interface TicketKanban {
  columns: Record<TicketStatus, Ticket[]>;
  counts: Record<TicketStatus, number>;
}

export interface TicketCreateInput {
  title: string;
  description_html?: string | null;
  description_text?: string | null;
  priority?: TicketPriority;
  category?: TicketCategory;
  due_date?: string | null;
  assigned_to?: string | null;
  save_as_draft?: boolean;
  attachment_ids?: string[];
}

export interface TicketUpdateInput {
  title?: string;
  description_html?: string | null;
  description_text?: string | null;
  priority?: TicketPriority;
  category?: TicketCategory;
  due_date?: string | null;
}

export interface TicketStatusChangeInput {
  new_status: TicketStatus;
  note?: string | null;
}

export interface TicketAssignInput {
  assignee_id?: string | null;
}

export interface TicketResponseUpdateInput {
  response_html: string;
  response_text?: string | null;
}

export interface TicketResolutionUpdateInput {
  resolution_html: string;
  resolution_text?: string | null;
}

export interface TicketWatchersUpdateInput {
  user_ids: string[];
}

export interface TicketListFilters {
  status?: TicketStatus;
  assigned_to?: string;
  raised_by?: string;
  priority?: TicketPriority;
  category?: TicketCategory;
  source_channel?: TicketSourceChannel;
  due_before?: string;
  q?: string;
}
