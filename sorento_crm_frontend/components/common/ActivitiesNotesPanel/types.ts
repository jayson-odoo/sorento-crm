/** Public types for ActivitiesNotesPanel — entity-generic. */

export interface ActivityActor {
  id: string;
  name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
}

export interface ActivityEvent {
  id: string;
  entity_type: string;
  entity_id: string;
  kind: 'system' | 'user_update';
  body_html?: string | null;
  body_text?: string | null;
  system_template?: string | null;
  system_payload?: Record<string, unknown> | null;
  actor?: ActivityActor | null;
  created_at: string;
  attachments: unknown[];
  mentioned_user_ids: string[];
}

export interface InternalNote {
  id: string;
  entity_type: string;
  entity_id: string;
  author_id: string;
  author?: ActivityActor | null;
  body_html?: string | null;
  body_text?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EntityRespondContact {
  contact_id: string;
  name?: string | null;
  phone?: string | null;
  is_primary: boolean;
}

export interface EntityMessage {
  id: string;
  contact_id: string;
  direction: 'incoming' | 'outgoing';
  body?: string | null;
  body_html?: string | null;
  sent_at: string;
  attachments: unknown[];
}

export interface PagedActivities {
  items: ActivityEvent[];
  has_more: boolean;
  next_cursor?: string | null;
}

export interface PagedNotes {
  items: InternalNote[];
  has_more: boolean;
  next_cursor?: string | null;
}

export interface PagedMessages {
  items: EntityMessage[];
  has_more: boolean;
  next_cursor?: string | null;
}

export type PanelTab = 'activities' | 'notes' | 'messages';
